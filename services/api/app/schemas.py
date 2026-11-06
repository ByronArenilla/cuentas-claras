"""Entradas y salidas de la API.

Las salidas se declaran campo a campo: así ninguna respuesta puede incluir
por accidente el hash de la contraseña (RF-7).
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app import dates
from app.installments import Installment
from app.models import Card

MIN_PASSWORD_LENGTH = 12
MAX_EMAIL_LENGTH = 320


def normalize_email(value: str) -> str:
    """Comprobación mínima propia del correo (plan 001), sin `email-validator`.

    Exige una sola `@`, partes no vacías, un punto en el dominio y ningún
    espacio. Devuelve el correo sin espacios alrededor y en minúsculas.
    """
    email = value.strip().lower()
    local, at, domain = email.partition("@")
    valid = (
        at == "@"
        and local
        and "@" not in domain
        and "." in domain.strip(".")
        and not any(char.isspace() for char in email)
        and len(email) <= MAX_EMAIL_LENGTH
    )
    if not valid:
        raise PydanticCustomError("invalid_email", "El correo no es válido.")
    return email


class RegisterIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        # Solo longitud, sin exigir mayúsculas ni símbolos (NIST, plan 001).
        if len(value) < MIN_PASSWORD_LENGTH:
            raise PydanticCustomError(
                "password_too_short",
                "La contraseña debe tener al menos {min_length} caracteres.",
                {"min_length": MIN_PASSWORD_LENGTH},
            )
        return value


MAX_SPACE_NAME_LENGTH = 100


class SpaceIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        # Sin espacios alrededor: el nombre se confirma letra a letra al
        # borrar el espacio (RF-25) y un espacio invisible lo haría imposible.
        name = value.strip()
        if not 1 <= len(name) <= MAX_SPACE_NAME_LENGTH:
            raise PydanticCustomError(
                "invalid_space_name",
                "El nombre del espacio debe tener entre 1 y {max_length} caracteres.",
                {"max_length": MAX_SPACE_NAME_LENGTH},
            )
        return name


class SpaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


MAX_CATEGORY_NAME_LENGTH = 50


class CategoryIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        # Se guarda sin espacios alrededor (RF-6) y el límite se mide después
        # de quitarlos, así "   " cuenta como vacío (RF-7, decisión 5).
        name = value.strip()
        if not 1 <= len(name) <= MAX_CATEGORY_NAME_LENGTH:
            raise PydanticCustomError(
                "invalid_category_name",
                "El nombre de la categoría debe tener entre 1 y {max_length} "
                "caracteres.",
                {"max_length": MAX_CATEGORY_NAME_LENGTH},
            )
        return name


class CategoryOut(BaseModel):
    # Sin `name_key`: la clave solo sirve para comparar nombres (plan 002).
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CategoryDeletedOut(BaseModel):
    # Con el aviso de cómo volver a usarla, que la web muestra tal cual
    # (spec 008, decisión 23).
    id: int
    name: str
    message: str


class RegisterOut(BaseModel):
    id: int
    email: str
    personal_space: SpaceOut


class InvitationOut(BaseModel):
    # Enlace `<WEB_BASE_URL>/unirse/<token>` (RF-15). El token en claro solo
    # aparece dentro de esta URL: la base de datos guarda su hash y no lo
    # puede volver a mostrar.
    url: str
    expires_at: datetime


class InvitationPreviewOut(BaseModel):
    # Lo que ve cualquiera con el enlace, sin sesión (RF-36): ni el id del
    # espacio, ni sus miembros, ni quién invitó.
    space_name: str
    expires_at: datetime


class LoginIn(BaseModel):
    # Sin validar formato ni longitud: unas credenciales mal escritas se
    # rechazan con el mismo mensaje que unas equivocadas (RF-9).
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


# --- Gastos (spec 003) ---

MAX_AMOUNT = 1_000_000_000_000  # Un billón de pesos (decisión 7).
MAX_DESCRIPTION_LENGTH = 200
PAYMENT_TYPES = ("credit", "debit")

# Solo dígitos ASCII, como el periodo en `app/dates.py`.
DAY_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def check_amount(value: object) -> object:
    # Antes de la conversión de Pydantic, que haría de `20000.0` y `"20000"`
    # un `20000` (RF-3). `type(...) is int` también rechaza `true`.
    if type(value) is not int:
        raise PydanticCustomError(
            "invalid_amount_type",
            "El monto debe ser un número entero de pesos, sin decimales.",
        )
    if not 1 <= value <= MAX_AMOUNT:
        raise PydanticCustomError(
            "invalid_amount_range",
            "El monto debe ser mayor que cero y como máximo {max_amount}.",
            {"max_amount": MAX_AMOUNT},
        )
    return value


def check_payment_type(value: object) -> object:
    if value not in PAYMENT_TYPES:
        raise PydanticCustomError(
            "invalid_payment_type",
            "El tipo de pago debe ser credit o debit.",
        )
    return value


def parse_spent_on(value: object) -> date:
    # Solo el texto `AAAA-MM-DD`: Pydantic aceptaría también un instante
    # como `2026-10-01T00:00:00`, y la fecha del gasto es un día (decisión 2).
    if isinstance(value, str) and DAY_PATTERN.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass  # Formato correcto pero día inexistente, como `2026-02-30`.
    raise PydanticCustomError(
        "invalid_spent_on",
        "La fecha debe ser un día real con el formato AAAA-MM-DD.",
    )


def check_not_future(value: date) -> date:
    # "Hoy" en `TZ` (RF-6, principio 7).
    if value > dates.today():
        raise PydanticCustomError(
            "future_spent_on",
            "La fecha del gasto no puede ser posterior a hoy.",
        )
    return value


def clean_description(value: str | None) -> str | None:
    # Se guarda sin espacios alrededor, y vacía cuenta como ausente (RF-7).
    if value is None:
        return None
    description = value.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise PydanticCustomError(
            "description_too_long",
            "La descripción puede tener como máximo {max_length} caracteres.",
            {"max_length": MAX_DESCRIPTION_LENGTH},
        )
    return description or None


# Tipos con sus validaciones, compartidos por `ExpenseIn` y `ExpensePatch`
# para que editar valide exactamente igual que registrar (RF-13).
Amount = Annotated[int, BeforeValidator(check_amount)]
PaymentType = Annotated[Literal["credit", "debit"], BeforeValidator(check_payment_type)]
SpentOn = Annotated[
    date, BeforeValidator(parse_spent_on), AfterValidator(check_not_future)
]
Description = Annotated[str | None, AfterValidator(clean_description)]


# Spec 008, RF-17: un gasto planeado lleva su rubro; uno no planeado, su
# categoría. Nunca los dos ni ninguno.
EXACTLY_ONE_MESSAGE = (
    "Indica el rubro del gasto o, si no estaba planeado, su categoría, pero no los dos."
)

# Spec 009: un gasto a crédito lleva tarjeta, descripción y categoría, nunca
# rubro (RF-9, decisiones 2, 8 y 26); uno a débito, ni tarjeta ni cuotas
# (RF-10).
CARD_REQUIRED_MESSAGE = "Un gasto a crédito necesita la tarjeta con la que se pagó."
NO_ITEM_ON_CARD_MESSAGE = (
    "Una compra con tarjeta no lleva rubro: cuenta en Deudas el mes en que se "
    "paga la tarjeta. Indica su categoría."
)
DESCRIPTION_REQUIRED_MESSAGE = (
    "Una compra con tarjeta necesita una descripción: es el nombre con el que "
    "sus cuotas salen en Deudas."
)
CATEGORY_REQUIRED_MESSAGE = "Una compra con tarjeta necesita su categoría."
DEBIT_WITHOUT_CARD_MESSAGE = "Un gasto a débito no lleva tarjeta ni cuotas."
MAX_INSTALLMENTS = 48


def check_installments(value: object) -> object:
    # Entero de 1 a 48 (RF-11, decisión 10). Estricto: ni `"3"`, ni `3.0`, ni
    # `true`.
    valid = isinstance(value, int) and not isinstance(value, bool)
    if not valid or not 1 <= value <= MAX_INSTALLMENTS:
        raise PydanticCustomError(
            "invalid_installments",
            "Las cuotas deben ser un número entero de 1 a {max_installments}.",
            {"max_installments": MAX_INSTALLMENTS},
        )
    return value


Installments = Annotated[int, BeforeValidator(check_installments)]


class ExpenseIn(BaseModel):
    # Sin `space_id` ni `created_by`: salen de la ruta y de la sesión, y si
    # llegan en el cuerpo se ignoran (RF-14).
    amount: Amount
    payment_type: PaymentType
    # Estrictos: `true` o `"1"` no son un id. Que el rubro o la categoría
    # existan en el espacio lo comprueba la ruta (RF-5; RF-18 de la 008).
    # Con rubro, la categoría sale del rubro (decisión 13 de la 008).
    budget_item_id: StrictInt | None = None
    category_id: StrictInt | None = None
    # `dates.today()` al validar, no al definir la clase (RF-2).
    spent_on: SpentOn = Field(default_factory=lambda: dates.today())
    description: Description = None
    # Compra con tarjeta (spec 009). Que la tarjeta exista en el espacio y
    # esté activa lo comprueba la ruta (RF-12).
    card_id: StrictInt | None = None
    installments: Installments | None = None

    @model_validator(mode="after")
    def payment_rules(self) -> "ExpenseIn":
        if self.payment_type == "credit":
            if self.card_id is None:
                raise PydanticCustomError("card_required", CARD_REQUIRED_MESSAGE)
            if self.budget_item_id is not None:
                raise PydanticCustomError("no_item_on_card", NO_ITEM_ON_CARD_MESSAGE)
            if self.description is None:
                raise PydanticCustomError(
                    "description_required", DESCRIPTION_REQUIRED_MESSAGE
                )
            if self.category_id is None:
                raise PydanticCustomError(
                    "category_required", CATEGORY_REQUIRED_MESSAGE
                )
            if self.installments is None:
                self.installments = 1
            return self

        if self.card_id is not None or self.installments is not None:
            raise PydanticCustomError("debit_without_card", DEBIT_WITHOUT_CARD_MESSAGE)
        if (self.budget_item_id is None) == (self.category_id is None):
            raise PydanticCustomError("item_or_category", EXACTLY_ONE_MESSAGE)
        return self


class ExpensePatch(BaseModel):
    # Todo es opcional y la ruta aplica solo `model_fields_set` (RF-13).
    amount: Amount | None = None
    payment_type: PaymentType | None = None
    category_id: StrictInt | None = None
    spent_on: SpentOn | None = None
    # `null` aquí sí vale: quita la descripción (decisión 8).
    description: Description = None
    # `null` también vale: quita el rubro y el gasto queda no planeado (RF-21
    # de la 008). Las reglas que cruzan campos las aplica la ruta.
    budget_item_id: StrictInt | None = None
    # Spec 009. Para quitarle la tarjeta a una compra se cambia a débito, así
    # que `null` no vale (RF-15).
    card_id: StrictInt | None = None
    installments: Installments | None = None

    @field_validator(
        "amount",
        "payment_type",
        "category_id",
        "spent_on",
        "card_id",
        "installments",
        mode="before",
    )
    @classmethod
    def reject_null(cls, value: object) -> object:
        # Sin esto, `None` pasaría por el `| None` del tipo y el gasto se
        # quedaría sin monto, tipo de pago, categoría o fecha.
        if value is None:
            raise PydanticCustomError(
                "null_not_allowed",
                "Este campo no puede quedar vacío; si no quieres cambiarlo, "
                "no lo envíes.",
            )
        return value


class ExpenseOut(BaseModel):
    # Sin `space_id`, que ya está en la ruta, ni el nombre de la categoría,
    # que el cliente tiene en su lista (plan 003, RF-8).
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    payment_type: str
    category_id: int
    spent_on: date
    description: str | None
    created_by: int
    created_at: datetime
    # Nulo si no estaba planeado (RF-20 de la 008).
    budget_item_id: int | None
    # Compra con tarjeta (spec 009, RF-18): nulos si no lo es. El mes de la
    # primera cuota sale como `AAAA-MM`, como los periodos.
    card_id: int | None
    installments: int | None
    first_due_period: Annotated[
        str | None,
        # `month_of` se define más abajo, con los periodos: la lambda lo busca
        # al validar, no al definir la clase.
        BeforeValidator(lambda value: month_of(value)),
        Field(validation_alias="first_due_start"),
    ]


# --- Periodo (spec 004) ---

# Lo usan también el listado de gastos y el resumen: un periodo mal escrito
# recibe el mismo mensaje en toda la API (plan 004).
PERIOD_FORMAT_MESSAGE = "El periodo debe tener el formato AAAA-MM, por ejemplo 2026-10."


def check_period(value: object) -> object:
    # `period_bounds` es la única regla de qué es un mes válido (plan 003).
    try:
        if not isinstance(value, str):
            raise ValueError
        dates.period_bounds(value)
    except ValueError:
        raise PydanticCustomError("invalid_period", PERIOD_FORMAT_MESSAGE) from None
    return value


Period = Annotated[str, BeforeValidator(check_period)]


# --- Plan del mes: rubros, ingresos y copia (spec 008) ---

MAX_PLAN_NAME_LENGTH = 50


def plan_name(kind: str) -> AfterValidator:
    """Validador del nombre de un rubro o un ingreso (RF-3, RF-10): sin
    espacios alrededor y de 1 a 50 caracteres, como las categorías."""

    def check(value: str) -> str:
        name = value.strip()
        if not 1 <= len(name) <= MAX_PLAN_NAME_LENGTH:
            raise PydanticCustomError(
                "invalid_plan_name",
                "El nombre del {kind} debe tener entre 1 y {max_length} caracteres.",
                {"kind": kind, "max_length": MAX_PLAN_NAME_LENGTH},
            )
        return name

    return AfterValidator(check)


ItemName = Annotated[str, plan_name("rubro")]
IncomeName = Annotated[str, plan_name("ingreso")]


def current_period() -> str:
    # Al validar, no al definir la clase: "hoy" cambia (RF-2).
    return dates.period_of(dates.today())


def reject_period_change(data: object) -> object:
    """El mes de un rubro o de un ingreso no se cambia (decisión 12). Se
    rechaza con un mensaje en lugar de ignorarlo en silencio."""
    if isinstance(data, dict) and "period" in data:
        raise PydanticCustomError(
            "period_not_editable",
            "El mes no se cambia: bórralo y créalo de nuevo en el otro mes.",
        )
    return data


def reject_nulls(value: object) -> object:
    # Sin esto, `None` pasaría por el `| None` del tipo y el rubro o el
    # ingreso se quedaría sin nombre, categoría o monto.
    if value is None:
        raise PydanticCustomError(
            "null_not_allowed",
            "Este campo no puede quedar vacío; si no quieres cambiarlo, no lo envíes.",
        )
    return value


def month_of(value: object) -> object:
    # Las filas guardan el día 1 del mes (`period_start`); se responde con el
    # mes `AAAA-MM`, igual que en la petición.
    return dates.period_of(value) if isinstance(value, date) else value


# Lee `period_start` de la fila y lo devuelve como `period`.
PeriodOut = Annotated[
    str, BeforeValidator(month_of), Field(validation_alias="period_start")
]


class BudgetItemIn(BaseModel):
    # Sin `space_id`: sale de la ruta.
    period: Period = Field(default_factory=current_period)
    name: ItemName
    # Que exista y esté activa en el espacio lo comprueba la ruta (RF-5).
    category_id: StrictInt
    amount: Amount


class BudgetItemPatch(BaseModel):
    # La ruta aplica solo `model_fields_set` (RF-6).
    name: ItemName | None = None
    category_id: StrictInt | None = None
    amount: Amount | None = None

    _no_period = model_validator(mode="before")(reject_period_change)
    _no_nulls = field_validator("name", "category_id", "amount", mode="before")(
        reject_nulls
    )


class BudgetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period: PeriodOut
    name: str
    category_id: int
    amount: int


class IncomeIn(BaseModel):
    period: Period = Field(default_factory=current_period)
    name: IncomeName
    amount: Amount


class IncomePatch(BaseModel):
    name: IncomeName | None = None
    amount: Amount | None = None

    _no_period = model_validator(mode="before")(reject_period_change)
    _no_nulls = field_validator("name", "amount", mode="before")(reject_nulls)


class IncomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period: PeriodOut
    name: str
    amount: int


class PlanCopyIn(BaseModel):
    # El mes destino; el origen es el inmediatamente anterior (decisión 9).
    period: Period = Field(default_factory=current_period)


# --- Resumen del mes (spec 008, reemplaza al de la 004) ---
# Solo enteros en la unidad mínima de la moneda (RF-24, principio 6). Ningún
# campo es nulo: sin plan, las listas salen vacías y los montos en 0 (RF-25).


class IncomeSummaryOut(BaseModel):
    id: int
    name: str
    amount: int


class ItemSummaryOut(BaseModel):
    id: int
    name: str
    category_id: int
    planned: int
    spent: int
    # Negativo si se excedió.
    remaining: int


class CategorySummaryOut(BaseModel):
    # Con el nombre: el resumen es lo que la web muestra tal cual (plan 004).
    category_id: int
    name: str
    # Suma de sus rubros del mes; 0 si no tiene.
    planned: int
    # Todos sus gastos del mes, planeados o no.
    spent: int
    # Solo salen eliminadas si tienen rubros o gastos en el mes (decisión 18).
    deleted: bool


class TotalSummaryOut(BaseModel):
    income: int
    # Desde la 009: lo planeado en rubros más las deudas del mes (RF-38).
    planned: int
    # Deudas de todas las tarjetas en el mes (spec 009, RF-35).
    debts: int
    spent_planned: int
    spent_unplanned: int
    # Desde la 009: gastado en rubros más no planeado más las deudas (RF-38).
    spent: int
    # Ingresos menos planeado, y ingresos menos gastado: pueden ser negativos.
    unassigned: int
    balance: int


class DebtInstallmentOut(BaseModel):
    """Cuota de una compra que se paga en el mes (spec 009, RF-36)."""

    expense_id: int
    # La descripción de la compra (decisión 23).
    name: str
    number: int
    count: int
    capital: int
    interest: int
    amount: int


class DebtPrepaymentOut(BaseModel):
    id: int
    expense_id: int
    name: str
    amount: int


class CardDebtOut(BaseModel):
    """Deuda de una tarjeta en el mes (spec 009, RF-34 a RF-36)."""

    card_id: int
    name: str
    # Una archivada sale si tiene algo en el mes (decisión 21).
    deleted: bool
    installments: list[DebtInstallmentOut]
    prepayments: list[DebtPrepaymentOut]
    # Suma de las cuotas del mes, con intereses estimados.
    estimated: int
    # Valor real del extracto, o nulo si no se escribió.
    statement: int | None
    # El valor real o lo estimado, más los abonos del mes.
    amount: int


class SummaryOut(BaseModel):
    period: str
    incomes: list[IncomeSummaryOut]
    budget_items: list[ItemSummaryOut]
    categories: list[CategorySummaryOut]
    # Spec 009: una entrada por tarjeta con cuotas, abonos o valor real en el
    # mes (RF-36).
    debts: list[CardDebtOut]
    total: TotalSummaryOut


class SkippedItemOut(BaseModel):
    # Rubro que la copia omitió porque su categoría está eliminada
    # (decisión 15).
    name: str
    category: str


class PlanCopyOut(BaseModel):
    # El resumen del mes destino, que es lo que la web muestra después, y los
    # rubros omitidos (RF-13).
    summary: SummaryOut
    skipped: list[SkippedItemOut]


# --- Tarjetas (spec 009) ---

MAX_CARD_NAME_LENGTH = 50
MAX_RATE = Decimal(10)
RATE_MESSAGE = (
    "La tasa mensual debe ser un número de 0.01 a 10 con hasta dos decimales, "
    "por ejemplo 1.89."
)


def check_card_name(value: str) -> str:
    # Como las categorías: sin espacios alrededor y de 1 a 50 caracteres
    # (RF-2).
    name = value.strip()
    if not 1 <= len(name) <= MAX_CARD_NAME_LENGTH:
        raise PydanticCustomError(
            "invalid_card_name",
            "El nombre de la tarjeta debe tener entre 1 y {max_length} caracteres.",
            {"max_length": MAX_CARD_NAME_LENGTH},
        )
    return name


def card_day(label: str) -> BeforeValidator:
    """Día de corte o de pago: entero de 1 a 31 (RF-3). Estricto: ni `"5"` ni
    `5.0` ni `true` son un día."""

    def check(value: object) -> object:
        valid = isinstance(value, int) and not isinstance(value, bool)
        if not valid or not 1 <= value <= 31:
            raise PydanticCustomError(
                "invalid_card_day", f"El {label} debe ser un número entero de 1 a 31."
            )
        return value

    return BeforeValidator(check)


def parse_rate(value: object) -> object:
    """Tasa mensual en porcentaje: número de 0,01 a 10 con hasta dos decimales
    (RF-3, decisión 27). Se convierte a `Decimal` y nunca se calcula con
    `float`.

    El JSON llega a Python como `float` (`1.89`); `str()` da el número tal
    como se escribió, porque Python muestra el decimal más corto que vuelve
    al mismo `float`, y de ahí sale un `Decimal` exacto. Texto y booleanos se
    rechazan, como en los montos.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PydanticCustomError("invalid_rate", RATE_MESSAGE)
    rate = Decimal(str(value))
    # `as_tuple().exponent` es -2 para 1.89 y -3 para 1.895.
    if not 0 < rate <= MAX_RATE or rate.as_tuple().exponent < -2:
        raise PydanticCustomError("invalid_rate", RATE_MESSAGE)
    return rate


