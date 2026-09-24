"""Entradas y salidas de la API.

Las salidas se declaran campo a campo: así ninguna respuesta puede incluir
por accidente el hash de la contraseña (RF-7).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_core import PydanticCustomError

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
    # Obligatorio en cuanto existe algún usuario (RF-2); lo exige la ruta,
    # porque depende del estado de la base de datos y no solo de la entrada.
    invitation_code: str | None = None

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


class RegisterOut(BaseModel):
    id: int
    email: str
    personal_space: SpaceOut


class InvitationOut(BaseModel):
    # El código en claro solo aparece en esta respuesta: la base de datos
    # guarda su hash y no lo puede volver a mostrar.
    code: str
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
