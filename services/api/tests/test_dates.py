from datetime import UTC, date, datetime

import pytest

from app import dates
from app.config import settings


@pytest.mark.parametrize(
    ("period", "start", "end"),
    [
        ("2026-02", date(2026, 2, 1), date(2026, 3, 1)),  # 28 días
        ("2028-02", date(2028, 2, 1), date(2028, 3, 1)),  # 29 días: bisiesto
        ("2026-04", date(2026, 4, 1), date(2026, 5, 1)),  # 30 días
        ("2026-10", date(2026, 10, 1), date(2026, 11, 1)),  # 31 días
        ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),  # cambia el año
    ],
)
def test_period_bounds_go_from_first_day_to_first_day_of_next_month(
    period: str, start: date, end: date
) -> None:
    assert dates.period_bounds(period) == (start, end)


@pytest.mark.parametrize(
    "period", ["2026-13", "2026-00", "2026-1", "26-10", "2026-10-01", "octubre"]
)
def test_period_bounds_rejects_invalid_period(period: str) -> None:
    with pytest.raises(ValueError):
        dates.period_bounds(period)


def test_period_of_day() -> None:
    assert dates.period_of(date(2026, 10, 31)) == "2026-10"


def test_today_is_computed_in_configured_time_zone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La 01:00 UTC del 1 de noviembre aún es 31 de octubre en Bogotá (UTC-5).
    assert settings.tz == "America/Bogota"
    monkeypatch.setattr(dates, "now", lambda: datetime(2026, 11, 1, 1, 0, tzinfo=UTC))

    assert dates.today() == date(2026, 10, 31)


def test_now_is_in_utc() -> None:
    assert dates.now().utcoffset() == UTC.utcoffset(None)


@pytest.mark.parametrize(
    ("period", "previous"),
    [("2026-11", "2026-10"), ("2026-01", "2025-12"), ("0001-02", "0001-01")],
)
def test_previous_period(period: str, previous: str) -> None:
    # Spec 008: la copia del plan toma el mes inmediatamente anterior.
    assert dates.previous_period(period) == previous


def test_previous_period_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        dates.previous_period("2026-13")


@pytest.mark.parametrize(
    ("period", "months", "shifted"),
    [
        ("2026-11", 2, "2027-01"),
        ("2026-01", -1, "2025-12"),
        ("2026-11", 0, "2026-11"),
        ("2026-12", -47, "2023-01"),
        ("2026-05", 12, "2027-05"),
    ],
)
def test_shift_period(period: str, months: int, shifted: str) -> None:
    # Spec 009: la cuota k cae k - 1 meses después del mes de pago (RF-13).
    assert dates.shift_period(period, months) == shifted


@pytest.mark.parametrize(
    ("spent_on", "cutoff_day", "due_day", "period"),
    [
        # Criterio 1 de la 009. Una compra el día de corte entra en ese corte.
        (date(2026, 11, 25), 25, 10, "2026-12"),
        (date(2026, 11, 26), 25, 10, "2027-01"),
        # Corte 15 y pago 30: se paga el mismo mes de la compra.
        (date(2026, 11, 10), 15, 30, "2026-11"),
        # Febrero no tiene día 30: el pago es el último día, el 28.
        (date(2027, 2, 10), 15, 30, "2027-02"),
        # Mismo día de corte y de pago: el pago es el del mes siguiente.
        (date(2026, 11, 10), 10, 10, "2026-12"),
        # Abril no tiene día 31: el corte es el 30.
        (date(2026, 4, 30), 31, 5, "2026-05"),
        # Diciembre pasa al año siguiente.
        (date(2026, 12, 26), 25, 10, "2027-02"),
    ],
)
def test_first_due_period(
    spent_on: date, cutoff_day: int, due_day: int, period: str
) -> None:
    assert dates.first_due_period(spent_on, cutoff_day, due_day) == period
