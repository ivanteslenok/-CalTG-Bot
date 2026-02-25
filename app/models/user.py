from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    gender = Column(String(10), nullable=True)  # male/female
    age = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True)  # in kg
    height = Column(Integer, nullable=True)  # in cm
    activity_level = Column(String(20), nullable=True)  # sedentary, light, moderate, active, very_active
    daily_calorie_goal = Column(Integer, nullable=True)
    daily_calorie_intake = Column(Integer, default=0)  # calories consumed today
    daily_remaining_calories = Column(Integer, nullable=True)  # calculated field
    reminder_time = Column(String(10), nullable=True)  # HH:MM format
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"