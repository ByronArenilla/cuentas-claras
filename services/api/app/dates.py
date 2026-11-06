"""Reloj y periodos de la API (principio 7).

Los instantes van en UTC; "hoy" y el mes de un gasto se calculan en la zona
configurada en `TZ`. Los tests fijan el reloj sustituyendo `now` con
`monkeypatch`, así que el resto del código debe llamarlo como `dates.now()`
o a través de `today()`, nunca importarlo con `from app.dates import now`.
"""

import calendar
import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import settings

# Solo dígitos ASCII: `\d` también aceptaría dígitos de otros alfabetos.
PERIOD_PATTERN = re.compile(r"([0-9]{4})-([0-9]{2})")


def now() -> datetime:
    """El instante actual en UTC. Es el único punto que los tests sustituyen."""
    return datetime.now(UTC)


def today() -> date:
    """El día de hoy en `TZ`, no en la zona del proceso como `date.today()`."""
    return now().astimezone(ZoneInfo(settings.tz)).date()


def period_of(day: date) -> str:
    """El periodo `YYYY-MM` al que pertenece un día."""
    return f"{day.year:04d}-{day.month:02d}"


def period_bounds(period: str) -> tuple[date, date]:
    """Primer día del periodo y primer día del periodo siguiente.

    Se filtra con `start <= spent_on < end`, así que no importa cuántos días
    tenga el mes. Lanza `ValueError` si `period` no es un mes `YYYY-MM`.
    """
    match = PERIOD_PATTERN.fullmatch(period)
    if match is None or not 1 <= int(match[2]) <= 12:
        raise ValueError(f"Periodo inválido: {period!r}. Usa el formato AAAA-MM.")
    year, month = int(match[1]), int(match[2])
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def previous_period(period: str) -> str:
    """El periodo anterior: de `2026-01` sale `2025-12` (spec 008, RF-13).

    Lanza `ValueError` si `period` no es un mes `YYYY-MM`.
    """
    start, _ = period_bounds(period)
    if start.month == 1:
        return period_of(date(start.year - 1, 12, 1))
    return period_of(date(start.year, start.month - 1, 1))


def shift_period(period: str, months: int) -> str:
    """El periodo `months` meses después (o antes, si es negativo): de
    `2026-11` y `2` sale `2027-01` (spec 009, RF-13).

    Lanza `ValueError` si `period` no es un mes `YYYY-MM`.
    """
    start, _ = period_bounds(period)
    # Meses contados desde el año 0: así se suma sin pensar en cambios de año.
    year, month_index = divmod(start.year * 12 + start.month - 1 + months, 12)
    return f"{year:04d}-{month_index + 1:02d}"


def _day_in_month(year: int, month: int, day: int) -> date:
    """El día `day` del mes o, si el mes no lo tiene (un 31 en abril), su
    último día (decisión 12 de la 009)."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _next_month(day: date) -> tuple[int, int]:
    return (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)


def first_due_period(spent_on: date, cutoff_day: int, due_day: int) -> str:
    """Mes de pago de la primera cuota de una compra con tarjeta (spec 009,
    decisión 12, RF-13).

    La compra entra en el primer corte en su fecha o después (una compra el
    mismo día de corte entra en ese corte), y se paga en el primer día límite
    estrictamente después de ese corte.
    """
    cutoff = _day_in_month(spent_on.year, spent_on.month, cutoff_day)
    if cutoff < spent_on:
        cutoff = _day_in_month(*_next_month(spent_on), cutoff_day)

    due = _day_in_month(cutoff.year, cutoff.month, due_day)
    if due <= cutoff:
        due = _day_in_month(*_next_month(cutoff), due_day)
    return period_of(due)
