"""La conversación del bot, sin Telegram ni red (spec 005; principio 10)."""

import asyncio
from datetime import UTC, datetime

import pytest

from bot.api import ApiUnavailable
from bot.conversation import Command, Conversations, Reply, Text
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
