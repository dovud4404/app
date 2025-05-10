#!/usr/bin/env python3
import os, re, html, logging
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes,
)

# ───────── CONFIG ─────────────────────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
PORT          = int(os.environ["PORT"])            # <- Render сам задаёт, например 10000
EXTERNAL_URL  = os.environ["RENDER_EXTERNAL_URL"]  # только для webhook, можно убрать

# простая валидация
PHONE_RE = re.compile(r"^\+?\d[\d\s\-\(\)]{7,}$")
NAME, PHONE, COMMENT = range(3)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ───────── SETUP FLASK & BOT ──────────────────────────
app = Flask(__name__)
bot = Bot(BOT_TOKEN)
dp  = Dispatcher(bot, None, workers=0, use_context=True)

# ───────── HANDLERS ───────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🍰 Как вас зовут?", reply_markup=ReplyKeyboardRemove())
    return NAME

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("📞 Укажите телефон:")
    return PHONE

async def ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not PHONE_RE.fullmatch(phone):
        await update.message.reply_text("❗ Неправильный телефон, повторите:")
        return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text("💬 Ваш комментарий или «-»:")
    return COMMENT

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = context.user_data
    d["comment"] = update.message.text.strip()
    text = (
        "🎂 <b>Новый заказ!</b>\n\n"
        f"<b>Имя:</b> {html.escape(d['name'])}\n"
        f"<b>Телефон:</b> {html.escape(d['phone'])}\n"
        f"<b>Комментарий:</b> {html.escape(d['comment'])}"
    )
    await bot.send_message(GROUP_CHAT_ID, text, parse_mode=ParseMode.HTML)
    await update.message.reply_text("Спасибо! ✅")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено. /start — заново.")
    return ConversationHandler.END

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

# ───────── WEBHOOK & HEALTHCHECK ──────────────────────
@app.before_first_request
def set_webhook():
    url = f"{EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
    logging.info("Set webhook → %s", url)
    bot.set_webhook(url)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    upd = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(upd)
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ───────── RUN ─────────────────────────────────────────
if __name__ == "__main__":
    # слушаем ТОЛЬКО на порту, который дал Render
    app.run(host="0.0.0.0", port=PORT)
