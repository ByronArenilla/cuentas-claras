"""Entradas y salidas de la API.

Las salidas se declaran campo a campo: así ninguna respuesta puede incluir
por accidente el hash de la contraseña (RF-7).
"""

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app import dates

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

    @model_validator(mode="after")
    def item_or_category(self) -> "ExpenseIn":
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

    @field_validator("amount", "payment_type", "category_id", "spent_on", mode="before")
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
    planned: int
    spent_planned: int
    spent_unplanned: int
    spent: int
    # Ingresos menos planeado, y ingresos menos gastado: pueden ser negativos.
    unassigned: int
    balance: int


class SummaryOut(BaseModel):
    period: str
    incomes: list[IncomeSummaryOut]
    budget_items: list[ItemSummaryOut]
    categories: list[CategorySummaryOut]
    total: TotalSummaryOut
