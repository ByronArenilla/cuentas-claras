"""La conversación del bot, sin Telegram ni red (spec 005; principio 10)."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from bot.api import ApiRejected, ApiUnavailable
from bot.conversation import Command, Conversations, Press, Reply, Text
from tests.fakes import EMAIL, VALID_CODE, FakeApi

CHAT = 42
# 2026-10-31 a las 20:00 en Bogotá (UTC-5): en UTC ya es 1 de noviembre.
NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)


class Clock:
    """Reloj que el test puede adelantar."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make(api: FakeApi, clock: Clock | None = None) -> Conversations:
    return Conversations(api, "America/Bogota", clock or Clock())


def send(bot: Conversations, event: object, chat_id: int = CHAT) -> list[Reply]:
    return asyncio.run(bot.handle(chat_id, event))


def text_of(replies: list[Reply]) -> str:
    return "\n".join(reply.text for reply in replies)


# --- Ayuda y vinculación (T8) ---


@pytest.mark.parametrize("name", ["start", "ayuda"])
def test_help_in_an_unlinked_chat_explains_how_to_link(name: str) -> None:
    # RF-27.
    replies = send(make(FakeApi(linked=False)), Command(name))

    assert "/gasto" in text_of(replies)
    assert "/vincular" in text_of(replies)
    assert "no está vinculado" in text_of(replies)


def test_help_in_a_linked_chat_does_not_ask_to_link() -> None:
    replies = send(make(FakeApi()), Command("start"))

    assert "/gasto" in text_of(replies)
    assert "no está vinculado" not in text_of(replies)


def test_linking_with_a_valid_code_names_the_user() -> None:
    # RF-3.
    api = FakeApi(linked=False)

    replies = send(make(api), Command("vincular", VALID_CODE))

    assert EMAIL in text_of(replies)
    assert api.linked


def test_linking_with_an_invalid_code_says_so() -> None:
    # RF-4.
    api = FakeApi(linked=False)

    replies = send(make(api), Command("vincular", "ZZZZ-ZZZZ"))

    assert "no es válido" in text_of(replies)
    assert not api.linked


def test_linking_without_a_code_explains_the_usage() -> None:
    api = FakeApi(linked=False)

    replies = send(make(api), Command("vincular"))

    assert "/vincular ABCD-EFGH" in text_of(replies)
    assert api.calls == []


def test_unlinking_confirms_it() -> None:
    # RF-6.
    api = FakeApi()

    replies = send(make(api), Command("desvincular"))

    assert "desvinculé" in text_of(replies)
    assert not api.linked


@pytest.mark.parametrize(
    "event", [Command("gasto"), Command("gasto", "20000"), Text("20.000")]
)
def test_an_unlinked_chat_gets_instructions_and_no_data(event: object) -> None:
    # Criterio 9 (RF-7): ninguna ruta de datos responde nada en su nombre.
    api = FakeApi(linked=False)

    replies = send(make(api), event)

    assert "no está vinculado" in text_of(replies)
    assert "/vincular" in text_of(replies)
    assert "categories" not in api.calls
    assert "create_expense" not in api.calls
    assert api.expenses == []


def test_text_that_is_not_understood_gets_the_help() -> None:
    replies = send(make(FakeApi()), Text("hola, ¿qué tal?"))

    assert "/gasto" in text_of(replies)


def test_an_unavailable_api_is_explained() -> None:
    class DownApi(FakeApi):
        async def link_chat(self, chat_id: int, code: str) -> str:
            raise ApiUnavailable("caída")

    replies = send(make(DownApi(linked=False)), Command("vincular", VALID_CODE))

    assert "No pude hablar con gastito" in text_of(replies)


# --- Registrar un gasto (T9) ---

TWO_SPACES = [{"id": 1, "name": "Personal"}, {"id": 2, "name": "Casa"}]


def labels(reply: Reply) -> list[str]:
    return [button.label for row in reply.buttons for button in row]


