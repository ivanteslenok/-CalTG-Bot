from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from datetime import datetime, date
from app.models.meal import MealLog
from app.models.user import User
from app.schemas.meal import MealLogCreate
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class MealService:
    @staticmethod
    async def create_meal_log(db: AsyncSession, meal_data: MealLogCreate) -> MealLog:
        """Create a new meal log entry"""
        db_meal = MealLog(**meal_data.model_dump())
        db.add(db_meal)
        await db.commit()
        await db.refresh(db_meal)
        return db_meal

    @staticmethod
    async def get_today_meals(db: AsyncSession, user_id: int) -> List[MealLog]:
        """Get all meals for today for a specific user"""
        today = date.today()
        result = await db.execute(
            select(MealLog)
            .filter(
                and_(
                    MealLog.user_id == user_id,
                    func.date(MealLog.timestamp) == today
                )
            )
            .order_by(MealLog.timestamp.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_meals_for_days(db: AsyncSession, user_id: int, days: int = 7) -> List[MealLog]:
        """Get meals for the specified number of days"""
        from datetime import timedelta
        
        start_date = date.today() - timedelta(days=days-1)
        result = await db.execute(
            select(MealLog)
            .filter(
                and_(
                    MealLog.user_id == user_id,
                    func.date(MealLog.timestamp) >= start_date
                )
            )
            .order_by(MealLog.timestamp.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_total_calories_today(db: AsyncSession, user_id: int) -> int:
        """Get total calories consumed today by user"""
        today = date.today()
        result = await db.execute(
            select(func.sum(MealLog.calories))
            .filter(
                and_(
                    MealLog.user_id == user_id,
                    func.date(MealLog.timestamp) == today
                )
            )
        )
        total_calories = result.scalar()
        return total_calories if total_calories else 0

    @staticmethod
    async def get_meal_by_id(db: AsyncSession, meal_id: int) -> Optional[MealLog]:
        """Get a specific meal by its ID"""
        result = await db.execute(select(MealLog).filter(MealLog.id == meal_id))
        return result.scalar_one_or_none()