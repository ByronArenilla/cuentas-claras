"""Hash de contraseñas y generación de tokens (RF-6, RF-8, RF-15) y de códigos
de vinculación de Telegram (spec 005).

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


def generate_invitation_token() -> str:
    """Token de invitación aleatorio de 128 bits, seguro para usar en una URL."""
    return secrets.token_urlsafe(16)


def hash_token(token: str) -> str:
    """SHA-256 en hexadecimal: lo único que se guarda de un token."""
    return hashlib.sha256(token.encode()).hexdigest()


# Crockford base32: sin I, L, O ni U, que se confunden con 1, 0 o V al
# copiar el código a mano (plan 005).
LINK_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LINK_CODE_LENGTH = 8


def generate_link_code() -> str:
    """Código de vinculación aleatorio de 40 bits, como `ABCD-EFGH`.

    Con 10 minutos de vida (RF-1), probar códigos a través de Telegram no
    llega a acertar ninguno. El guion solo ayuda a leerlo.
    """
    chars = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))
    return f"{chars[:4]}-{chars[4:]}"


def normalize_link_code(typed: str) -> str:
    """El código como se guarda su hash: sin espacios ni guiones y en
    mayúsculas, así `abcd-efgh` y `ABCD EFGH` son el mismo código."""
    return "".join(char for char in typed.upper() if char not in " -")