def press(bot: Conversations, replies: list[Reply], label: str) -> list[Reply]:
    """Toca el botón `label` del último mensaje que tenía botones."""
    with_buttons = [reply for reply in replies if reply.buttons]
    for row in with_buttons[-1].buttons:
        for button in row:
            if button.label == label:
                return send(bot, Press(button.data))
    raise AssertionError(f"no hay botón {label!r} en {labels(with_buttons[-1])}")


def summary_with(budget: int | None, spent: int, remaining: int | None) -> dict:
    return {
        "period": "2026-10",
        "categories": [
            {
                "category_id": 1,
                "name": "Hogar",
                "budget": None,
                "spent": 0,
                "remaining": None,
            },
            {
                "category_id": 2,
                "name": "Comida",
                "budget": budget,
                "spent": spent,
                "remaining": remaining,
            },
        ],
        "total": {"budget": budget, "spent": spent, "remaining": remaining},
    }


def up_to_confirmation(
    bot: Conversations, day: str = "Hoy", description: str | None = None
) -> list[Reply]:
    """Recorre un gasto de $ 20.000 en Comida, Débito, en un solo espacio."""
    replies = send(bot, Text("20000"))
    replies = press(bot, replies, "Comida")
    replies = press(bot, replies, "Débito")
    replies = press(bot, replies, day)
    if description is None:
        return press(bot, replies, "Omitir")
    return send(bot, Text(description))


def test_a_full_expense_with_two_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    # Criterio 4 (RF-12 a RF-21).
    api = FakeApi(spaces=TWO_SPACES)
    api.summary_reply = summary_with(400_000, 412_000, -12_000)
    bot = make(api)

    replies = send(bot, Command("gasto"))
    assert "¿Cuánto gastaste?" in text_of(replies)
    replies = send(bot, Text("$20.000"))
    assert labels(replies[-1]) == ["Personal", "Casa"]
    replies = press(bot, replies, "Casa")
    assert labels(replies[-1]) == ["Hogar", "Comida", "Transporte"]
    replies = press(bot, replies, "Comida")
    assert labels(replies[-1]) == ["Débito", "Crédito"]
    replies = press(bot, replies, "Débito")
    assert labels(replies[-1]) == ["Hoy", "Ayer", "Otra fecha"]
    replies = press(bot, replies, "Ayer")
    assert labels(replies[-1]) == ["Omitir"]
    replies = send(bot, Text("  Mercado  "))

    # RF-19: el borrador completo antes de registrar.
    confirmation = text_of(replies)
    for expected in (
        "$ 20.000",
        "Débito",
        "Comida",
        "Casa",
        "ayer, 30 de octubre",
        "Mercado",
    ):
        assert expected in confirmation
    assert labels(replies[-1]) == ["Confirmar", "Cancelar"]
    assert api.expenses == []

    replies = press(bot, replies, "Confirmar")

    assert api.expenses == [
        (
            2,
            {
                "amount": 20_000,
                "payment_type": "debit",
                "category_id": 2,
                "spent_on": "2026-10-30",
                "description": "Mercado",
            },
        )
    ]
    answer = text_of(replies)
    assert "Gasto registrado" in answer
    # RF-21: la línea del presupuesto del mes del gasto.
    assert "Comida: llevas $ 412.000 de $ 400.000 en octubre" in answer
    assert "Te pasaste por $ 12.000" in answer


def test_with_a_single_space_the_space_is_not_asked() -> None:
    # Criterio 6 (RF-14). La confirmación muestra el espacio igualmente.
    api = FakeApi()
    bot = make(api)

    replies = send(bot, Command("gasto", "20000"))

    assert labels(replies[-1]) == ["Hogar", "Comida", "Transporte"]
    replies = up_to_confirmation(make(api))
    assert "Personal" in text_of(replies)


@pytest.mark.parametrize(
    "event", [Command("gasto", "20.000"), Command("gasto", "$ 20000"), Text("20.000")]
)
def test_the_amount_can_come_with_the_command_or_alone(event: object) -> None:
    # RF-12, decisión 3.
    replies = send(make(FakeApi()), event)

    assert labels(replies[-1]) == ["Hogar", "Comida", "Transporte"]


