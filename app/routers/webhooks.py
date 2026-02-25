from fastapi import APIRouter, Request, HTTPException
from app.bot import application
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates"""
    try:
        # Get the update data from the request
        update_data = await request.json()
        
        # Process the update with the bot application
        await application.update_queue.put(update_data)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/webhook")
async def verify_webhook():
    """Verify webhook setup"""
    return {"status": "webhook endpoint is active"}