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


class ExpenseIn(BaseModel):
    # Sin `space_id` ni `created_by`: salen de la ruta y de la sesión, y si
    # llegan en el cuerpo se ignoran (RF-14).
    amount: Amount
    payment_type: PaymentType
    # Estricto: `true` o `"1"` no son el id de una categoría. Que exista en
    # el espacio lo comprueba la ruta (RF-5).
    category_id: StrictInt
    # `dates.today()` al validar, no al definir la clase (RF-2).
    spent_on: SpentOn = Field(default_factory=lambda: dates.today())
    description: Description = None


class ExpensePatch(BaseModel):
    # Todo es opcional y la ruta aplica solo `model_fields_set` (RF-13).
    amount: Amount | None = None
    payment_type: PaymentType | None = None
    category_id: StrictInt | None = None
    spent_on: SpentOn | None = None
    # `null` aquí sí vale: quita la descripción (decisión 8).
    description: Description = None

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
