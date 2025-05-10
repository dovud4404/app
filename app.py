#!/usr/bin/env python3
import os, re, html, logging, asyncio, threading
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes,
)

# ─── ENV ─────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID  = int(os.environ["GROUP_CHAT_ID"])
EXTERNAL_URL   = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
PORT           = int(os.environ.get("PORT", "8443"))

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{7,}$")
NAME, PHONE, COMMENT = range(3)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ─── Flask ------------------------------------------------------------
flask_app = Flask(__name__)

# ─── отдельный event-loop + поток ------------------------------------
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()

# ─── PTB Application --------------------------------------------------
tg_app = Application.builder().token(BOT_TOKEN).build()
bot: Bot = tg_app.bot

# ─── handlers ---------------------------------------------------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🍰 Ассаляму алейкум! Я приму ваш заказ. Как вас зовут?",
                                    reply_markup=ReplyKeyboardRemove())
    return NAME

async def ask_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("📞 Укажите ваш номер телефона (например +992 000000000):
    return PHONE

async def ask_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not PHONE_RE.fullmatch(phone):
        await update.message.reply_text("❗ Номер неверный, попробуйте ещё раз:")
        return PHONE
    ctx.user_data["phone"] = phone
    await update.message.reply_text("💬 Добавьте комментарий (вкус, вес, дата) или «-», если без комментариев:")
    return COMMENT

async def finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    d = ctx.user_data
    d["comment"] = update.message.text.strip()
    txt = (
        "🎂 <b>Новый заказ!</b>\n\n"
        f"<b>Имя:</b> {html.escape(d['name'])}\n"
        f"<b>Телефон:</b> {html.escape(d['phone'])}\n"
        f"<b>Комментарий:</b> {html.escape(d['comment'])}"
    )
    await bot.send_message(GROUP_CHAT_ID, txt, parse_mode=ParseMode.HTML)
    await update.message.reply_text("Спасибо!🎉 Ващ заказ отправлен администратору. Мы свяжемся с вами в ближайщее время ✅")
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено. /start — заново.")
    return ConversationHandler.END

tg_app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_comment)],
        COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
))

# ─── init bot + webhook в том же loop --------------------------------
async def _init():
    await tg_app.initialize()
    await bot.set_webhook(f"{EXTERNAL_URL}/{BOT_TOKEN}")
    logging.info("Webhook установлен → %s/%s", EXTERNAL_URL, BOT_TOKEN)

asyncio.run_coroutine_threadsafe(_init(), loop)

# ─── Flask routes -----------------------------------------------------
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    asyncio.run_coroutine_threadsafe(tg_app.process_update(update), loop)
    return "OK", 200

@flask_app.route("/health")
def health():
    return "OK", 200

# ─── local run (Render -> gunicorn) -----------------------------------
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
