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
WEEKLY_REPORT_INTERVAL_HOURS = float(os.environ.get("NOBODY_WEEKLY_REPORT_INTERVAL_HOURS", str(24 * 7)))
FOUNDER_EMAIL = os.environ.get("NOBODY_FOUNDER_EMAIL", "santiago.respen@gmail.com")

TELEGRAM_MESSAGE_LIMIT = 4000  # límite real de Telegram es 4096, se deja margen


def _split_long_message(text: str) -> list[str]:
    """Telegram corta mensajes en 4096 caracteres — el Board Report
    semanal suele superarlo. Se parte por párrafos para no cortar una
    oración a la mitad."""
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def _send_long_message(send, text: str) -> None:
    """`send` es cualquier callable async de un solo argumento de texto
    (update.message.reply_text, update.message.chat.send_message, o
    functools.partial(app.bot.send_message, chat_id=...))."""
    for chunk in _split_long_message(text):
        await send(chunk)


def _email_report(subject: str, body: str) -> None:
    """Envía el mismo reporte que va por Telegram, también por correo.
    Nunca revienta el ciclo si falla — solo lo deja en el log."""
    try:
        from integrations.gmail.client import send_email

        send_email(FOUNDER_EMAIL, subject, body)
    except Exception:
        logger.exception("No se pudo enviar el reporte por correo")


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


