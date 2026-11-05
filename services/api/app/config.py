"""Configuración de la API, leída del entorno una sola vez al importar (RF-33).

Si falta una variable obligatoria el proceso no arranca: es preferible un
error claro al inicio que un valor por defecto silencioso que falle después.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Solo se leen estas variables: las que sobran, como `BOT_API_KEY` en un
# `.env` de antes de la spec 007, se ignoran sin error.
REQUIRED_VARIABLES = ("DATABASE_URL", "TZ", "WEB_BASE_URL")


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
    return Settings(
        database_url=environ["DATABASE_URL"],
        tz=environ["TZ"],
        # Sin la `/` final: el enlace se arma como `<web_base_url>/unirse/...`
        # y no debe salir con `//unirse`.
        web_base_url=environ["WEB_BASE_URL"].strip().rstrip("/"),
    )


settings = load_settings(os.environ)
