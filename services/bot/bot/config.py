"""Configuración del bot, leída del entorno al arrancar (principio 11).

Si falta una variable el bot no arranca y las nombra todas, como la API
(RF-33 de la 001). A diferencia de la API, no se lee al importar: así los
tests usan los módulos del bot sin definir el entorno.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REQUIRED_VARIABLES = ("TELEGRAM_BOT_TOKEN", "API_URL", "BOT_API_KEY", "TZ")


class MissingSettingError(RuntimeError):
    """Falta al menos una variable de entorno obligatoria."""


class InvalidSettingError(RuntimeError):
    """Una variable de entorno tiene un valor que el bot no puede usar."""


@dataclass(frozen=True)
class Settings:
    # `repr=False` en los secretos: imprimir la configuración no los muestra
    # (principio 12).
    telegram_bot_token: str = field(repr=False)
    api_url: str
    bot_api_key: str = field(repr=False)
    # Zona en la que se calculan "hoy" y "ayer" (principio 7).
    tz: str


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Construye la configuración o falla nombrando cada variable que falta."""
    missing = [name for name in REQUIRED_VARIABLES if not environ.get(name, "").strip()]
    if missing:
        raise MissingSettingError(
            f"Faltan variables de entorno obligatorias: {', '.join(missing)}. "
            "Defínelas en .env (copia .env.example) o en el entorno."
        )
    try:
        ZoneInfo(environ["TZ"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidSettingError(
            f"TZ no es una zona horaria válida: {environ['TZ']!r}. "
            "Usa un nombre de la base de datos IANA, por ejemplo America/Bogota."
        ) from error
    return Settings(
        telegram_bot_token=environ["TELEGRAM_BOT_TOKEN"].strip(),
        api_url=environ["API_URL"].strip().rstrip("/"),
        bot_api_key=environ["BOT_API_KEY"].strip(),
        tz=environ["TZ"],
    )
