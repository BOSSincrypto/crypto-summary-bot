import asyncio
import logging
import os
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import BOT_TOKEN, MORNING_HOUR_UTC, EVENING_HOUR_UTC
from db import init_db
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
    scheduled_summary,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("Health check server on port %d", port)
    server.serve_forever()


async def post_init(application: Application):
    await init_db()
    jq = application.job_queue
    jq.run_daily(
        scheduled_summary,
        time=datetime.time(hour=MORNING_HOUR_UTC, minute=0, second=0),
        name="morning_summary",
    )
    jq.run_daily(
        scheduled_summary,
        time=datetime.time(hour=EVENING_HOUR_UTC, minute=0, second=0),
        name="evening_summary",
    )
    logger.info(
        "Scheduled summaries at %02d:00 UTC and %02d:00 UTC",
        MORNING_HOUR_UTC,
        EVENING_HOUR_UTC,
    )


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("coins", coins_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("myid", myid_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
