#!/usr/bin/env python3
import os
import re
import html
import logging

from flask import Flask, request, abort
from telegram import Bot, Update, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ─── Settings ──────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
EXTERNAL_URL  = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
PORT          = int(os.environ.get("PORT", "8443"))

PHONE_RE = re.compile(r"^\+?\d[\d\s\-\(\)]{7,}$")
NAME, PHONE, COMMENT = range(3)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ─── App & Bot setup ───────────────────────────────────────────────────────────
app = Flask(__name__)
bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot, None, workers=0, use_context=True)

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🍰 Добро пожаловать! Я приму ваш заказ на торт.\nКак вас зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    return NAME

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("📞 Номер телефона:")
    return PHONE

async def ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not PHONE_RE.fullmatch(phone):
        await update.message.reply_text("❗ Некорректный номер. Попробуйте ещё раз:")
        return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text("💬 Комментарий (вкус, вес, дата) или «-»:")
    return COMMENT

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = context.user_data
    d["comment"] = update.message.text.strip()

    text = (
        "🎂 <b>Новый заказ торта!</b>\n\n"
        f"<b>Имя:</b> {html.escape(d['name'])}\n"
        f"<b>Телефон:</b> {html.escape(d['phone'])}\n"
        f"<b>Комментарий:</b> {html.escape(d['comment'])}"
    )
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.HTML)
    await update.message.reply_text("Спасибо! Ваш заказ принят ✅")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено. /start — начать заново.")
    return ConversationHandler.END

# регистрируем ConversationHandler
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_comment)],
        COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
dp.add_handler(conv)

# ─── Webhook & Health ─────────────────────────────────────────────────────────
@app.before_first_request
def setup_webhook():
    url = f"{EXTERNAL_URL}/{BOT_TOKEN}"
    logging.info("Setting webhook → %s", url)
    bot.set_webhook(url)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(update)
    return "OK"

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ─── Run Flask ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
