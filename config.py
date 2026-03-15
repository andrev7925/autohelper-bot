from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="api.env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
	raise RuntimeError(
		"Telegram bot token is not configured. Set TELEGRAM_BOT_TOKEN (or BOT_TOKEN/TOKEN) in environment."
	)