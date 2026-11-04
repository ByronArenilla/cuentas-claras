"""Adaptador de python-telegram-bot: solo traduce, sin conectarse a Telegram."""

from datetime import UTC, datetime

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from bot.config import Settings
from bot.conversation import Button, Reply
from bot.telegram_app import COMMANDS, MENU, build_application, is_private, to_markup

SETTINGS = Settings(
    telegram_bot_token="123456:token-de-prueba",
    api_url="http://api.test",
    bot_api_key="k" * 32,
    tz="America/Bogota",
)


def update_in(chat_type: str, text: str = "hola") -> Update:
    entities = (
        [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))]
        if text.startswith("/")
        else []
    )
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=7, type=chat_type),
        from_user=User(id=7, first_name="Ana", is_bot=False),
        text=text,
        entities=entities,
    )
    return Update(update_id=1, message=message)


def test_buttons_become_an_inline_keyboard() -> None:
    reply = Reply(
        "¿Cómo pagaste?",
        ((Button("Débito", "1:payment:debit"), Button("Crédito", "1:payment:credit")),),
    )

    markup = to_markup(reply)

    assert markup is not None
    [[debit, credit]] = markup.inline_keyboard
    assert (debit.text, debit.callback_data) == ("Débito", "1:payment:debit")
    assert (credit.text, credit.callback_data) == ("Crédito", "1:payment:credit")


def test_a_reply_without_buttons_has_no_keyboard() -> None:
    assert to_markup(Reply("Hola")) is None


@pytest.mark.parametrize(
    ("chat_type", "private"),
    [("private", True), ("group", False), ("supergroup", False), ("channel", False)],
)
def test_only_private_chats_are_private(chat_type: str, private: bool) -> None:
    # RF-8, decisión 6.
    assert is_private(update_in(chat_type)) is private


def test_every_command_has_a_handler() -> None:
    app = build_application(SETTINGS)
    handlers = app.handlers[0]

    commands = {
        command
        for handler in handlers
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert commands == set(COMMANDS)
    assert any(isinstance(handler, CallbackQueryHandler) for handler in handlers)


@pytest.mark.parametrize("text", ["/gasto", "20.000"])
def test_message_handlers_ignore_groups(text: str) -> None:
    # RF-8: los filtros de cada manejador de mensajes dejan pasar el chat
    # privado y frenan el grupo.
    handlers = [
        handler
        for handler in build_application(SETTINGS).handlers[0]
        if isinstance(handler, CommandHandler | MessageHandler)
    ]

    assert handlers
    for handler in handlers:
        assert not handler.filters.check_update(update_in("group", text))
    assert any(
        handler.filters.check_update(update_in("private", text)) for handler in handlers
    )


# --- Spec 006 ---


def test_query_commands_are_registered() -> None:
    assert {"resumen", "ultimos", "deshacer"} <= set(COMMANDS)


def test_the_menu_only_lists_existing_commands_with_a_description() -> None:
    # RF-20, decisión 8.
    names = [name for name, _ in MENU]
    assert set(names) <= set(COMMANDS)
    assert {"gasto", "resumen", "ultimos", "deshacer"} <= set(names)
    assert all(description.strip() for _, description in MENU)
    # Telegram admite descripciones de 3 a 256 caracteres.
    assert all(3 <= len(description) <= 256 for _, description in MENU)


def test_the_menu_is_registered_when_the_bot_starts() -> None:
    app = build_application(SETTINGS)

    assert app.post_init is not None