@pytest.mark.parametrize(
    "typed", ["20,5", "20.000,50", "0", "-5", "abc", "1.000.000.000.001"]
)
def test_an_invalid_amount_is_asked_again(typed: str) -> None:
    # Criterio 5 en la conversación (RF-13).
    bot = make(FakeApi())
    send(bot, Command("gasto"))

    replies = send(bot, Text(typed))

    assert "No entendí el monto" in text_of(replies)
    assert replies[-1].buttons == ()
    # Sigue esperando el monto.
    assert labels(send(bot, Text("20000"))[-1]) == ["Hogar", "Comida", "Transporte"]


def test_an_invalid_amount_with_the_command_is_asked_again() -> None:
    replies = send(make(FakeApi()), Command("gasto", "20,5"))

    assert "No entendí el monto" in text_of(replies)


def test_yesterday_and_today_are_computed_in_tz() -> None:
    # Criterio 7 (RF-17, principio 7): en Bogotá todavía es 31 de octubre.
    api = FakeApi()
    bot = make(api)
    press(bot, up_to_confirmation(bot, day="Ayer"), "Confirmar")
    press(bot, up_to_confirmation(bot, day="Hoy"), "Confirmar")

    yesterday, today = (body for _, body in api.expenses)
    assert yesterday["spent_on"] == "2026-10-30"
    # "Hoy" no envía la fecha: la API usa su propio hoy (plan 005).
    assert "spent_on" not in today


def test_another_day_is_typed_and_cannot_be_in_the_future() -> None:
    # Criterio 7 (RF-17).
    api = FakeApi()
    bot = make(api)
    replies = send(bot, Text("20000"))
    replies = press(bot, replies, "Comida")
    replies = press(bot, replies, "Débito")
    replies = press(bot, replies, "Otra fecha")
    assert "DD/MM" in text_of(replies)

    assert "posterior a hoy" in text_of(send(bot, Text("1/11")))
    assert "No entendí la fecha" in text_of(send(bot, Text("31/02")))
    replies = send(bot, Text("15/10"))
    replies = press(bot, replies, "Omitir")
    assert "15 de octubre" in text_of(replies)
    press(bot, replies, "Confirmar")

    assert api.expenses[0][1]["spent_on"] == "2026-10-15"


def test_skipping_the_description_sends_none() -> None:
    api = FakeApi()
    bot = make(api)

    press(bot, up_to_confirmation(bot), "Confirmar")

    assert "description" not in api.expenses[0][1]


def test_a_description_over_200_characters_is_asked_again() -> None:
    # RF-18.
    bot = make(FakeApi())
    replies = send(bot, Text("20000"))
    replies = press(bot, replies, "Comida")
    replies = press(bot, replies, "Débito")
    press(bot, replies, "Hoy")

    replies = send(bot, Text("x" * 201))

    assert "200 caracteres" in text_of(replies)
    assert labels(replies[-1]) == ["Omitir"]
    assert "x" * 200 in text_of(send(bot, Text("x" * 200)))


def test_pressing_confirm_twice_registers_one_expense() -> None:
    # Criterio 8 (RF-20).
    api = FakeApi()
    bot = make(api)
    replies = up_to_confirmation(bot)

    press(bot, replies, "Confirmar")
    again = press(bot, replies, "Confirmar")

    assert len(api.expenses) == 1
    assert "ya terminó" in text_of(again)


def test_a_button_after_cancelling_registers_nothing() -> None:
    # Criterio 8 (RF-22, RF-24).
    api = FakeApi()
    bot = make(api)
    replies = up_to_confirmation(bot)

    cancelled = press(bot, replies, "Cancelar")
    late = press(bot, replies, "Confirmar")

    assert "No registré nada" in text_of(cancelled)
    assert "ya terminó" in text_of(late)
    assert api.expenses == []


