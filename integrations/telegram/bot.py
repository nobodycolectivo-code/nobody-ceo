"""Bot de Telegram — modo pregunta del CEO, long-polling.

Restringido al chat_id del Founder (TELEGRAM_FOUNDER_CHAT_ID) — cualquier
otro chat se ignora y nunca llega al CEO ni a NOBODY_BRAIN.

Uso:
    python -m integrations.telegram.bot
"""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from agents.ceo.ask import answer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("nobody_ceo.telegram")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    if update.effective_chat is None or update.effective_chat.id != founder_chat_id:
        logger.warning(
            "Mensaje ignorado de chat no autorizado: %s",
            update.effective_chat.id if update.effective_chat else "desconocido",
        )
        return

    question = update.message.text
    await update.message.chat.send_action("typing")
    try:
        reply = answer(question)
    except Exception:
        logger.exception("Error respondiendo la pregunta")
        reply = "Algo falló leyendo NOBODY_BRAIN — revisa los logs de la terminal."
    await update.message.reply_text(reply)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("NOBODY CEO escuchando en Telegram (long-polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
