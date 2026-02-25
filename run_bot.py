#!/usr/bin/env python3
"""
Entry point to run the CalTG Telegram bot
"""

import asyncio
import logging
from app.bot import application
from app.config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to run the bot"""
    logger.info("Starting CalTG bot...")
    
    # Initialize the application
    await application.initialize()
    
    # Start the bot
    await application.start()
    
    # Run the bot until manually stopped
    try:
        await application.updater.start_polling()
        logger.info("Bot is running. Press Ctrl+C to stop.")
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Stopping bot...")
    finally:
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")