def test_a_draft_expires_after_ten_minutes() -> None:
    # Criterio 8 (RF-23, decisión 8).
    api = FakeApi()
    clock = Clock()
    bot = make(api, clock)
    replies = up_to_confirmation(bot)

    clock.now += timedelta(minutes=10, seconds=1)
    late = press(bot, replies, "Confirmar")

    assert "caducó" in text_of(late)
    assert api.expenses == []


def test_a_draft_used_within_ten_minutes_does_not_expire() -> None:
    api = FakeApi()
    clock = Clock()
    bot = make(api, clock)
    replies = send(bot, Text("20000"))
    clock.now += timedelta(minutes=9)
    replies = press(bot, replies, "Comida")
    clock.now += timedelta(minutes=9)

    assert labels(press(bot, replies, "Débito")[-1]) == ["Hoy", "Ayer", "Otra fecha"]


def test_a_button_from_a_previous_step_changes_nothing() -> None:
    # RF-24: tocar otra categoría cuando ya se está en el tipo de pago.
    bot = make(FakeApi())
    categories = send(bot, Text("20000"))
    payments = press(bot, categories, "Comida")

    replies = press(bot, categories, "Hogar")

    assert "ya terminó" in text_of(replies)
    # El borrador sigue en el tipo de pago, con Comida.
    replies = press(bot, payments, "Débito")
    replies = press(bot, replies, "Hoy")
    confirmation = text_of(press(bot, replies, "Omitir"))
    assert "Comida" in confirmation
    assert "Hogar" not in confirmation


@pytest.mark.parametrize(
    ("budget", "spent", "remaining", "expected"),
    [
        (
            500_000,
            412_000,
            88_000,
            "Comida: llevas $ 412.000 de $ 500.000 en octubre. Te quedan $ 88.000.",
        ),
        (
            400_000,
            412_000,
            -12_000,
            "Comida: llevas $ 412.000 de $ 400.000 en octubre. "
            "Te pasaste por $ 12.000.",
        ),
        (
            None,
            412_000,
            None,
            "Comida: llevas $ 412.000 en octubre. No tiene presupuesto.",
        ),
    ],
)
def test_the_budget_line_after_registering(
    budget: int | None, spent: int, remaining: int | None, expected: str
) -> None:
    # RF-21, decisión 4.
    api = FakeApi()
    api.summary_reply = summary_with(budget, spent, remaining)
    bot = make(api)

    replies = press(bot, up_to_confirmation(bot), "Confirmar")

    assert expected in text_of(replies)


def test_without_a_summary_the_expense_is_still_confirmed() -> None:
    # RF-21: si el resumen falla, se confirma sin la línea.
    api = FakeApi()
    api.summary_reply = ApiRejected("algo")
    bot = make(api)

    replies = press(bot, up_to_confirmation(bot), "Confirmar")

    assert "Gasto registrado" in text_of(replies)
    assert "llevas" not in text_of(replies)


def test_an_unavailable_api_keeps_the_draft_to_retry() -> None:
    # RF-25.
    api = FakeApi()
    api.create_error = ApiUnavailable("caída")
    bot = make(api)
    replies = up_to_confirmation(bot)

    failed = press(bot, replies, "Confirmar")

    assert "no responde" in text_of(failed)
    assert labels(failed[-1]) == ["Confirmar", "Cancelar"]
    api.create_error = None
    assert "Gasto registrado" in text_of(press(bot, failed, "Confirmar"))
    assert len(api.expenses) == 1


def test_a_rejected_expense_shows_the_reason_and_ends() -> None:
    # RF-25.
    api = FakeApi()
    api.create_error = ApiRejected("La categoría no existe en este espacio.")
    bot = make(api)
    replies = up_to_confirmation(bot)

    failed = press(bot, replies, "Confirmar")

    assert "La categoría no existe en este espacio." in text_of(failed)
    assert "Gasto registrado" not in text_of(failed)
    assert "ya terminó" in text_of(press(bot, replies, "Confirmar"))


