from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[int] = None
    activity_level: Optional[str] = None
    daily_calorie_goal: Optional[int] = None
    daily_calorie_intake: Optional[int] = 0
    daily_remaining_calories: Optional[int] = None
    reminder_time: Optional[str] = None
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    gender: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[int] = None
    activity_level: Optional[str] = None
    daily_calorie_goal: Optional[int] = None
    reminder_time: Optional[str] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True