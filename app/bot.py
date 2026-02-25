from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler,
    ContextTypes
)
from app.config import Config
from app.handlers.commands import (
    start_command, 
    profile_command, 
    goal_command, 
    today_command, 
    history_command, 
    reminder_command
)
from app.handlers.messages import handle_photo, handle_text_message
from app.handlers.callbacks import handle_callback_query
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create the bot application
application = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()

# Add command handlers
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("profile", profile_command))
application.add_handler(CommandHandler("goal", goal_command))
application.add_handler(CommandHandler("today", today_command))
application.add_handler(CommandHandler("history", history_command))
application.add_handler(CommandHandler("reminder", reminder_command))

# Add message handlers
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

# Add callback query handler
application.add_handler(CallbackQueryHandler(handle_callback_query))

logger.info("Bot application initialized with all handlers")