@pytest.mark.parametrize("steps", [0, 1, 2, 3])
def test_cancel_command_at_any_step(steps: int) -> None:
    # RF-22.
    api = FakeApi()
    bot = make(api)
    replies = send(bot, Text("20000"))
    for label in ("Comida", "Débito", "Hoy")[:steps]:
        replies = press(bot, replies, label)

    cancelled = send(bot, Command("cancelar"))

    assert "No registré nada" in text_of(cancelled)
    assert "ya terminó" in text_of(press(bot, replies, labels(replies[-1])[0]))
    assert api.expenses == []


def test_cancel_without_a_draft_says_there_is_nothing() -> None:
    assert "No hay ningún gasto" in text_of(send(make(FakeApi()), Command("cancelar")))


def test_a_new_expense_replaces_the_current_draft() -> None:
    # RF-26.
    api = FakeApi()
    bot = make(api)
    old = send(bot, Text("20000"))

    send(bot, Command("gasto", "5000"))

    assert "ya terminó" in text_of(press(bot, old, "Comida"))


def test_text_in_a_button_step_gets_an_indication() -> None:
    # RF-26: el borrador no cambia.
    bot = make(FakeApi())
    replies = send(bot, Text("20000"))

    hint = send(bot, Text("comida"))

    assert "botones" in text_of(hint)
    assert labels(press(bot, replies, "Comida")[-1]) == ["Débito", "Crédito"]


def test_conversations_of_two_chats_do_not_mix() -> None:
    api = FakeApi()
    bot = make(api)
    send(bot, Text("20000"), chat_id=1)

    replies = send(bot, Text("comida"), chat_id=2)

    assert "/gasto" in text_of(replies)  # El chat 2 no tiene borrador.


# --- /resumen (spec 006, T4) ---


def empty_summary(period: str) -> dict:
    return {
        "period": period,
        "categories": [
            {
                "category_id": 2,
                "name": "Comida",
                "budget": 400_000,
                "spent": 0,
                "remaining": 400_000,
            }
        ],
        "total": {"budget": 400_000, "spent": 0, "remaining": 400_000},
    }


def summaries_for(space_ids: list[int], periods: list[str]) -> dict:
    return {(s, p): empty_summary(p) for s in space_ids for p in periods}


def test_summary_of_the_current_month_in_tz() -> None:
    # RF-5: con el reloj fijado, en Bogotá todavía es octubre.
    api = FakeApi()
    api.summaries = summaries_for([1], ["2026-10"])

    replies = send(make(api), Command("resumen"))

    assert api.summary_requests == [(1, "2026-10")]
    assert text_of(replies).startswith("Personal · octubre de 2026")
    assert labels(replies[-1]) == ["‹ septiembre", "noviembre ›"]


def test_with_two_spaces_summary_asks_the_space_first() -> None:
    # Criterio 4 de la 006 (decisión 5).
    api = FakeApi(spaces=TWO_SPACES)
    api.summaries = summaries_for([2], ["2026-10"])
    bot = make(api)

    replies = send(bot, Command("resumen"))

    assert labels(replies[-1]) == ["Personal", "Casa"]
    assert api.summary_requests == []
    replies = press(bot, replies, "Casa")
    assert api.summary_requests == [(2, "2026-10")]
    assert text_of(replies).startswith("Casa · octubre de 2026")


def test_summary_buttons_move_month_by_month() -> None:
    # Criterio 3 de la 006 (RF-8), también cruzando de año.
    api = FakeApi(spaces=TWO_SPACES)
    api.summaries = summaries_for([2], ["2026-10", "2026-09", "2026-11"])
    bot = make(api)
    october = press(bot, send(bot, Command("resumen")), "Casa")

    september = press(bot, october, "‹ septiembre")
    november = press(bot, october, "noviembre ›")

    assert api.summary_requests[-2:] == [(2, "2026-09"), (2, "2026-11")]
    assert text_of(september).startswith("Casa · septiembre de 2026")
    assert labels(november[-1]) == ["‹ octubre", "diciembre ›"]

    api.summaries = summaries_for([2], ["2026-01", "2025-12"])
    january = send(bot, Press("sum:2:2026-01"))
    assert labels(january[-1]) == ["‹ diciembre", "febrero ›"]
    press(bot, january, "‹ diciembre")
    assert api.summary_requests[-1] == (2, "2025-12")


