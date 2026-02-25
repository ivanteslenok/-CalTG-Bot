from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
import logging

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, bot_application: Application):
        self.scheduler = AsyncIOScheduler()
        self.application = bot_application

    def start_scheduler(self):
        """Start the reminder scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Reminder scheduler started")

    def stop_scheduler(self):
        """Stop the reminder scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Reminder scheduler stopped")

    async def schedule_user_reminder(self, user_id: int, time_str: str, message: str = "Не забудьте записать ваш приём пищи!"):
        """Schedule a daily reminder for a specific user"""
        try:
            hour, minute = map(int, time_str.split(':'))
            
            # Create a unique job ID for this user's reminder
            job_id = f"reminder_{user_id}"
            
            # Remove any existing reminder for this user
            self.scheduler.remove_job(job_id, jobstore='default')
            
            # Schedule the new reminder
            self.scheduler.add_job(
                self._send_reminder,
                CronTrigger(hour=hour, minute=minute),
                id=job_id,
                args=[user_id, message],
                replace_existing=True
            )
            
            logger.info(f"Scheduled daily reminder for user {user_id} at {time_str}")
        except Exception as e:
            logger.error(f"Error scheduling reminder for user {user_id}: {e}")

    async def _send_reminder(self, user_id: int, message: str):
        """Send reminder message to user"""
        try:
            await self.application.bot.send_message(chat_id=user_id, text=message)
            logger.info(f"Sent reminder to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending reminder to user {user_id}: {e}")

    async def cancel_user_reminder(self, user_id: int):
        """Cancel scheduled reminder for a user"""
        try:
            job_id = f"reminder_{user_id}"
            self.scheduler.remove_job(job_id, jobstore='default')
            logger.info(f"Canceled reminder for user {user_id}")
        except Exception as e:
            logger.error(f"Error canceling reminder for user {user_id}: {e}")


# Global scheduler instance
scheduler_instance = None


def schedule_reminders(bot_application: Application):
    """Initialize and return the reminder scheduler"""
    global scheduler_instance
    if scheduler_instance is None:
        scheduler_instance = ReminderScheduler(bot_application)
    return scheduler_instance