"""Leer y escribir montos y fechas como los escribe una persona (spec 005).

Funciones puras, sin Telegram ni red. Solo traducen el formato: si un gasto
es válido lo decide la API (principio 10).
"""

import re
from datetime import date, timedelta

# El mismo tope que la API (decisión 7 de la 003): avisar aquí ahorra un
# paso, pero quien decide sigue siendo la API.
MAX_AMOUNT = 1_000_000_000_000

# Pesos enteros, con `$` opcional y puntos de miles solo en grupos de tres
# (decisión 3). `[0-9]` y no `\d`: `\d` también acepta dígitos de otros
# alfabetos, como `２`. Sin coma: en Colombia es el separador decimal.
AMOUNT_PATTERN = re.compile(r"\$?\s*([0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)")

# `DD/MM` o `DD/MM/AAAA`, también con guiones (decisión 5).
DAY_PATTERN = re.compile(r"([0-9]{1,2})[/-]([0-9]{1,2})(?:[/-]([0-9]{4}))?")

MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def parse_amount(text: str) -> int | None:
    """Monto en pesos enteros, o None si no tiene un formato admitido o no
    está entre 1 y un billón (RF-13). Nunca redondea."""
    match = AMOUNT_PATTERN.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match[1].replace(".", ""))
    return amount if 1 <= amount <= MAX_AMOUNT else None


def parse_day(text: str, today: date) -> date | None:
    """Día escrito como `DD/MM` (año de `today`) o `DD/MM/AAAA`, o None si
    no es un día real. Que no sea futuro lo comprueba quien llama (RF-17)."""
    match = DAY_PATTERN.fullmatch(text.strip())
    if match is None:
        return None
    day, month = int(match[1]), int(match[2])
    year = int(match[3]) if match[3] else today.year
    try:
        return date(year, month, day)
    except ValueError:
        return None  # Como el 31 de febrero.


def format_money(amount: int) -> str:
    """Monto en pesos con puntos de miles: `$ 1.240.000` (RF-28)."""
    return "$ " + f"{amount:,}".replace(",", ".")


def month_name(month: int) -> str:
    """Nombre del mes en español, en minúsculas."""
    return MONTHS[month - 1]


def format_day(day: date, today: date) -> str:
    """El día como se dice: "hoy, 4 de noviembre", "ayer, ...", "1 de
    octubre" o, en otro año, "24 de diciembre de 2025"."""
    text = f"{day.day} de {month_name(day.month)}"
    if day == today:
        return f"hoy, {text}"
    if day == today - timedelta(days=1):
        return f"ayer, {text}"
    return text if day.year == today.year else f"{text} de {day.year}"
