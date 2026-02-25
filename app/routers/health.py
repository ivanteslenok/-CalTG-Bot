from fastapi import APIRouter
from app.config import Config
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "CalTG Telegram Bot API",
        "telegram_bot_configured": bool(Config.TELEGRAM_BOT_TOKEN),
        "openrouter_configured": bool(Config.OPENROUTER_API_KEY),
        "usda_configured": bool(Config.USDA_API_KEY)
    }


@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "CalTG - Telegram Bot for Calorie Counting API"}