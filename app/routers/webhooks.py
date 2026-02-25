from fastapi import APIRouter, Request, HTTPException
from telegram import Update
from app.bot import application
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates"""
    try:
        update_data = await request.json()
        # PTB ожидает объект Update, не сырой dict
        update = Update.de_json(data=update_data, bot=application.bot)
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/webhook")
async def verify_webhook():
    """Verify webhook setup"""
    return {"status": "webhook endpoint is active"}