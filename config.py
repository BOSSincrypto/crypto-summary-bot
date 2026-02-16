import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "ax1")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
EVM_ADDRESS = "0x5F4fe992a847e6B3cA07EBb379Ae02608D21BAb3"
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
AI_MODEL = os.getenv("AI_MODEL", "google/gemma-3n-e4b-it")
MORNING_HOUR_UTC = 5
EVENING_HOUR_UTC = 20
