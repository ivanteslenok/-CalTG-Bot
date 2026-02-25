import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routers import webhook_router, health_router
from app.config import Config
from app.database import engine, Base
from app.bot import application
from app.utils.reminders import schedule_reminders
import logging
import asyncio
import sqlalchemy.exc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the reminder scheduler
reminder_scheduler = schedule_reminders(application)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    logger.info("Starting up CalTG application...")
    Config.validate()
    # Create database tables (игнорируем DuplicateTableError при нескольких воркерах или повторном деплое)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    except sqlalchemy.exc.ProgrammingError as e:
        if "already exists" in str(e).lower():
            logger.info("Database tables already exist, skipping create_all")
        else:
            raise

    # Регистрируем webhook в Telegram (чтобы обновления шли на наш URL)
    webhook_url = Config.WEBHOOK_URL
    if webhook_url and "your-app-name" not in webhook_url:
        try:
            await application.bot.set_webhook(url=webhook_url)
            logger.info("Telegram webhook set to %s", webhook_url)
        except Exception as e:
            logger.warning("Failed to set Telegram webhook: %s", e)
    else:
        logger.warning("WEBHOOK_URL not set or placeholder - set it in Render Environment to your URL, e.g. https://caltg-bot.onrender.com/webhook")

    # Start the reminder scheduler
    reminder_scheduler.start_scheduler()
    logger.info("Reminder scheduler started")
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down CalTG application...")
    
    # Stop the reminder scheduler
    reminder_scheduler.stop_scheduler()
    logger.info("Reminder scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="CalTG - Telegram Bot for Calorie Counting",
    description="A Telegram bot that helps users track their calorie intake using AI-powered food recognition.",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(webhook_router, prefix="", tags=["webhook"])
app.include_router(health_router, prefix="", tags=["health"])

# Initialize the bot application
async def initialize_bot():
    """Initialize the bot application"""
    await application.initialize()
    await application.start()

# Run initialization
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))