def test_summary_in_the_middle_of_an_expense_keeps_the_draft() -> None:
    # Criterio 7 de la 006 (RF-18).
    api = FakeApi()
    api.summaries = summaries_for([1], ["2026-10", "2026-09"])
    bot = make(api)
    categories = send(bot, Text("20000"))

    summary = send(bot, Command("resumen"))
    press(bot, summary, "‹ septiembre")
    payments = press(bot, categories, "Comida")

    assert labels(payments[-1]) == ["Débito", "Crédito"]


def test_summary_buttons_work_without_any_state() -> None:
    # RF-18, decisión 6: un botón de un resumen sirve en un bot recién
    # arrancado, sin borrador ni conversación previa.
    api = FakeApi()
    api.summaries = summaries_for([1], ["2026-08"])

    replies = send(make(api), Press("sum:1:2026-08"))

    assert text_of(replies).startswith("Personal · agosto de 2026")


@pytest.mark.parametrize("data", ["sum:x:2026-10", "sum:1", "sum:1:2026-13", "otra:1"])
def test_malformed_query_buttons_change_nothing(data: str) -> None:
    api = FakeApi()

    replies = send(make(api), Press(data))

    assert "ya terminó" in text_of(replies)
    assert api.summary_requests == []


# --- /ultimos (spec 006, T5) ---


def expense(
    expense_id: int,
    amount: int,
    created_by: int = 1,
    created_at: str = "2026-10-31T15:00:00Z",
    description: str | None = None,
) -> dict:
    return {
        "id": expense_id,
        "amount": amount,
        "payment_type": "debit",
        "category_id": 2,
        "spent_on": "2026-10-30",
        "description": description,
        "created_by": created_by,
        "created_at": created_at,
    }


def test_recent_with_one_space_lists_the_expenses() -> None:
    # RF-9, RF-10 (criterio 5 de la 006).
    api = FakeApi()
    api.recent = {
        1: [expense(2, 5_000, created_by=7), expense(1, 20_000, description="Mercado")]
    }

    replies = send(make(api), Command("ultimos"))

    assert text_of(replies).split("\n") == [
        "Últimos gastos registrados en Personal:",
        "",
        "1. $ 5.000 · Comida · ayer, 30 de octubre · de otro miembro",
        "2. $ 20.000 · Comida · ayer, 30 de octubre · Mercado",
    ]


def test_recent_of_an_empty_space_says_so() -> None:
    # RF-11.
    replies = send(make(FakeApi()), Command("ultimos"))

    assert text_of(replies) == "Todavía no hay gastos registrados en Personal."


def test_with_two_spaces_recent_asks_the_space_first() -> None:
    # Criterio 4 de la 006.
    api = FakeApi(spaces=TWO_SPACES)
    api.recent = {2: [expense(1, 20_000)]}
    bot = make(api)

    replies = send(bot, Command("ultimos"))

    assert labels(replies[-1]) == ["Personal", "Casa"]
    assert "recent_expenses" not in api.calls
    assert "en Casa" in text_of(press(bot, replies, "Casa"))


def test_recent_in_the_middle_of_an_expense_keeps_the_draft() -> None:
    # RF-18.
    api = FakeApi()
    bot = make(api)
    categories = send(bot, Text("20000"))

    send(bot, Command("ultimos"))

    assert labels(press(bot, categories, "Comida")[-1]) == ["Débito", "Crédito"]


# --- /deshacer (spec 006, T6) ---


