"""Reloj y periodos de la API (principio 7).

Los instantes van en UTC; "hoy" y el mes de un gasto se calculan en la zona
configurada en `TZ`. Los tests fijan el reloj sustituyendo `now` con
`monkeypatch`, así que el resto del código debe llamarlo como `dates.now()`
o a través de `today()`, nunca importarlo con `from app.dates import now`.
"""

import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import settings

# Solo dígitos ASCII: `\d` también aceptaría dígitos de otros alfabetos.
PERIOD_PATTERN = re.compile(r"([0-9]{4})-([0-9]{2})")


def now() -> datetime:
    """El instante actual en UTC. Es el único punto que los tests sustituyen."""
    return datetime.now(UTC)


def today() -> date:
    """El día de hoy en `TZ`, no en la zona del proceso como `date.today()`."""
    return now().astimezone(ZoneInfo(settings.tz)).date()


def period_of(day: date) -> str:
    """El periodo `YYYY-MM` al que pertenece un día."""
    return f"{day.year:04d}-{day.month:02d}"


def period_bounds(period: str) -> tuple[date, date]:
    """Primer día del periodo y primer día del periodo siguiente.

    Se filtra con `start <= spent_on < end`, así que no importa cuántos días
    tenga el mes. Lanza `ValueError` si `period` no es un mes `YYYY-MM`.
    """
    match = PERIOD_PATTERN.fullmatch(period)
    if match is None or not 1 <= int(match[2]) <= 12:
        raise ValueError(f"Periodo inválido: {period!r}. Usa el formato AAAA-MM.")
    year, month = int(match[1]), int(match[2])
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end
