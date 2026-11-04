from datetime import date

import pytest

from bot.parsing import format_day, format_money, month_name, parse_amount, parse_day

TODAY = date(2026, 11, 4)


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("20000", 20_000),
        ("20.000", 20_000),
        ("$20.000", 20_000),
        ("$ 20.000", 20_000),
        ("  20000  ", 20_000),
        ("1.000.000", 1_000_000),
        ("1.000.000.000.000", 1_000_000_000_000),
    ],
)
def test_amounts_in_whole_pesos_are_read(text: str, amount: int) -> None:
    # Decisión 3.
    assert parse_amount(text) == amount


@pytest.mark.parametrize(
    "text",
    [
        "20,5",
        "20,000",  # En Colombia la coma es decimal: ambiguo (decisión 3).
        "20.000,50",
        "20000.5",
        "2.00",
        "20.00.000",
        "0",
        "-5",
        "abc",
        "",
        "20 mil",
        "1.000.000.000.001",  # Más de un billón (RF-3 de la 003).
        "２００００",  # Dígitos que no son ASCII.
    ],
)
def test_other_amounts_are_rejected(text: str) -> None:
    # Criterio 5 (RF-13): nunca se redondea ni se adivina.
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("30/10", date(2026, 10, 30)),
        ("3/1", date(2026, 1, 3)),
        ("30/10/2026", date(2026, 10, 30)),
        ("30-10-2026", date(2026, 10, 30)),
        (" 01/09/2025 ", date(2025, 9, 1)),
    ],
)
def test_days_are_read_with_the_current_year_by_default(text: str, day: date) -> None:
    # Decisión 5.
    assert parse_day(text, TODAY) == day


@pytest.mark.parametrize(
    "text", ["31/02", "2026-10-30", "ayer", "30/13", "30/10/26", "", "30.10"]
)
def test_other_days_are_rejected(text: str) -> None:
    assert parse_day(text, TODAY) is None


@pytest.mark.parametrize(
    ("amount", "text"),
    [(0, "$ 0"), (500, "$ 500"), (20_000, "$ 20.000"), (1_240_000, "$ 1.240.000")],
)
def test_money_uses_dots_for_thousands(amount: int, text: str) -> None:
    # RF-28.
    assert format_money(amount) == text


@pytest.mark.parametrize(
    ("day", "text"),
    [
        (TODAY, "hoy, 4 de noviembre"),
        (date(2026, 11, 3), "ayer, 3 de noviembre"),
        (date(2026, 10, 1), "1 de octubre"),
        (date(2025, 12, 24), "24 de diciembre de 2025"),
    ],
)
def test_days_are_written_in_spanish(day: date, text: str) -> None:
    assert format_day(day, TODAY) == text


def test_month_names_are_in_spanish() -> None:
    assert [month_name(m) for m in (1, 3, 12)] == ["enero", "marzo", "diciembre"]
