from telegram import Update
from telegram.ext import ContextTypes
from app.services.user_service import UserService
from app.services.meal_service import MealService
from app.services.nlp_service import NLPService
from app.services.usda_service import USDAClient
from app.schemas.meal import MealLogCreate
from app.database import get_db
from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages (food images)"""
    user_info = update.effective_user
    telegram_id = user_info.id
    
    # Get the highest resolution photo
    photo = update.message.photo[-1]  # Last element is the highest resolution
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    
    # Show loading message
    loading_msg = await update.message.reply_text("🔍 Анализирую изображение...")
    
    # Analyze the food image
    nlp_service = NLPService()
    analysis_result = await nlp_service.analyze_food_image(photo_url)
    
    if not analysis_result:
        await loading_msg.edit_text("❌ Не удалось проанализировать изображение. Попробуйте снова.")
        return
    
    # Extract food information
    food_name = analysis_result.get('food_name', 'Неизвестно')
    calories = analysis_result.get('calories', 0)
    protein = analysis_result.get('protein')
    carbs = analysis_result.get('carbs')
    fat = analysis_result.get('fat')
    serving_size = analysis_result.get('serving_size')
    meal_type = analysis_result.get('meal_type', 'snack')
    
    # Save to database
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await loading_msg.edit_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Create meal log
        meal_data = MealLogCreate(
            user_id=user.id,
            food_name=food_name,
            calories=int(calories),
            protein=protein,
            carbs=carbs,
            fat=fat,
            serving_size=serving_size,
            meal_type=meal_type,
            photo_url=photo_url
        )
        
        meal_log = await MealService.create_meal_log(db, meal_data)
        
        # Update user's daily calorie intake
        await UserService.update_calorie_intake(db, telegram_id, int(calories))
        
        # Prepare response
        response_text = f"✅ Приём пищи добавлен!\n\n"
        response_text += f"🍽️ {food_name}\n"
        response_text += f"🔥 Калории: {int(calories)} ккал"
        
        if protein is not None:
            response_text += f"\n🍗 Белки: {protein} г"
        if carbs is not None:
            response_text += f"\n🍞 Углеводы: {carbs} г"
        if fat is not None:
            response_text += f"\n🧀 Жиры: {fat} г"
        
        if serving_size is not None:
            response_text += f"\n⚖️ Размер порции: {serving_size} г"
        
        if user.daily_calorie_goal:
            remaining = user.daily_calorie_goal - user.daily_calorie_intake
            response_text += f"\n📊 Осталось сегодня: {remaining} ккал"
        
        await loading_msg.edit_text(response_text)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (food descriptions)"""
    user_info = update.effective_user
    telegram_id = user_info.id
    message_text = update.message.text
    
    # Show loading message
    loading_msg = await update.message.reply_text("🧠 Анализирую описание еды...")
    
    # Analyze the food description
    nlp_service = NLPService()
    analysis_result = await nlp_service.analyze_food_text(message_text)
    
    if not analysis_result:
        # Fallback to USDA search
        usda_client = USDAClient()
        search_results = await usda_client.search_foods(message_text)
        
        if search_results:
            # Take the first result
            first_result = search_results[0]
            fdc_id = first_result.get('fdcId')
            
            if fdc_id:
                food_details = await usda_client.get_food_details(fdc_id)
                if food_details:
                    nutrition_info = usda_client.parse_nutrition_info(food_details)
                    
                    # Use USDA info with basic food name
                    food_name = first_result.get('description', message_text)
                    analysis_result = {
                        'food_name': food_name,
                        'calories': nutrition_info.get('calories', 0),
                        'protein': nutrition_info.get('protein'),
                        'carbs': nutrition_info.get('carbs'),
                        'fat': nutrition_info.get('fat'),
                        'serving_size': None,
                        'meal_type': 'snack'
                    }
    
    if not analysis_result:
        await loading_msg.edit_text("❌ Не удалось определить информацию о еде. Попробуйте описать блюдо подробнее.")
        return
    
    # Extract food information
    food_name = analysis_result.get('food_name', message_text)
    calories = analysis_result.get('calories', 0)
    protein = analysis_result.get('protein')
    carbs = analysis_result.get('carbs')
    fat = analysis_result.get('fat')
    serving_size = analysis_result.get('serving_size')
    meal_type = analysis_result.get('meal_type', 'snack')
    
    # Save to database
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        
        if not user:
            await loading_msg.edit_text("Пожалуйста, сначала используйте /start для регистрации.")
            return
        
        # Create meal log
        meal_data = MealLogCreate(
            user_id=user.id,
            food_name=food_name,
            calories=int(calories),
            protein=protein,
            carbs=carbs,
            fat=fat,
            serving_size=serving_size,
            meal_type=meal_type
        )
        
        meal_log = await MealService.create_meal_log(db, meal_data)
        
        # Update user's daily calorie intake
        await UserService.update_calorie_intake(db, telegram_id, int(calories))
        
        # Prepare response
        response_text = f"✅ Приём пищи добавлен!\n\n"
        response_text += f"🍽️ {food_name}\n"
        response_text += f"🔥 Калории: {int(calories)} ккал"
        
        if protein is not None:
            response_text += f"\n🍗 Белки: {protein} г"
        if carbs is not None:
            response_text += f"\n🍞 Углеводы: {carbs} г"
        if fat is not None:
            response_text += f"\n🧀 Жиры: {fat} г"
        
        if serving_size is not None:
            response_text += f"\n⚖️ Размер порции: {serving_size} г"
        
        if user.daily_calorie_goal:
            remaining = user.daily_calorie_goal - user.daily_calorie_intake
            response_text += f"\n📊 Осталось сегодня: {remaining} ккал"
        
        await loading_msg.edit_text(response_text)