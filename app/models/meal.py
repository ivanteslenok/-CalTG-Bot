from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class MealLog(Base):
    __tablename__ = "meal_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    food_name = Column(String, nullable=False)
    calories = Column(Integer, nullable=False)  # total calories for this meal
    protein = Column(Float, nullable=True)  # in grams
    carbs = Column(Float, nullable=True)  # in grams
    fat = Column(Float, nullable=True)  # in grams
    serving_size = Column(Float, nullable=True)  # in grams
    photo_url = Column(String, nullable=True)  # URL of uploaded photo
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MealLog(id={self.id}, user_id={self.user_id}, food_name={self.food_name}, calories={self.calories})>"