import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./calories.db")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "gpt-4.2-mini")
    USDA_API_KEY = os.getenv("USDA_API_KEY")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-app-name.onrender.com/webhook")

    @classmethod
    def validate(cls) -> None:
        """Проверяет наличие обязательных переменных окружения. Вызывать при старте приложения."""
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.OPENROUTER_API_KEY:
            missing.append("OPENROUTER_API_KEY")
        if not cls.USDA_API_KEY:
            missing.append("USDA_API_KEY")
        if missing:
            raise ValueError(
                f"Не заданы обязательные переменные окружения в Render Dashboard: {', '.join(missing)}. "
                "Добавьте их в Environment для сервиса caltg."
            )