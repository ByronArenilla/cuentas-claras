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
