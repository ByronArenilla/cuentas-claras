"""Plan de cuotas de una compra con tarjeta, sin base de datos ni HTTP
(spec 009, criterios 2 y 3; principio 10)."""

import pytest

from app.installments import (
    Installment,
    PrepaymentPlan,
    build_schedule,
    interest,
    prepayment_limit,
    split_capital,
)

# La "Compra TV" de la spec: 1.200.000 a 6 cuotas con tasa 1,90 % mensual.
TV_AMOUNT = 1_200_000
TV_RATE_BP = 190


def tv_schedule(*prepayments: PrepaymentPlan) -> list[Installment]:
    return build_schedule(TV_AMOUNT, 6, TV_RATE_BP, "2026-12", prepayments)


def amounts(schedule: list[Installment]) -> list[tuple[str, int]]:
    return [(row.period, row.amount) for row in schedule]


def test_tv_schedule_has_fixed_capital_and_interest_on_balance() -> None:
    schedule = tv_schedule()

    assert [row.capital for row in schedule] == [200_000] * 6
    assert [row.interest for row in schedule] == [
        22_800,
        19_000,
        15_200,
        11_400,
        7_600,
        3_800,
    ]
    assert [row.period for row in schedule] == [
        "2026-12",
        "2027-01",
        "2027-02",
        "2027-03",
        "2027-04",
        "2027-05",
    ]
    assert [row.number for row in schedule] == [1, 2, 3, 4, 5, 6]
    assert all(row.count == 6 for row in schedule)
    assert schedule[0].amount == 222_800
    assert [row.balance_after for row in schedule] == [
        1_000_000,
        800_000,
        600_000,
        400_000,
        200_000,
        0,
    ]


def test_capital_remainder_goes_one_peso_to_each_first_installment() -> None:
    assert split_capital(1_000_000, 3) == [333_334, 333_333, 333_333]
    assert split_capital(10, 4) == [3, 3, 2, 2]


@pytest.mark.parametrize("amount", [1, 7, 999_999, 1_000_000, 1_000_000_000_000])
@pytest.mark.parametrize("count", [1, 2, 3, 7, 12, 48])
def test_capital_always_adds_up_to_the_amount(amount: int, count: int) -> None:
    schedule = build_schedule(amount, count, 189, "2026-12", [])

    assert sum(row.capital for row in schedule) == amount
    assert schedule[-1].balance_after == 0


def test_single_installment_has_no_interest() -> None:
    (only,) = build_schedule(200_000, 1, TV_RATE_BP, "2026-12", [])

    assert only.interest == 0
    assert only.amount == 200_000


def test_card_without_rate_has_no_interest() -> None:
    schedule = build_schedule(TV_AMOUNT, 6, None, "2026-12", [])

    assert all(row.interest == 0 for row in schedule)


def test_interest_rounds_half_peso_up() -> None:
    # 50 × 1 % = 0,5 → 1; 49 × 1 % = 0,49 → 0.
    assert interest(50, 100) == 1
    assert interest(49, 100) == 0
    assert interest(1_200_000, 190) == 22_800
    assert interest(1_000, None) == 0


def test_prepayment_reducing_term_keeps_capital_and_ends_earlier() -> None:
    schedule = tv_schedule(PrepaymentPlan("2026-12", 400_000, "term"))

    assert amounts(schedule) == [
        ("2026-12", 222_800),
        ("2027-01", 211_400),
        ("2027-02", 207_600),
        ("2027-03", 203_800),
    ]
    assert all(row.count == 4 for row in schedule)
    assert schedule[0].balance_after == 600_000


def test_prepayment_reducing_installment_keeps_term_with_lower_installments() -> None:
    schedule = tv_schedule(PrepaymentPlan("2026-12", 400_000, "installment"))

    assert amounts(schedule) == [
        ("2026-12", 222_800),
        ("2027-01", 131_400),
        ("2027-02", 129_120),
        ("2027-03", 126_840),
        ("2027-04", 124_560),
        ("2027-05", 122_280),
    ]
    assert all(row.count == 6 for row in schedule)


def test_prepayment_for_the_whole_balance_cancels_the_purchase() -> None:
    schedule = tv_schedule(PrepaymentPlan("2026-12", 1_000_000, "term"))

    assert amounts(schedule) == [("2026-12", 222_800)]
    assert schedule[0].count == 1
    assert schedule[0].balance_after == 0


def test_term_reduction_leaves_the_rest_in_the_last_installment() -> None:
    # Tras la cuota 1, el saldo es 1.000.000; con un abono de 450.000 quedan
    # 550.000: dos cuotas de 200.000 y una última de 150.000.
    schedule = tv_schedule(PrepaymentPlan("2026-12", 450_000, "term"))

    assert [row.capital for row in schedule] == [200_000, 200_000, 200_000, 150_000]


def test_several_prepayments_apply_in_month_order() -> None:
    schedule = tv_schedule(
        PrepaymentPlan("2027-02", 200_000, "term"),
        PrepaymentPlan("2026-12", 400_000, "installment"),
    )

    # Diciembre: saldo 600.000 en 5 cuotas de 120.000. Febrero: tras la
    # cuota 3 quedan 360.000, menos 200.000 = 160.000 en cuotas de 120.000.
    assert [row.capital for row in schedule] == [
        200_000,
        120_000,
        120_000,
        120_000,
        40_000,
    ]
    assert sum(row.capital for row in schedule) + 600_000 == TV_AMOUNT


def test_prepayment_limit_is_the_balance_after_that_installment() -> None:
    schedule = tv_schedule()

    assert prepayment_limit(schedule, "2026-12") == 1_000_000
    assert prepayment_limit(schedule, "2027-04") == 200_000
    # Antes de la primera cuota no hay cuota; tras la última no queda saldo.
    assert prepayment_limit(schedule, "2026-11") is None
    assert prepayment_limit(schedule, "2027-05") is None


def test_prepayment_above_the_balance_is_a_bug() -> None:
    with pytest.raises(ValueError):
        tv_schedule(PrepaymentPlan("2026-12", 1_000_001, "term"))


def test_prepayment_in_a_month_without_installment_is_a_bug() -> None:
    with pytest.raises(ValueError):
        tv_schedule(PrepaymentPlan("2027-05", 1, "term"))
