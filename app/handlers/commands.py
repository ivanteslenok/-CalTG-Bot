from telegram import Update
from telegram.ext import ContextTypes
from app.services.user_service import UserService
from app.services.meal_service import MealService
from app.schemas.user import UserCreate, UserUpdate
from app.utils.calorie_calc import calculate_bmr, calculate_daily_calories
from app.database import get_db
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    async for db in get_db():
        # Check if user already exists
        existing_user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if existing_user:
            await update.message.reply_text(
                f"Привет снова, {user_info.first_name}! Вы уже зарегистрированы в системе."
            )
        else:
            # Create new user with default settings
            user_create = UserCreate(
                telegram_id=telegram_id,
                username=user_info.username,
                first_name=user_info.first_name,
                last_name=user_info.last_name,
                daily_calorie_intake=0
            )
            
            new_user = await UserService.create_user(db, user_create)
            await update.message.reply_text(
                f"Привет, {user_info.first_name}! Добро пожаловать в CalTG — помощник в подсчёте калорий.\n\n"
                "Чтобы рассчитать вашу норму калорий, заполните профиль: /setprofile"
            )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Prepare profile info
        profile_info = f"👤 Профиль пользователя:\n\n"
        profile_info += f"Имя: {user.first_name or 'Не указано'} {user.last_name or ''}\n"
        profile_info += f"Пол: {user.gender or 'Не указан'}\n"
        profile_info += f"Возраст: {user.age or 'Не указан'} лет\n"
        profile_info += f"Вес: {user.weight or 'Не указан'} кг\n"
        profile_info += f"Рост: {user.height or 'Не указан'} см\n"
        profile_info += f"Уровень активности: {user.activity_level or 'Не указан'}\n"
        profile_info += f"Цель по калориям: {user.daily_calorie_goal or 'Не установлена'} ккал\n"
        profile_info += f"Напоминания: {user.reminder_time or 'Не установлено'}\n"
        
        await update.message.reply_text(profile_info)


async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /goal command: без аргумента — показать текущую цель, с числом — установить."""
    user_info = update.effective_user
    telegram_id = user_info.id

    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return

        # Чтение: /goal без аргументов — показать текущую цель
        if not context.args:
            if user.daily_calorie_goal:
                remaining = user.daily_calorie_goal - user.daily_calorie_intake
                await update.message.reply_text(
                    f"🎯 Текущая цель: {user.daily_calorie_goal} ккал/день\n"
                    f"Сегодня съедено: {user.daily_calorie_intake} ккал\n"
                    f"Осталось: {remaining} ккал"
                )
            else:
                await update.message.reply_text(
                    "Цель по калориям не установлена.\nУкажите число, например: /goal 2000"
                )
            return

        # Запись: /goal 2000
        try:
            calorie_goal = int((context.args[0] or "").strip().lower())
            if calorie_goal <= 0:
                await update.message.reply_text("Пожалуйста, укажите положительное число калорий.")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, укажите корректное число. Пример: /goal 2000")
            return

        user_update = UserUpdate(daily_calorie_goal=calorie_goal)
        updated_user = await UserService.update_user(db, telegram_id, user_update)
        remaining_calories = calorie_goal - updated_user.daily_calorie_intake
        await update.message.reply_text(
            f"Ваша дневная цель установлена на {calorie_goal} ккал.\nОсталось сегодня: {remaining_calories} ккал"
        )
        return


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /today command to show today's calorie intake"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Get today's meals
        meals = await MealService.get_today_meals(db, user.id)
        total_calories = sum(meal.calories for meal in meals)
        
        if not meals:
            await update.message.reply_text("Сегодня вы ещё не добавили ни одного приёма пищи.")
            return
        
        # Prepare today's summary
        summary = f"🍽️ Ваш рацион за сегодня ({total_calories} ккал):\n\n"
        for meal in meals:
            summary += f"• {meal.food_name} - {meal.calories} ккал"
            if meal.meal_type:
                summary += f" ({meal.meal_type})"
            summary += "\n"
        
        # Add goal information
        if user.daily_calorie_goal:
            summary += f"\n📊 Цель: {user.daily_calorie_goal} ккал\n"
            if total_calories > user.daily_calorie_goal:
                over = total_calories - user.daily_calorie_goal
                summary += f"📊 Перебор: {over} ккал"
            else:
                remaining = user.daily_calorie_goal - total_calories
                summary += f"📊 Осталось: {remaining} ккал"
        else:
            summary += f"\n📊 Цель по калориям не установлена. Используйте /goal для установки цели."
        
        await update.message.reply_text(summary)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command to show meal history"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    # Default to 7 days if no argument provided
    days = 7
    if context.args:
        try:
            days = int((context.args[0] or "").strip().lower())
            if days <= 0 or days > 30:
                await update.message.reply_text("Пожалуйста, укажите количество дней от 1 до 30.")
                return
        except ValueError:
            await update.message.reply_text("Пожалуйста, укажите корректное число дней. Пример: /history 7")
            return
    
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Get meals for the specified number of days
        meals = await MealService.get_meals_for_days(db, user.id, days)
        
        if not meals:
            await update.message.reply_text(f"За последние {days} дней у вас нет записей о приёмах пищи.")
            return
        
        # Group meals by date
        meals_by_date = {}
        for meal in meals:
            date_str = meal.timestamp.strftime("%Y-%m-%d")
            if date_str not in meals_by_date:
                meals_by_date[date_str] = []
            meals_by_date[date_str].append(meal)
        
        # Prepare history summary
        summary = f"📅 История питания за последние {days} дней:\n\n"
        for date_str, day_meals in meals_by_date.items():
            daily_total = sum(meal.calories for meal in day_meals)
            summary += f"{date_str} ({daily_total} ккал):\n"
            for meal in day_meals:
                summary += f"  • {meal.food_name} - {meal.calories} ккал"
                if meal.meal_type:
                    summary += f" ({meal.meal_type})"
                summary += "\n"
            summary += "\n"
        
        await update.message.reply_text(summary[:4000])  # Limit message length


async def reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reminder command to set reminder time"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите время для напоминаний в формате ЧЧ:ММ. Пример: /reminder 09:00")
        return
    
    time_str = (context.args[0] or "").strip().lower()
    # Basic validation for time format
    if len(time_str) != 5 or time_str[2] != ':' or not time_str.replace(':', '').isdigit():
        await update.message.reply_text("Пожалуйста, укажите время в формате ЧЧ:ММ. Пример: /reminder 09:00")
        return
    
    hours, minutes = time_str.split(':')
    if int(hours) > 23 or int(minutes) > 59:
        await update.message.reply_text("Пожалуйста, укажите корректное время в формате ЧЧ:ММ.")
        return
    
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Update user's reminder time
        user_update = UserUpdate(reminder_time=time_str)
        await UserService.update_user(db, telegram_id, user_update)
        
        await update.message.reply_text(f"Напоминания установлены на {time_str} ежедневно.")