from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def is_profile_complete(user: Optional[User]) -> bool:
    """Профиль считается заполненным, если указаны пол, возраст, вес, рост и активность."""
    if not user:
        return False
    return bool(
        user.gender and str(user.gender).strip()
        and user.age is not None
        and user.weight is not None
        and user.height is not None
        and user.activity_level and str(user.activity_level).strip()
    )


class UserService:
    @staticmethod
    async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID"""
        result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """Create a new user"""
        db_user = User(**user_data.model_dump())
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    @staticmethod
    async def update_user(db: AsyncSession, telegram_id: int, user_update: UserUpdate) -> Optional[User]:
        """Update user information"""
        db_user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if db_user:
            for key, value in user_update.model_dump(exclude_unset=True).items():
                setattr(db_user, key, value)
            await db.commit()
            await db.refresh(db_user)
        return db_user

    @staticmethod
    async def update_calorie_intake(db: AsyncSession, telegram_id: int, calorie_amount: int) -> Optional[User]:
        """Update daily calorie intake for user"""
        db_user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if db_user:
            db_user.daily_calorie_intake += calorie_amount
            if db_user.daily_calorie_goal:
                db_user.daily_remaining_calories = db_user.daily_calorie_goal - db_user.daily_calorie_intake
            await db.commit()
            await db.refresh(db_user)
        return db_user

    @staticmethod
    async def reset_daily_calories(db: AsyncSession, telegram_id: int) -> Optional[User]:
        """Reset daily calorie counters for a new day"""
        db_user = await UserService.get_user_by_telegram_id(db, telegram_id)
        if db_user:
            db_user.daily_calorie_intake = 0
            if db_user.daily_calorie_goal:
                db_user.daily_remaining_calories = db_user.daily_calorie_goal
            await db.commit()
            await db.refresh(db_user)
        return db_user