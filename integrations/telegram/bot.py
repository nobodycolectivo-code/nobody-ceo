"""Bot de Telegram — modo pregunta del CEO, long-polling. También corre
el ciclo autónomo (agents.ceo.loop) en segundo plano dentro del mismo
proceso, para compartir el volumen de NOBODY_BRAIN sin necesitar un
segundo servicio en Railway.

Restringido al chat_id del Founder (TELEGRAM_FOUNDER_CHAT_ID) — cualquier
otro chat se ignora y nunca llega al CEO ni a NOBODY_BRAIN.

Uso:
    python -m integrations.telegram.bot
"""

from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agents.ceo.ask import answer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("nobody_ceo.telegram")

CYCLE_INTERVAL_HOURS = float(os.environ.get("NOBODY_CYCLE_INTERVAL_HOURS", "24"))


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


async def handle_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/nuevo <descripción> — Santiago avisa que agregó material a la
    carpeta del catálogo. El bot NO puede leer esa carpeta (vive en la
    máquina local, no en Railway) — solo deja constancia en
    brain/decisions. La sincronización real corre localmente, ver
    scripts/sync_catalogue.py."""
    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    if update.effective_chat is None or update.effective_chat.id != founder_chat_id:
        return

    from brain.db import connect
    from brain.decisions.store import Decision, record as record_decision

    detalle = " ".join(context.args) if context.args else "(sin descripción)"
    conn = connect()
    record_decision(
        conn,
        Decision(
            objective_id=None,
            evidence=f"aviso de Santiago vía Telegram: {detalle}",
            reasoning="El catálogo local no es visible desde Railway — queda pendiente de sync manual.",
            action="Pendiente: sincronizar catálogo (correr scripts/sync_catalogue.py localmente)",
            expected_result="Contenido nuevo disponible para generar reels/videos",
            status="pending",
        ),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        "Anotado. No puedo leer la carpeta del catálogo desde aquí (vivo en la nube) — "
        "hay que correr scripts/sync_catalogue.py en tu máquina para que quede disponible."
    )


def _cycle_summary_text(result: dict) -> str:
    if result.get("skipped"):
        return f"Ciclo del CEO: no corrió ({result.get('reason')})."
    actions = result.get("actions", [])
    if not actions:
        return "Ciclo del CEO corrido — no había contenido nuevo para generar."
    lines = ["Ciclo del CEO completado:"]
    for a in actions:
        status = a["status"]
        vid = a.get("video_id")
        link = f" https://youtu.be/{vid}" if vid else ""
        lines.append(f"- {a['kind']}: {status}{link}")
    after = result.get("after", {})
    lines.append(
        f"\nSubs: {after.get('subscribers')} | "
        f"Watch hours 365d: {after.get('watch_hours_365d')}"
    )
    return "\n".join(lines)


async def _run_cycle_periodically(app: Application) -> None:
    from agents.ceo.loop import run_cycle

    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    cycle_count = 0
    while True:
        try:
            logger.info("Iniciando ciclo del CEO #%d", cycle_count)
            result = await asyncio.to_thread(run_cycle)
            logger.info("Ciclo del CEO completado: %s", result.get("actions"))
            await app.bot.send_message(chat_id=founder_chat_id, text=_cycle_summary_text(result))
        except Exception:
            logger.exception("Error en el ciclo del CEO")
        cycle_count += 1
        await asyncio.sleep(CYCLE_INTERVAL_HOURS * 3600)


async def post_init(app: Application) -> None:
    asyncio.create_task(_run_cycle_periodically(app))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).post_init(post_init).build()
    app.add_handler(CommandHandler("nuevo", handle_nuevo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info(
        "NOBODY CEO escuchando en Telegram (long-polling) — ciclo cada %sh",
        CYCLE_INTERVAL_HOURS,
    )
    app.run_polling()


if __name__ == "__main__":
    main()