def rate_to_bp(rate: Decimal | None) -> int | None:
    """De porcentaje a puntos básicos, como se guarda: 1.89 → 189."""
    return None if rate is None else int(rate * 100)


def rate_from_bp(rate_bp: int | None) -> Decimal | None:
    return None if rate_bp is None else Decimal(rate_bp) / 100


def rate_number(rate: Decimal | None) -> float | int | None:
    # Sale como número JSON (`1.89`) y no como texto, que es lo que Pydantic
    # hace con un `Decimal`. Solo es para mostrarla: ningún cálculo usa este
    # `float`.
    if rate is None:
        return None
    return int(rate) if rate == rate.to_integral_value() else float(rate)


CardName = Annotated[str, AfterValidator(check_card_name)]
CutoffDay = Annotated[int, card_day("día de corte")]
DueDay = Annotated[int, card_day("día límite de pago")]
MonthlyRate = Annotated[Decimal | None, BeforeValidator(parse_rate)]
RateOut = Annotated[Decimal | None, PlainSerializer(rate_number)]


class CardIn(BaseModel):
    name: CardName
    cutoff_day: CutoffDay
    due_day: DueDay
    monthly_rate: MonthlyRate = None


class CardPatch(BaseModel):
    # La ruta aplica solo `model_fields_set` (RF-5).
    name: CardName | None = None
    cutoff_day: CutoffDay | None = None
    due_day: DueDay | None = None
    # `null` aquí sí vale: quita la tasa.
    monthly_rate: MonthlyRate = None

    _no_nulls = field_validator("name", "cutoff_day", "due_day", mode="before")(
        reject_nulls
    )


