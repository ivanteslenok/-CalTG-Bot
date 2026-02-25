"""
Обработчики сообщений: фото и текст для добавления приёмов пищи.
Определение калорийности через FoodAnalysisService (OpenRouter + USDA fallback).
"""
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.database import get_db
from app.schemas.analysis import FoodAnalysisResult
from app.schemas.meal import MealLogCreate
from app.services.food_analysis_service import FoodAnalysisService
from app.services.meal_service import MealService
from app.services.user_service import UserService, is_profile_complete

logger = logging.getLogger(__name__)


def _format_meal_response(analysis: FoodAnalysisResult, daily_goal: Optional[int], daily_intake: int) -> str:
    """Формирует текст ответа пользователю после добавления приёма пищи."""
    lines = [
        "✅ Приём пищи добавлен!",
        "",
        f"🍽️ {analysis.food_name}",
        f"🔥 Калории: {analysis.calories} ккал",
    ]
    if analysis.protein is not None:
        lines.append(f"🍗 Белки: {analysis.protein} г")
    if analysis.carbs is not None:
        lines.append(f"🍞 Углеводы: {analysis.carbs} г")
    if analysis.fat is not None:
        lines.append(f"🧀 Жиры: {analysis.fat} г")
    if analysis.serving_size is not None:
        lines.append(f"⚖️ Размер порции: {analysis.serving_size} г")
    if daily_goal is not None:
        remaining = daily_goal - daily_intake
        lines.append(f"📊 Осталось сегодня: {remaining} ккал")
    return "\n".join(lines)


async def _save_meal_and_reply(
    telegram_id: int,
    analysis: FoodAnalysisResult,
    loading_msg,
    photo_url: Optional[str] = None,
) -> None:
    """
    Сохраняет приём пищи в БД, обновляет дневную сумму калорий и редактирует loading_msg.
    Использует актуальные данные пользователя после update_calorie_intake для корректного «осталось».
    """
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if not user:
            await loading_msg.edit_text("Пожалуйста, сначала используйте /start для регистрации.")
            return

        meal_data = MealLogCreate(
            user_id=user.id,
            food_name=analysis.food_name,
            calories=analysis.calories,
            protein=analysis.protein,
            carbs=analysis.carbs,
            fat=analysis.fat,
            serving_size=analysis.serving_size,
            meal_type=analysis.meal_type,
            photo_url=photo_url,
        )
        await MealService.create_meal_log(db, meal_data)
        updated_user = await UserService.update_calorie_intake(db, telegram_id, analysis.calories)
        daily_intake = updated_user.daily_calorie_intake if updated_user else user.daily_calorie_intake + analysis.calories
        daily_goal = (updated_user or user).daily_calorie_goal
        response_text = _format_meal_response(analysis, daily_goal, daily_intake)
        await loading_msg.edit_text(response_text)
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка фото: определение калорийности по изображению (OpenRouter vision)."""
    telegram_id = update.effective_user.id

    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        if not is_profile_complete(user):
            await update.message.reply_text(
                "Сначала заполните профиль (пол, возраст, вес, рост, активность): /setprofile\n"
                "Или отмените текущий ввод: /cancel"
            )
            return
        break

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    loading_msg = await update.message.reply_text("🔍 Анализирую изображение...")

    service = FoodAnalysisService()
    analysis = await service.analyze_by_image(photo_url)

    if not analysis:
        await loading_msg.edit_text("❌ Не удалось проанализировать изображение. Попробуйте снова.")
        return

    await _save_meal_and_reply(telegram_id, analysis, loading_msg, photo_url=photo_url)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текста: определение калорийности по описанию (OpenRouter, fallback USDA)."""
    telegram_id = update.effective_user.id

    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if not user:
            await update.message.reply_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        if not is_profile_complete(user):
            await update.message.reply_text(
                "Сначала заполните профиль (пол, возраст, вес, рост, активность): /setprofile\n"
                "Или отмените текущий ввод: /cancel"
            )
            return
        break

    message_text = (update.message.text or "").strip().lower()
    loading_msg = await update.message.reply_text("🧠 Анализирую описание еды...")

    service = FoodAnalysisService()
    analysis = await service.analyze_by_text(message_text)

    if not analysis:
        await loading_msg.edit_text(
            "❌ Не удалось определить информацию о еде. Попробуйте описать блюдо подробнее."
        )
        return

    await _save_meal_and_reply(telegram_id, analysis, loading_msg)
