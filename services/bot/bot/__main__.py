"""`python -m bot`: arranca el bot y espera mensajes (*polling*, plan 005)."""

import logging
import os

from telegram import Update

from bot.config import load_settings
from bot.telegram_app import build_application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    # httpx registra cada URL en INFO, y las de Telegram llevan el token del
    # bot dentro: así el token nunca llega a los logs (principio 12).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings(os.environ)
    build_application(settings).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
