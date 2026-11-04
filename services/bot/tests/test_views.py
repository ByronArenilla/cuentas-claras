"""Textos de /resumen, /ultimos y /deshacer, sin red (spec 006)."""

from datetime import date

from bot.views import expense_text, recent_text, remaining_text, summary_text

TODAY = date(2026, 11, 4)


def row(category_id: int, name: str, budget: int | None, spent: int) -> dict:
    remaining = None if budget is None else budget - spent
    return {
        "category_id": category_id,
        "name": name,
        "budget": budget,
        "spent": spent,
        "remaining": remaining,
    }


def summary(rows: list[dict], period: str = "2026-11") -> dict:
    budgets = [r["budget"] for r in rows if r["budget"] is not None]
    budget = sum(budgets) if budgets else None
    spent = sum(r["spent"] for r in rows)
    remaining = None if budget is None else budget - spent
    return {
        "period": period,
        "categories": rows,
        "total": {"budget": budget, "spent": spent, "remaining": remaining},
    }


def test_remaining_text() -> None:
    assert remaining_text(50_000) == "Te quedan $ 50.000."
    assert remaining_text(0) == "Te quedan $ 0."
    assert remaining_text(-12_000) == "Te pasaste por $ 12.000."


def test_summary_text_lists_only_categories_with_data() -> None:
    # Criterio 2 (RF-6, RF-7, decisión 3).
    text = summary_text(
        "Casa",
        summary(
            [
                row(1, "Hogar", None, 0),  # Sin nada: no aparece.
                row(2, "Comida", 400_000, 412_000),
                row(3, "Transporte", None, 38_000),
                row(4, "Ocio", 100_000, 0),
            ]
        ),
    )

    lines = text.split("\n")
    assert lines[0] == "Casa · noviembre de 2026"
    assert lines[1] == "Gastado: $ 450.000 de $ 500.000. Te quedan $ 50.000."
    assert lines[2] == ""
    assert lines[3:] == [
        "Comida: $ 412.000 de $ 400.000. Te pasaste por $ 12.000.",
        "Transporte: $ 38.000. Sin presupuesto.",
        "Ocio: $ 0 de $ 100.000. Te quedan $ 100.000.",
    ]
    assert "Hogar" not in text


def test_summary_text_without_budgets_only_shows_spent() -> None:
    text = summary_text("Personal", summary([row(1, "Comida", None, 20_000)]))

    assert text.split("\n")[1] == "Gastado: $ 20.000. Sin presupuesto."


def test_summary_text_of_an_empty_month_says_so() -> None:
    text = summary_text("Personal", summary([row(1, "Hogar", None, 0)], "2026-01"))

    assert text.split("\n")[0] == "Personal · enero de 2026"
    assert "No hay gastos ni presupuesto este mes." in text


EXPENSE = {
    "id": 9,
    "amount": 20_000,
    "payment_type": "debit",
    "category_id": 2,
    "spent_on": "2026-11-03",
    "description": "Mercado",
    "created_by": 1,
    "created_at": "2026-11-04T15:00:00Z",
}


def test_expense_text_with_and_without_description() -> None:
    assert expense_text(EXPENSE, "Comida", TODAY) == (
        "$ 20.000 · Comida · ayer, 3 de noviembre · Mercado"
    )
    without = {**EXPENSE, "description": None}
    assert expense_text(without, "Comida", TODAY) == (
        "$ 20.000 · Comida · ayer, 3 de noviembre"
    )


def test_recent_text_marks_expenses_of_other_members() -> None:
    # RF-9, RF-10, decisión 7: sin decir quién.
    other = {**EXPENSE, "id": 10, "amount": 5_000, "created_by": 2, "description": None}
    text = recent_text("Casa", [other, EXPENSE], {2: "Comida"}, my_id=1, today=TODAY)

    assert text.split("\n") == [
        "Últimos gastos registrados en Casa:",
        "",
        "1. $ 5.000 · Comida · ayer, 3 de noviembre · de otro miembro",
        "2. $ 20.000 · Comida · ayer, 3 de noviembre · Mercado",
    ]


def test_recent_text_of_an_empty_space_says_so() -> None:
    # RF-11.
    assert recent_text("Casa", [], {}, my_id=1, today=TODAY) == (
        "Todavía no hay gastos registrados en Casa."
    )


def test_an_unknown_category_still_shows_the_expense() -> None:
    text = recent_text("Casa", [EXPENSE], {}, my_id=1, today=TODAY)

    assert "Categoría desconocida" in text
