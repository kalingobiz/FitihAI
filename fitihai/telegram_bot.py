"""Telegram bot: the primary low-bandwidth channel.

Run:  TELEGRAM_BOT_TOKEN=... python -m fitihai.telegram_bot
"""

from __future__ import annotations

import asyncio
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

from .config import settings
from .corpus.store import CorpusStore
from .i18n import LANGUAGES, normalize_language, t
from .embeddings import build_embedder
from .llm import IMAGE_TYPES, PDF_TYPE, build_model
from .pipeline import Advisor, QuotaExceeded
from .schemas import AnalyzeResponse, AskResponse

log = logging.getLogger("fitihai.telegram")
TELEGRAM_LIMIT = 4000
SEVERITY_ICON = {"danger": "🔴", "attention": "🟡", "standard": "🟢"}


def _lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang") or normalize_language(None)


def _session_id(update: Update) -> str:
    return f"tg-{update.effective_chat.id}"


def _chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    parts, current = [], ""
    for para in text.split("\n"):
        while len(para) > limit:
            parts.append(para[:limit])
            para = para[limit:]
        if len(current) + len(para) + 1 > limit:
            parts.append(current)
            current = ""
        current += para + "\n"
    if current.strip():
        parts.append(current)
    return parts


def format_answer(res: AskResponse, lang: str) -> str:
    e = html.escape
    out = [e(res.answer)]
    if res.citations:
        out.append(f"\n<b>{e(t('sources', lang))}</b>")
        out += [f"• {e(c.citation)}" for c in res.citations]
    out.append(f"\n<i>{e(res.disclaimer)}</i>")
    return "\n".join(out)


def format_analysis(res: AnalyzeResponse, lang: str) -> str:
    e = html.escape
    out = [f"<b>{e(res.title)}</b>", e(res.summary), ""]
    for c in res.clauses:
        out.append(f"{SEVERITY_ICON[c.severity]} <i>“{e(c.quote)}”</i>\n{e(c.explanation)}")
    if res.deadlines:
        out.append(f"\n<b>⏰ {e(t('deadlines', lang))}</b>")
        for d in res.deadlines:
            when = d.date_as_written
            if d.gregorian_date:
                when += f" → {d.gregorian_date}"
            out.append(f"• {e(when)}: {e(d.description)}")
    if res.lawyer_questions:
        out.append(f"\n<b>❓ {e(t('ask_lawyer', lang))}</b>")
        out += [f"• {e(q)}" for q in res.lawyer_questions]
    if res.citations:
        out.append(f"\n<b>{e(t('sources', lang))}</b>")
        out += [f"• {e(c.citation)}" for c in res.citations]
    out.append(f"\n<i>{e(res.disclaimer)}</i>")
    return "\n".join(out)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=f"lang:{code}")]
                                 for code, name in LANGUAGES.items()])


async def _send(update: Update, text: str) -> None:
    for part in _chunks(text):
        await update.effective_chat.send_message(part, parse_mode=ParseMode.HTML)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t("choose_language", _lang(context)), reply_markup=language_keyboard())


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = normalize_language(query.data.split(":", 1)[1])
    context.user_data["lang"] = lang
    context.application.bot_data["advisor"].sessions.get(_session_id(update), lang)
    await query.edit_message_text(t("welcome", lang))


async def new_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["advisor"].sessions.clear(_session_id(update))
    await update.message.reply_text(t("new_session", _lang(context)))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context)
    advisor: Advisor = context.application.bot_data["advisor"]
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        res = await asyncio.to_thread(advisor.ask, update.message.text, _session_id(update), lang)
        await _send(update, format_answer(res, lang))
    except Exception:
        log.exception("ask failed")
        await update.message.reply_text(t("error", lang))


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context)
    advisor: Advisor = context.application.bot_data["advisor"]
    msg = update.message
    if msg.photo:
        tg_file = await msg.photo[-1].get_file()
        media_type = "image/jpeg"
    else:
        media_type = (msg.document.mime_type or "").lower()
        if media_type not in IMAGE_TYPES | {PDF_TYPE}:
            await msg.reply_text("PDF / JPEG / PNG")
            return
        if (msg.document.file_size or 0) > settings.max_upload_mb * 1024 * 1024:
            await msg.reply_text(f"Max {settings.max_upload_mb} MB")
            return
        tg_file = await msg.document.get_file()
    await msg.reply_text(t("working", lang))
    await update.effective_chat.send_action(ChatAction.TYPING)
    data = bytes(await tg_file.download_as_bytearray())
    try:
        res = await asyncio.to_thread(
            advisor.analyze_document, data, media_type, _session_id(update), lang, str(update.effective_user.id)
        )
        await _send(update, format_analysis(res, lang))
    except QuotaExceeded:
        await msg.reply_text(t("quota_exceeded", lang))
    except Exception:
        log.exception("analysis failed")
        await msg.reply_text(t("error", lang))
    finally:
        del data


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t("voice_unsupported", _lang(context)))


def build_application(advisor: Advisor, token: str) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["advisor"] = advisor
    app.add_handler(CommandHandler(["start", "lang"], start))
    app.add_handler(CommandHandler("new", new_session))
    app.add_handler(CallbackQueryHandler(choose_language, pattern=r"^lang:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.telegram_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    advisor = Advisor(settings, CorpusStore(settings.db_path), build_model(settings), build_embedder(settings))
    build_application(advisor, settings.telegram_token).run_polling()


if __name__ == "__main__":
    main()
