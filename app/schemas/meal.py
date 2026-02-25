from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MealLogBase(BaseModel):
    user_id: int
    food_name: str
    calories: int
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    serving_size: Optional[float] = None
    meal_type: Optional[str] = None
    photo_url: Optional[str] = None


class MealLogCreate(MealLogBase):
    pass


class MealLogResponse(MealLogBase):
    id: int
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True