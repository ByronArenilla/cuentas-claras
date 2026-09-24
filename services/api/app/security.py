"""Hash de contraseñas y generación de tokens (RF-6, RF-8, RF-15, RF-16).

Contraseñas y tokens se tratan distinto a propósito. Una contraseña la elige
una persona y se puede adivinar: necesita un hash lento y con sal (Argon2id).
Un token es aleatorio de 128 bits o más e imposible de adivinar por fuerza
bruta: basta con SHA-256, que además es estable y permite buscarlo por hash.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Parámetros por defecto de argon2-cffi (Argon2id): la sal se genera sola y
# los parámetros quedan guardados dentro del propio hash.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de la contraseña, con sal aleatoria."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Indica si la contraseña corresponde al hash, sin lanzar excepciones."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def generate_session_token() -> str:
    """Token de sesión aleatorio de 256 bits, seguro para usar en una URL."""
    return secrets.token_urlsafe(32)


def generate_invitation_code() -> str:
    """Código de invitación aleatorio de 128 bits, seguro para usar en una URL."""
    return secrets.token_urlsafe(16)


def hash_token(token: str) -> str:
    """SHA-256 en hexadecimal: lo único que se guarda de un token o código."""
    return hashlib.sha256(token.encode()).hexdigest()
