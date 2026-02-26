"""Схема результата анализа блюда (OpenRouter или USDA)."""
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List


def _clamp_float(value: Any) -> Optional[float]:
    """Приводит значение к float >= 0 или None."""
    if value is None:
        return None
    try:
        v = float(value)
        return max(0.0, v) if v >= 0 else None
    except (TypeError, ValueError):
        return None


def _clamp_int(value: Any) -> int:
    """Приводит значение к int >= 0."""
    try:
        v = int(float(value))
        return max(0, v)
    except (TypeError, ValueError):
        return 0


class OpenRouterIngredient(BaseModel):
    """Один ингредиент из ответа OpenRouter для поиска в USDA."""

    weight_grams: float = Field(..., gt=0, description="Вес ингредиента, г")
    search_names_en: List[str] = Field(..., min_length=1, description="Варианты названий на английском для поиска")

    class Config:
        extra = "ignore"


class FoodAnalysisResult(BaseModel):
    """Унифицированный результат определения калорийности по описанию или фото."""

    food_name: str = Field(..., description="Название блюда/продукта (для отображения)")
    calories: int = Field(..., ge=0, description="Калории (ккал)")
    protein: Optional[float] = Field(None, ge=0, description="Белки, г")
    carbs: Optional[float] = Field(None, ge=0, description="Углеводы, г")
    fat: Optional[float] = Field(None, ge=0, description="Жиры, г")
    serving_size: Optional[float] = Field(None, ge=0, description="Размер порции, г")

    class Config:
        extra = "ignore"

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], default_name: str = "Блюдо") -> Optional["FoodAnalysisResult"]:
        """
        Создаёт результат из сырого ответа OpenRouter или USDA.
        Возвращает None, если нет минимально необходимых полей (food_name, calories).
        """
        name = raw.get("food_name") or raw.get("description") or default_name
        if isinstance(name, str) and not name.strip():
            name = default_name
        calories = _clamp_int(raw.get("calories"))
        protein = _clamp_float(raw.get("protein"))
        carbs = _clamp_float(raw.get("carbs"))
        fat = _clamp_float(raw.get("fat"))
        serving_size = _clamp_float(raw.get("serving_size"))
        return cls(
            food_name=name.strip(),
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            serving_size=serving_size,
        )
