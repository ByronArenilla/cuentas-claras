"""Adaptador entre python-telegram-bot y la conversación (spec 005).

Solo traduce: un mensaje o un botón de Telegram pasa a ser un evento de
`bot.conversation`, y cada respuesta vuelve a ser un mensaje. Ninguna regla
vive aquí (principio 10).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.api import ApiClient
from bot.config import Settings
from bot.conversation import Command, Conversations, Event, Press, Reply, Text

COMMANDS = ("start", "ayuda", "gasto", "cancelar", "vincular", "desvincular")

# RF-8, decisión 6: en un grupo, cualquiera podría registrar a nombre del
# usuario vinculado.
PRIVATE = filters.ChatType.PRIVATE


def is_private(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


def to_markup(reply: Reply) -> InlineKeyboardMarkup | None:
    """Las filas de botones de la respuesta como teclado en línea."""
    if not reply.buttons:
        return None
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(b.label, callback_data=b.data) for b in row]
            for row in reply.buttons
        ]
    )


def build_application(settings: Settings) -> Application:
    """La aplicación de Telegram con un manejador por comando, uno para texto
    y uno para botones. Construirla no se conecta a Telegram."""
    api = ApiClient(settings.api_url, settings.bot_api_key)
    conversations = Conversations(api, settings.tz)

    async def close_api(_app: Application) -> None:
        await api.aclose()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_shutdown(close_api)
        .build()
    )

    async def answer(update: Update, event: Event) -> None:
        chat = update.effective_chat
        assert chat is not None
        for reply in await conversations.handle(chat.id, event):
            await chat.send_message(reply.text, reply_markup=to_markup(reply))

    def on_command(name: str):  # noqa: ANN202 - devuelve el manejador
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await answer(update, Command(name, " ".join(context.args or [])))

        return handler

    async def on_text(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_message is not None
        await answer(update, Text(update.effective_message.text or ""))

    async def on_unknown_command(
        update: Update, _context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        # Un comando que no existe recibe la ayuda.
        await answer(update, Command("desconocido"))

    async def on_press(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or not is_private(update):
            return
        await query.answer()
        # Sin teclado, el mismo botón no se puede tocar dos veces (RF-20).
        try:
            await query.edit_message_reply_markup(None)
        except TelegramError:
            pass  # El mensaje es muy viejo o ya no tiene teclado: da igual.
        await answer(update, Press(query.data or ""))

    for name in COMMANDS:
        app.add_handler(CommandHandler(name, on_command(name), filters=PRIVATE))
    app.add_handler(MessageHandler(PRIVATE & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(PRIVATE & filters.COMMAND, on_unknown_command))
    # `CallbackQueryHandler` no admite filtros: el chat se comprueba dentro.
    app.add_handler(CallbackQueryHandler(on_press))
    return app
