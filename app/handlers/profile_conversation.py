"""
Пошаговое заполнение профиля: пол, возраст, вес, рост, уровень активности.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.ext import CommandHandler, MessageHandler, filters
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserUpdate
from app.utils.calorie_calc import calculate_bmr, calculate_daily_calories
from app.database import get_db
import logging

logger = logging.getLogger(__name__)

GENDER, AGE, WEIGHT, HEIGHT, ACTIVITY = range(5)

ACTIVITY_MAP = {
    "1": "sedentary",
    "2": "light",
    "3": "moderate",
    "4": "active",
    "5": "very_active",
    "минимальный": "sedentary",
    "низкий": "light",
    "средний": "moderate",
    "высокий": "active",
    "очень высокий": "very_active",
}


async def start_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа по /start: новый пользователь — создаём и сразу в диалог профиля; иначе приветствие."""
    user_info = update.effective_user
    telegram_id = user_info.id
    async for db in get_db():
        existing = await UserService.get_user_by_telegram_id(db, telegram_id)
        if existing:
            await update.message.reply_text(
                f"Привет снова, {user_info.first_name}! Вы уже зарегистрированы. Профиль: /profile"
            )
            return ConversationHandler.END
        user_create = UserCreate(
            telegram_id=telegram_id,
            username=user_info.username,
            first_name=user_info.first_name,
            last_name=user_info.last_name,
            daily_calorie_intake=0,
        )
        await UserService.create_user(db, user_create)
        break
    context.user_data["profile"] = {}
    await update.message.reply_text(
        f"Привет, {user_info.first_name}! Добро пожаловать в CalTG — помощник в подсчёте калорий.\n\n"
        "Заполним профиль для расчёта нормы калорий. В любой момент можно отменить: /cancel\n\n"
        "Укажите пол: м или ж (можно male/female)."
    )
    return GENDER


async def start_setprofile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа по /setprofile: проверяем пользователя и спрашиваем пол."""
    telegram_id = update.effective_user.id
    context.user_data["profile"] = {}
    async for db in get_db():
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if not user:
            await update.message.reply_text("Сначала используйте /start для регистрации.")
            return ConversationHandler.END
    await update.message.reply_text(
        "Заполним ваш профиль для расчёта нормы калорий. В любой момент можно отменить: /cancel\n\n"
        "Укажите пол: м или ж (можно male/female)."
    )
    return GENDER


async def receive_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip().lower()
    if text in ("м", "male", "мужской"):
        context.user_data["profile"]["gender"] = "male"
    elif text in ("ж", "female", "женский", "f"):
        context.user_data["profile"]["gender"] = "female"
    else:
        await update.message.reply_text("Введите м или ж (либо male/female).")
        return GENDER
    await update.message.reply_text("Укажите возраст (полных лет), например: 30")
    return AGE


async def receive_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int((update.message.text or "").strip().lower())
        if age < 10 or age > 120:
            await update.message.reply_text("Укажите возраст от 10 до 120 лет.")
            return AGE
    except ValueError:
        await update.message.reply_text("Введите число, например: 30")
        return AGE
    context.user_data["profile"]["age"] = age
    await update.message.reply_text("Укажите вес в кг, например: 70 или 72.5")
    return WEIGHT


async def receive_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float((update.message.text or "").strip().lower().replace(",", "."))
        if weight < 30 or weight > 300:
            await update.message.reply_text("Укажите вес от 30 до 300 кг.")
            return WEIGHT
    except ValueError:
        await update.message.reply_text("Введите число, например: 70")
        return WEIGHT
    context.user_data["profile"]["weight"] = weight
    await update.message.reply_text("Укажите рост в см, например: 175")
    return HEIGHT


async def receive_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        height = int((update.message.text or "").strip().lower())
        if height < 100 or height > 250:
            await update.message.reply_text("Укажите рост от 100 до 250 см.")
            return HEIGHT
    except ValueError:
        await update.message.reply_text("Введите целое число, например: 175")
        return HEIGHT
    context.user_data["profile"]["height"] = height
    await update.message.reply_text(
        "Укажите уровень активности:\n"
        "1 — минимальный (почти нет движения)\n"
        "2 — низкий (1–3 дня в неделю)\n"
        "3 — средний (3–5 дней)\n"
        "4 — высокий (6–7 дней)\n"
        "5 — очень высокий (спорт/физическая работа)"
    )
    return ACTIVITY


async def receive_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip().lower()
    activity = ACTIVITY_MAP.get(text)
    if not activity:
        await update.message.reply_text("Введите число от 1 до 5 или название уровня (например: средний).")
        return ACTIVITY
    context.user_data["profile"]["activity_level"] = activity

    telegram_id = update.effective_user.id
    profile = context.user_data["profile"]
    user_update = UserUpdate(
        gender=profile.get("gender"),
        age=profile.get("age"),
        weight=profile.get("weight"),
        height=profile.get("height"),
        activity_level=profile.get("activity_level"),
    )

    async for db in get_db():
        await UserService.update_user(db, telegram_id, user_update)
        user = await UserService.get_user_by_telegram_id(db, telegram_id)
        break
    else:
        user = None

    # Рассчитать рекомендуемую норму калорий
    msg = "✅ Профиль сохранён.\n\n"
    msg += f"Пол: {'мужской' if profile.get('gender') == 'male' else 'женский'}\n"
    msg += f"Возраст: {profile.get('age')} лет\n"
    msg += f"Вес: {profile.get('weight')} кг\n"
    msg += f"Рост: {profile.get('height')} см\n"
    msg += f"Активность: {profile.get('activity_level')}\n\n"

    if user and all([user.gender, user.age, user.weight, user.height, user.activity_level]):
        bmr = calculate_bmr(user.gender, user.weight, user.height, user.age)
        recommended = calculate_daily_calories(bmr, user.activity_level)
        msg += f"📊 Рекомендуемая дневная норма: ~{recommended} ккал.\n"
        msg += f"Установить цель: /goal {recommended}"
    await update.message.reply_text(msg)
    context.user_data.pop("profile", None)
    return ConversationHandler.END


async def cancel_setprofile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("profile", None)
    await update.message.reply_text("Заполнение профиля отменено.")
    return ConversationHandler.END


def build_profile_conversation_handler(*, persistent: bool = False):
    """Создаёт ConversationHandler для заполнения профиля.
    persistent=True допустим только если у Application настроена persistence (например PERSISTENCE_PATH).
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start_from_start),
            CommandHandler("setprofile", start_setprofile),
        ],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_height)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_activity)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setprofile)],
        name="profile_fill",
        persistent=persistent,
    )
