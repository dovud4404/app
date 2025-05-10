#!/usr/bin/env python3
import os, re, html, logging, asyncio
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ─── Конфиг ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID  = int(os.environ["GROUP_CHAT_ID"])
EXTERNAL_URL   = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
PORT           = int(os.environ.get("PORT", "8443"))

PHONE_RE = re.compile(r"^\+?\d[\d\s\-\(\)]{7,}$")
NAME, PHONE, COMMENT = range(3)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─── Flask и Telegram-Application ────────────────────────────────────────────
flask_app = Flask(__name__)
tg_app    = Application.builder().token(BOT_TOKEN).build()   # ← вместо Dispatcher
bot       = tg_app.bot

# ─── Хэндлеры бота ────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🍰 Добро пожаловать! Как вас зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    return NAME

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("📞 Ваш номер телефона:")
    return PHONE

async def ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not PHONE_RE.fullmatch(phone):
        await update.message.reply_text("❗ Некорректный номер, попробуйте ещё раз:")
        return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text("💬 Комментарий (вкус, дата) или «-»:")
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
    await update.message.reply_text("Спасибо! Заказ принят ✅")
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
tg_app.add_handler(conv)

# ─── Webhook + health ────────────────────────────────────────────────────────
@flask_app.before_first_request
def init_webhook():
    """Запускается один раз при первом HTTP-запросе к Flask."""
    async def setup():
        await tg_app.initialize()
        await tg_app.start()
        await bot.set_webhook(f"{EXTERNAL_URL}/{BOT_TOKEN}")
        logging.info("Webhook установлен: %s/%s", EXTERNAL_URL, BOT_TOKEN)
    asyncio.get_event_loop().create_task(setup())

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    asyncio.get_event_loop().create_task(tg_app.process_update(update))
    return "OK", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ─── Запуск ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
