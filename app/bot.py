import os

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    PicklePersistence,
)
from app.config import Config
from app.handlers.commands import (
    profile_command,
    goal_command,
    today_command,
    history_command,
    reminder_command,
)
from app.handlers.messages import handle_photo, handle_text_message
from app.handlers.callbacks import handle_callback_query
from app.handlers.profile_conversation import build_profile_conversation_handler
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояние диалога профиля: опционально сохраняем на диск (задайте PERSISTENCE_PATH, например /tmp/calTG_state)
_builder = (
    ApplicationBuilder()
    .token(Config.TELEGRAM_BOT_TOKEN)
    .concurrent_updates(False)
)
_path = os.environ.get("PERSISTENCE_PATH")
if _path:
    try:
        _builder = _builder.persistence(PicklePersistence(filepath=_path))
        logger.info("Using persistence path: %s", _path)
    except Exception as e:
        logger.warning("Persistence disabled: %s", e)
application = _builder.build()

# Пошаговое заполнение профиля — добавляем первым, чтобы перехватывать ответы в диалоге
# persistent=True только если задан PERSISTENCE_PATH, иначе ValueError при старте
application.add_handler(build_profile_conversation_handler(persistent=bool(_path)))

# /start обрабатывается в ConversationHandler (сразу ведёт в заполнение профиля для новых)
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