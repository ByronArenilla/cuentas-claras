"""Configuración de la API, leída del entorno una sola vez al importar (RF-33).

Si falta una variable obligatoria el proceso no arranca: es preferible un
error claro al inicio que un valor por defecto silencioso que falle después.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REQUIRED_VARIABLES = ("DATABASE_URL", "TZ", "WEB_BASE_URL", "BOT_API_KEY")

# Una llave más corta se podría adivinar (plan 005).
MIN_BOT_API_KEY_LENGTH = 32


class MissingSettingError(RuntimeError):
    """Falta al menos una variable de entorno obligatoria."""


class InvalidSettingError(RuntimeError):
    """Una variable de entorno tiene un valor que la API no puede usar."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    tz: str
    # URL pública de la web; con ella se arma el enlace de invitación (RF-15).
    web_base_url: str
    # Secreto compartido con el bot (spec 005). `repr=False`: si alguien
    # imprime la configuración, la llave no aparece (principio 12).
    bot_api_key: str = field(repr=False)


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Construye la configuración o falla nombrando cada variable que falta.

    Un valor vacío cuenta como ausente: `DATABASE_URL=` en un `.env` es un
    olvido, no una configuración válida.
    """
    missing = [name for name in REQUIRED_VARIABLES if not environ.get(name, "").strip()]
    if missing:
        names = ", ".join(missing)
        raise MissingSettingError(
            f"Faltan variables de entorno obligatorias: {names}. "
            "Defínelas en .env (copia .env.example) o en el entorno."
        )
    # Una zona mal escrita dejaría arrancar la API y cada cálculo de "hoy"
    # fallaría después (plan 003). `ValueError` cubre nombres con forma de
    # ruta, como `../Marte`, que `ZoneInfo` rechaza antes de buscarlos.
    try:
        ZoneInfo(environ["TZ"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidSettingError(
            f"TZ no es una zona horaria válida: {environ['TZ']!r}. "
            "Usa un nombre de la base de datos IANA, por ejemplo America/Bogota."
        ) from error
    # El mensaje nombra la variable pero nunca muestra su valor.
    if len(environ["BOT_API_KEY"].strip()) < MIN_BOT_API_KEY_LENGTH:
        raise InvalidSettingError(
            f"BOT_API_KEY debe tener al menos {MIN_BOT_API_KEY_LENGTH} caracteres. "
            'Genera una con: python3 -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )
    return Settings(
        database_url=environ["DATABASE_URL"],
        tz=environ["TZ"],
        # Sin la `/` final: el enlace se arma como `<web_base_url>/unirse/...`
        # y no debe salir con `//unirse`.
        web_base_url=environ["WEB_BASE_URL"].strip().rstrip("/"),
        bot_api_key=environ["BOT_API_KEY"].strip(),
    )


settings = load_settings(os.environ)