def test_undo_proposes_my_latest_expense_across_spaces() -> None:
    # Criterio 6 de la 006 (RF-12): el más reciente de cualquier espacio, y
    # nunca el de otro miembro aunque sea más nuevo.
    api = FakeApi(spaces=TWO_SPACES)
    api.recent = {
        1: [expense(1, 20_000, created_at="2026-10-31T10:00:00Z")],
        2: [
            expense(5, 99_000, created_by=7, created_at="2026-10-31T23:00:00Z"),
            expense(4, 8_000, created_at="2026-10-31T12:00:00Z", description="Taxi"),
        ],
    }

    replies = send(make(api), Command("deshacer"))

    text = text_of(replies)
    assert "¿Borro este gasto?" in text
    assert "$ 8.000 · Comida · ayer, 30 de octubre · Taxi" in text
    assert "Espacio: Casa" in text
    assert labels(replies[-1]) == ["Borrar", "Cancelar"]
    # RF-14: todavía no se borró nada.
    assert "delete_expense" not in api.calls


def test_undo_cancel_deletes_nothing() -> None:
    # RF-16.
    api = FakeApi()
    api.recent = {1: [expense(1, 20_000)]}
    bot = make(api)

    replies = press(bot, send(bot, Command("deshacer")), "Cancelar")

    assert "No borré nada" in text_of(replies)
    assert api.deleted == []


def test_undo_deletes_only_that_expense_and_only_once() -> None:
    # Criterio 6 (RF-15).
    api = FakeApi()
    api.recent = {1: [expense(2, 5_000), expense(1, 20_000)]}
    bot = make(api)
    proposal = send(bot, Command("deshacer"))

    first = press(bot, proposal, "Borrar")
    second = press(bot, proposal, "Borrar")

    assert "borré el gasto" in text_of(first)
    assert api.deleted == [(1, 2)]
    assert "ya no existe" in text_of(second)
    assert api.deleted == [(1, 2)]


def test_undo_without_own_expenses_says_there_is_nothing() -> None:
    # RF-13: los gastos de otros miembros no cuentan.
    api = FakeApi()
    api.recent = {1: [expense(1, 20_000, created_by=7)]}

    replies = send(make(api), Command("deshacer"))

    assert "No tienes gastos que deshacer" in text_of(replies)
    assert replies[-1].buttons == ()


def test_undo_in_the_middle_of_an_expense_keeps_the_draft() -> None:
    # RF-18.
    api = FakeApi()
    api.recent = {1: [expense(1, 20_000)]}
    bot = make(api)
    categories = send(bot, Text("20000"))

    press(bot, send(bot, Command("deshacer")), "Cancelar")

    assert labels(press(bot, categories, "Comida")[-1]) == ["Débito", "Crédito"]


# --- Comunes de la 006 (T7) ---


@pytest.mark.parametrize("name", ["resumen", "ultimos", "deshacer"])
def test_queries_in_an_unlinked_chat_explain_how_to_link(name: str) -> None:
    # Criterio 8 de la 006 (RF-17).
    api = FakeApi(linked=False)

    replies = send(make(api), Command(name))

    assert "no está vinculado" in text_of(replies)
    assert set(api.calls) <= {"spaces"}  # Corta en la primera llamada.


@pytest.mark.parametrize("name", ["resumen", "ultimos", "deshacer"])
def test_queries_with_the_api_down_say_so(name: str) -> None:
    # RF-19.
    api = FakeApi()
    api.down = True

    assert "No pude hablar con gastito" in text_of(send(make(api), Command(name)))


def test_a_query_with_the_api_down_keeps_the_draft() -> None:
    # RF-18 también cuando la consulta falla.
    api = FakeApi()
    bot = make(api)
    categories = send(bot, Text("20000"))

    api.down = True
    send(bot, Command("resumen"))
    api.down = False

    assert labels(press(bot, categories, "Comida")[-1]) == ["Débito", "Crédito"]


def test_help_names_the_query_commands() -> None:
    # RF-20.
    text = text_of(send(make(FakeApi()), Command("ayuda")))

    for command in ("/resumen", "/ultimos", "/deshacer"):
        assert command in text