class CardOut(BaseModel):
    id: int
    name: str
    cutoff_day: int
    due_day: int
    monthly_rate: RateOut
    # Una archivada sale en Deudas, en su estado y al editarla (decisión 21).
    deleted: bool

    @classmethod
    def of(cls, card: Card) -> "CardOut":
        return cls(
            id=card.id,
            name=card.name,
            cutoff_day=card.cutoff_day,
            due_day=card.due_day,
            monthly_rate=rate_from_bp(card.monthly_rate_bp),
            deleted=card.deleted_at is not None,
        )


class CardDeletedOut(BaseModel):
    # Con el aviso de que sus cuotas siguen llegando y cómo volver a usarla
    # (RF-6), que la web muestra tal cual.
    id: int
    name: str
    message: str


# --- Cuotas, abonos y valor real del extracto (spec 009) ---


class InstallmentOut(BaseModel):
    """Una cuota de una compra con tarjeta (RF-21). `count` es el total de
    cuotas tras los abonos."""

    number: int
    count: int
    period: str
    capital: int
    interest: int
    amount: int
    balance_after: int

    @classmethod
    def of(cls, row: Installment) -> "InstallmentOut":
        return cls(
            number=row.number,
            count=row.count,
            period=row.period,
            capital=row.capital,
            interest=row.interest,
            amount=row.amount,
            balance_after=row.balance_after,
        )


class PrepaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_id: int
    period: PeriodOut
    amount: int
    reduces: str


class ScheduleOut(BaseModel):
    """Plan de cuotas de una compra con sus abonos (RF-21)."""

    expense_id: int
    card_id: int
    installments: list[InstallmentOut]
    prepayments: list[PrepaymentOut]


def check_statement_amount(value: object) -> object:
    # Entero de 0 a un billón (RF-31, decisión 20). A diferencia del monto de
    # un gasto, `0` vale: un mes en que la tarjeta no cobró nada.
    valid = isinstance(value, int) and not isinstance(value, bool)
    if not valid or not 0 <= value <= MAX_AMOUNT:
        raise PydanticCustomError(
            "invalid_statement_amount",
            "El valor del extracto debe ser un número entero de 0 a {max_amount}.",
            {"max_amount": MAX_AMOUNT},
        )
    return value


class StatementIn(BaseModel):
    amount: Annotated[int, BeforeValidator(check_statement_amount)]


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: int
    period: PeriodOut
    amount: int


def check_reduces(value: object) -> object:
    if value not in ("installment", "term"):
        raise PydanticCustomError(
            "invalid_reduces",
            "Indica si el abono baja la cuota (installment) o el plazo (term).",
        )
    return value


class PrepaymentIn(BaseModel):
    # Mismas reglas que el monto de un gasto (RF-23).
    amount: Amount
    # Cualquier mes con cuota y saldo después, también futuro (decisión 19).
    period: Period = Field(default_factory=current_period)
    reduces: Annotated[Literal["installment", "term"], BeforeValidator(check_reduces)]


class PrepaymentCreatedOut(BaseModel):
    # El abono y el plan de cuotas nuevo de la compra (RF-22).
    prepayment: PrepaymentOut
    schedule: ScheduleOut


def format_pesos(amount: int) -> str:
    """Monto con punto de miles, como se escribe en Colombia: 1.000.000."""
    return f"{amount:,}".replace(",", ".")


class PayoffIn(BaseModel):
    # Mes en que se paga todo; por defecto el actual (RF-29).
    period: Period = Field(default_factory=current_period)


class PayoffOut(BaseModel):
    period: str
    # Un abono por cada compra saldada.
    prepayments: list[PrepaymentOut]
    # La deuda de la tarjeta en ese mes, con los abonos nuevos (RF-35).
    debt: int