async def handle_genera_ahora(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/genera_ahora — dispara el ciclo del CEO fuera del horario
    automático. Publica de verdad (mismo comportamiento que el ciclo
    diario) — no es una simulación."""
    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    if update.effective_chat is None or update.effective_chat.id != founder_chat_id:
        return

    from agents.ceo.loop import run_cycle

    await update.message.reply_text(
        "Arrancando el ciclo ahora — va a generar y publicar de verdad. Aviso cuando termine."
    )
    try:
        result = await asyncio.to_thread(run_cycle, True)
        summary = _cycle_summary_text(result)
        await update.message.reply_text(summary)
        if result.get("playlist_message"):
            await update.message.reply_text(result["playlist_message"])
        await asyncio.to_thread(_email_report, "NOBODY CEO — ciclo on-demand", summary)
    except Exception:
        logger.exception("Error corriendo el ciclo on-demand")
        await update.message.reply_text("Algo falló corriendo el ciclo — revisa los logs.")


async def handle_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/agenda <texto libre> — crea un evento SOLO en tu calendario, nunca
    invita a terceros directo (decisión de gobierno, ver
    integrations/calendar/client.py)."""
    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    if update.effective_chat is None or update.effective_chat.id != founder_chat_id:
        return

    request_text = " ".join(context.args) if context.args else ""
    if not request_text:
        await update.message.reply_text(
            "Uso: /agenda mañana 3pm llamada con distribuidor sobre APU"
        )
        return

    from agents.capabilities.schedule import parse_and_create_event

    try:
        link = await asyncio.to_thread(parse_and_create_event, request_text)
        await update.message.reply_text(f"Agendado: {link}")
    except ValueError as e:
        await update.message.reply_text(f"No pude agendar: {e}")
    except Exception:
        logger.exception("Error agendando evento")
        await update.message.reply_text("Algo falló creando el evento — revisa los logs.")


def _cycle_summary_text(result: dict) -> str:
    if result.get("skipped"):
        return f"Ciclo del CEO: no corrió ({result.get('reason')})."
    actions = result.get("actions", [])
    if not actions:
        return "Ciclo del CEO corrido — no había contenido nuevo para generar."
    lines = ["Ciclo del CEO completado:"]
    for a in actions:
        status = a["status"]
        if a["kind"] == "comment":
            lines.append(f"- comentario en '{a.get('channel')}': {status}")
        elif a["kind"] == "playlist":
            # No crea nada en Spotify (add_tracks sigue bloqueado, ver
            # agents.capabilities.playlist) — status siempre es "draft",
            # la tracklist curada va en el próximo mensaje para crear a mano.
            lines.append("- playlist: curada, pendiente de crear a mano (tracklist en el próximo mensaje)")
        else:
            vid = a.get("video_id")
            link = f" https://youtu.be/{vid}" if vid else ""
            lines.append(f"- {a['kind']}: {status}{link}")
    after = result.get("after", {})
    lines.append(
        f"\nSubs: {after.get('subscribers')} | "
        f"Watch hours 365d: {after.get('watch_hours_365d')}"
    )
    return "\n".join(lines)


async def handle_reporte_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reporte_semanal — genera el Board Report bajo demanda (mismo
    contenido que el envío automático semanal), para no tener que
    esperar al disparador periódico para revisarlo o probarlo."""
    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    if update.effective_chat is None or update.effective_chat.id != founder_chat_id:
        return

    from agents.ceo.board_report import generate_weekly_report

    await update.message.chat.send_action("typing")
    try:
        report = await asyncio.to_thread(generate_weekly_report)
        await _send_long_message(update.message.reply_text, report)
        await asyncio.to_thread(_email_report, "NOBODY CEO — Board Report semanal", report)
    except Exception:
        logger.exception("Error generando el Board Report semanal")
        await update.message.reply_text("Algo falló generando el Board Report — revisa los logs.")


async def _run_weekly_report_periodically(app: Application) -> None:
    from agents.ceo.board_report import generate_weekly_report

    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    # Primer envío recién a los WEEKLY_REPORT_INTERVAL_HOURS de arrancar
    # el bot (no al iniciar) — evita mandar un reporte cada vez que el
    # proceso se reinicia (crash, redeploy).
    while True:
        await asyncio.sleep(WEEKLY_REPORT_INTERVAL_HOURS * 3600)
        try:
            logger.info("Generando Board Report semanal")
            report = await asyncio.to_thread(generate_weekly_report)
            send = lambda text: app.bot.send_message(chat_id=founder_chat_id, text=text)
            await _send_long_message(send, report)
            await asyncio.to_thread(_email_report, "NOBODY CEO — Board Report semanal", report)
        except Exception:
            logger.exception("Error generando el Board Report semanal")


async def _run_cycle_periodically(app: Application) -> None:
    from agents.ceo.loop import run_cycle

    founder_chat_id = int(os.environ["TELEGRAM_FOUNDER_CHAT_ID"])
    cycle_count = 0
    while True:
        try:
            logger.info("Iniciando ciclo del CEO #%d", cycle_count)
            result = await asyncio.to_thread(run_cycle)
            logger.info("Ciclo del CEO completado: %s", result.get("actions"))
            summary = _cycle_summary_text(result)
            await app.bot.send_message(chat_id=founder_chat_id, text=summary)
            if result.get("playlist_message"):
                await app.bot.send_message(chat_id=founder_chat_id, text=result["playlist_message"])
            await asyncio.to_thread(_email_report, "NOBODY CEO — ciclo diario", summary)
        except Exception:
            logger.exception("Error en el ciclo del CEO")
        cycle_count += 1
        await asyncio.sleep(CYCLE_INTERVAL_HOURS * 3600)


async def post_init(app: Application) -> None:
    asyncio.create_task(_run_cycle_periodically(app))
    asyncio.create_task(_run_weekly_report_periodically(app))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).post_init(post_init).build()
    app.add_handler(CommandHandler("nuevo", handle_nuevo))
    app.add_handler(CommandHandler("genera_ahora", handle_genera_ahora))
    app.add_handler(CommandHandler("agenda", handle_agenda))
    app.add_handler(CommandHandler("reporte_semanal", handle_reporte_semanal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info(
        "NOBODY CEO escuchando en Telegram (long-polling) — ciclo cada %sh",
        CYCLE_INTERVAL_HOURS,
    )
    app.run_polling()


if __name__ == "__main__":
    main()
