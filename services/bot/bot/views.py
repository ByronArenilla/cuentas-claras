"""Textos de /resumen, /ultimos y /deshacer (spec 006).

Funciones puras: reciben lo que devuelve la API y arman el mensaje, sin red
ni Telegram (principio 10).
"""

from datetime import date

from bot.parsing import format_day, format_money, month_name

UNKNOWN_CATEGORY = "Categoría desconocida"


def remaining_text(remaining: int) -> str:
    """Lo que queda, o cuánto se pasó si es negativo."""
    if remaining < 0:
        return f"Te pasaste por {format_money(-remaining)}."
    return f"Te quedan {format_money(remaining)}."


def period_title(period: str) -> str:
    """`2026-11` como "noviembre de 2026"."""
    return f"{month_name(int(period[5:7]))} de {period[:4]}"


def amounts_text(spent: int, budget: int | None, remaining: int | None) -> str:
    """ "$ 412.000 de $ 400.000. Te pasaste por $ 12.000." o, sin
    presupuesto, "$ 38.000. Sin presupuesto."."""
    if budget is None or remaining is None:
        return f"{format_money(spent)}. Sin presupuesto."
    return (
        f"{format_money(spent)} de {format_money(budget)}. {remaining_text(remaining)}"
    )


def summary_text(space_name: str, summary: dict) -> str:
    """El resumen del mes para el chat (RF-6, RF-7).

    Solo se listan las categorías con presupuesto o con gastos: en un chat,
    las líneas en cero son ruido (decisión 3). La API devuelve todas.
    """
    total = summary["total"]
    lines = [
        f"{space_name} · {period_title(summary['period'])}",
        f"Gastado: {amounts_text(total['spent'], total['budget'], total['remaining'])}",
        "",
    ]
    shown = [
        row
        for row in summary["categories"]
        if row["budget"] is not None or row["spent"] > 0
    ]
    if not shown:
        lines.append("No hay gastos ni presupuesto este mes.")
    for row in shown:
        amounts = amounts_text(row["spent"], row["budget"], row["remaining"])
        lines.append(f"{row['name']}: {amounts}")
    return "\n".join(lines)


def expense_text(expense: dict, category_name: str, today: date) -> str:
    """ "$ 20.000 · Comida · ayer, 3 de noviembre · Mercado"."""
    parts = [
        format_money(expense["amount"]),
        category_name,
        format_day(date.fromisoformat(expense["spent_on"]), today),
    ]
    if expense.get("description"):
        parts.append(expense["description"])
    return " · ".join(parts)


def recent_text(
    space_name: str,
    expenses: list[dict],
    category_names: dict[int, str],
    my_id: int,
    today: date,
) -> str:
    """La lista de /ultimos (RF-9 a RF-11). Un gasto de otro miembro se
    marca sin decir quién: la API solo da su `id` (decisión 7)."""
    if not expenses:
        return f"Todavía no hay gastos registrados en {space_name}."
    lines = [f"Últimos gastos registrados en {space_name}:", ""]
    for number, expense in enumerate(expenses, start=1):
        name = category_names.get(expense["category_id"], UNKNOWN_CATEGORY)
        text = expense_text(expense, name, today)
        if expense["created_by"] != my_id:
            text += " · de otro miembro"
        lines.append(f"{number}. {text}")
    return "\n".join(lines)
