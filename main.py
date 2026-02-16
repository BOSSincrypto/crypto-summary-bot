import asyncio
import json
import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import BOT_TOKEN
from db import init_db
import db
import services
from handlers import (
    start_cmd,
    help_cmd,
    summary_cmd,
    coins_cmd,
    support_cmd,
    myid_cmd,
    admin_cmd,
    callback_handler,
    text_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
WEBHOOK_PATH = "/webhook"
bot_loop = None
bot_application = None


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/trigger" and bot_loop and bot_application:
            import asyncio as _aio
            try:
                future = _aio.run_coroutine_threadsafe(
                    _run_trigger_summary(), bot_loop
                )
                future.result(timeout=180)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Summary sent")
            except Exception as exc:
                logger.error("Trigger summary failed: %s", exc)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Error")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        if self.path == WEBHOOK_PATH and bot_loop and bot_application:
            import asyncio as _aio
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body)
                update = Update.de_json(data, bot_application.bot)
                future = _aio.run_coroutine_threadsafe(
                    bot_application.process_update(update), bot_loop
                )
                future.result(timeout=30)
            except Exception as e:
                logger.error("Webhook processing error: %s", e)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


async def _run_trigger_summary():
    logger.info("Запуск сводки через /trigger...")
    try:
        summary = await services.generate_full_summary()
        users = await db.get_authenticated_users()
        sent = 0
        for user in users:
            try:
                text = summary
                while text:
                    chunk = text[:4000]
                    if len(text) > 4000:
                        idx = chunk.rfind("\n")
                        if idx > 0:
                            chunk = text[:idx]
                        text = text[len(chunk):].lstrip("\n")
                    else:
                        text = ""
                    try:
                        await bot_application.bot.send_message(
                            chat_id=user["telegram_id"], text=chunk,
                            parse_mode="HTML", disable_web_page_preview=True,
                        )
                    except Exception:
                        await bot_application.bot.send_message(
                            chat_id=user["telegram_id"], text=chunk,
                            disable_web_page_preview=True,
                        )
                sent += 1
            except Exception as e:
                logger.error("Ошибка отправки %s: %s", user["telegram_id"], e)
        logger.info("Сводка отправлена %d пользователям", sent)
    except Exception as e:
        logger.error("Ошибка генерации сводки: %s", e)


def _build_app():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("coins", coins_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("myid", myid_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    return app


async def run_webhook():
    global bot_loop, bot_application
    app = _build_app()
    await app.initialize()
    await app.start()
    await init_db()

    bot_loop = asyncio.get_event_loop()
    bot_application = app

    webhook_url = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"
    await app.bot.set_webhook(url=webhook_url)
    logger.info("Webhook установлен: %s", webhook_url)

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("HTTP сервер на порту %d", port)

    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()
        await app.shutdown()


def run_polling():
    global bot_loop, bot_application

    async def _post_init(application: Application):
        global bot_loop, bot_application
        bot_loop = asyncio.get_event_loop()
        bot_application = application
        await init_db()

    app = _build_app()
    app.post_init = _post_init

    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), WebhookHandler).serve_forever(),
        daemon=True,
    ).start()

    logger.info("Бот запускается в режиме polling...")
    app.run_polling(drop_pending_updates=True)


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        return

    if WEBHOOK_HOST:
        logger.info("Бот запускается в режиме webhook (%s)...", WEBHOOK_HOST)
        asyncio.run(run_webhook())
    else:
        logger.info("Бот запускается в режиме polling (WEBHOOK_HOST не задан)...")
        run_polling()


if __name__ == "__main__":
    main()
