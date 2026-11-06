"""Plan de cuotas de una compra con tarjeta (spec 009, RF-19 a RF-26).

Capital fijo e interés sobre el saldo, como los extractos en Colombia
(decisión 5). Las cuotas no se guardan: se calculan al leer, con la tasa
actual de la tarjeta y los abonos de la compra (plan 009, ADR 0013).

Funciones puras, sin base de datos ni HTTP (principio 10). Todos los montos
son pesos enteros (principio 6) y la tasa va en puntos básicos: 1,89 % es
`189`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app import dates

Reduces = Literal["installment", "term"]


@dataclass(frozen=True)
class PrepaymentPlan:
    """Abono que entra al cálculo: su mes, su monto y si baja la cuota
    (`installment`) o el plazo (`term`)."""

    period: str
    amount: int
    reduces: Reduces


@dataclass(frozen=True)
class Installment:
    """Una cuota. `count` es el total de cuotas de la compra después de los
    abonos, para que una cuota diga "2 de 4" tras bajar el plazo."""

    number: int
    count: int
    period: str
    capital: int
    interest: int
    # Saldo después de esta cuota y, si lo hay, del abono de su mes.
    balance_after: int

    @property
    def amount(self) -> int:
        return self.capital + self.interest


def split_capital(amount: int, count: int) -> list[int]:
    """Reparte `amount` en `count` cuotas de pesos enteros. Si la división no
    es exacta, cada una de las primeras lleva un peso más (decisión 15)."""
    base, extra = divmod(amount, count)
    return [base + 1 if index < extra else base for index in range(count)]


def interest(balance: int, rate_bp: int | None) -> int:
    """Interés de un mes sobre `balance`, redondeado al peso con el medio
    peso hacia arriba (decisión 15). Sin tasa, `0` (decisión 16).

    Con enteros: `balance * rate_bp / 10000`, sumando media unidad antes de
    la división entera para redondear hacia arriba desde el medio peso.
    """
    if rate_bp is None:
        return 0
    return (balance * rate_bp + 5_000) // 10_000


def _term_capital(balance: int, capital: int) -> list[int]:
    """Cuotas de `capital` hasta cubrir `balance`; la última lleva el resto
    (RF-25, abono que baja el plazo)."""
    full, rest = divmod(balance, capital)
    return [capital] * full + ([rest] if rest else [])


def build_schedule(
    amount: int,
    count: int,
    rate_bp: int | None,
    first_period: str,
    prepayments: Sequence[PrepaymentPlan],
) -> list[Installment]:
    """Cuotas de una compra de `amount` a `count` cuotas con primera cuota en
    `first_period`, aplicando los abonos en orden de mes (RF-19 a RF-26).

    Cada abono se descuenta del saldo después de la cuota de su mes y rehace
    las cuotas siguientes. Un abono que pasa del saldo o cae en un mes sin
    cuota lanza `ValueError`: la API los rechaza antes (RF-23), así que aquí
    sería un error de programación.
    """
    by_period = {prepayment.period: prepayment for prepayment in prepayments}
    # Una compra a 1 cuota no genera intereses (decisión 15).
    charges_interest = count > 1
    capitals = split_capital(amount, count)
    balance = amount
    rows: list[tuple[str, int, int, int]] = []
    period = first_period

    while balance > 0:
        capital = capitals[len(rows)]
        month_interest = interest(balance, rate_bp) if charges_interest else 0
        balance -= capital

        prepayment = by_period.pop(period, None)
        if prepayment is not None:
            if prepayment.amount > balance:
                raise ValueError(
                    f"El abono de {period} pasa del saldo después de su cuota."
                )
            balance -= prepayment.amount
            done = len(rows) + 1
            if prepayment.reduces == "term":
                rest = _term_capital(balance, capitals[done]) if balance else []
            else:
                rest = split_capital(balance, len(capitals) - done) if balance else []
            capitals = capitals[:done] + rest

        rows.append((period, capital, month_interest, balance))
        period = dates.shift_period(period, 1)

    if by_period:
        raise ValueError(f"Hay abonos en meses sin cuota: {sorted(by_period)}.")

    total = len(rows)
    return [
        Installment(
            number=number,
            count=total,
            period=row_period,
            capital=capital,
            interest=month_interest,
            balance_after=balance_after,
        )
        for number, (row_period, capital, month_interest, balance_after) in enumerate(
            rows, start=1
        )
    ]


def prepayment_limit(schedule: Sequence[Installment], period: str) -> int | None:
    """Máximo que se puede abonar en `period`: el saldo después de la cuota
    de ese mes (RF-23). `None` si ese mes no tiene cuota o no queda saldo.

    Supone que `period` aún no tiene abono: un abono nuevo siempre es de un
    mes posterior a los que ya tiene la compra (decisión 18).
    """
    for row in schedule:
        if row.period == period:
            return row.balance_after or None
    return None
