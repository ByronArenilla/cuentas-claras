"""Entradas y salidas de la API.

Las salidas se declaran campo a campo: así ninguna respuesta puede incluir
por accidente el hash de la contraseña (RF-7).
"""

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


class SpaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RegisterOut(BaseModel):
    id: int
    email: str
    personal_space: SpaceOut
