"""
Оркестрация определения калорийности: OpenRouter (состав + fallback калории), USDA по ингредиентам.
Успешный расчёт через USDA только если все ингредиенты найдены; иначе используются данные OpenRouter.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.schemas.analysis import FoodAnalysisResult
from app.services.nlp_service import NLPService
from app.services.usda_service import USDAClient

logger = logging.getLogger(__name__)


def _valid_ingredient(ing: Any) -> bool:
    """Проверяет наличие weight_grams и хотя бы одного названия в search_names_en."""
    if not ing or not isinstance(ing, dict):
        return False
    try:
        w = ing.get("weight_grams")
        if w is None or float(w) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    names = ing.get("search_names_en")
    if not isinstance(names, list) or not names:
        return False
    if not any(isinstance(n, str) and (n or "").strip() for n in names):
        return False
    return True


def _parse_ingredients(raw: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Извлекает и валидирует список ингредиентов из ответа OpenRouter.
    Возвращает None, если ingredients отсутствуют или хотя бы один ингредиент невалиден.
    """
    ingredients = raw.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        return None
    result = []
    for ing in ingredients:
        if not _valid_ingredient(ing):
            return None
        try:
            weight = float(ing["weight_grams"])
            names = [str(n).strip() for n in ing["search_names_en"] if isinstance(n, str) and (n or "").strip()]
        except (TypeError, ValueError, KeyError):
            return None
        if weight <= 0 or not names:
            return None
        result.append({"weight_grams": weight, "search_names_en": names})
    return result if result else None


def _scale_nutrients(nutrition_per_100g: Dict[str, Any], weight_grams: float) -> Dict[str, float]:
    """Масштабирует нутриенты с 100 г на заданный вес в граммах."""
    if weight_grams <= 0:
        return {"calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    k = weight_grams / 100.0
    return {
        "calories": int((nutrition_per_100g.get("calories") or 0) * k),
        "protein": (nutrition_per_100g.get("protein") or 0) * k,
        "carbs": (nutrition_per_100g.get("carbs") or 0) * k,
        "fat": (nutrition_per_100g.get("fat") or 0) * k,
    }


class FoodAnalysisService:
    """
    Единая точка для определения калорийности по описанию или фото.
    OpenRouter возвращает название блюда (RU), fallback калории/БЖУ и ингредиенты с граммовкой и EN-названиями.
    При успешном получении данных по всем ингредиентам из USDA — считаем калории по граммовке; иначе — fallback OpenRouter.
    """

    def __init__(
        self,
        nlp_service: Optional[NLPService] = None,
        usda_client: Optional[USDAClient] = None,
    ):
        self._nlp = nlp_service or NLPService()
        self._usda = usda_client or USDAClient()

    async def _try_usda_calculation(
        self, raw: Dict[str, Any], ingredients: List[Dict[str, Any]]
    ) -> Optional[FoodAnalysisResult]:
        """
        Пытается получить нутриенты из USDA для каждого ингредиента и рассчитать итог.
        Возвращает None при неудаче по любому ингредиенту.
        """
        nutrients_per_ingredient = await asyncio.gather(
            *[self._usda.search_with_fallback(ing["search_names_en"]) for ing in ingredients]
        )
        if any(n is None for n in nutrients_per_ingredient):
            return None
        total_calories = 0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        for ing, nut in zip(ingredients, nutrients_per_ingredient):
            scaled = _scale_nutrients(nut, ing["weight_grams"])
            total_calories += scaled["calories"]
            total_protein += scaled["protein"]
            total_carbs += scaled["carbs"]
            total_fat += scaled["fat"]
        food_name = (raw.get("food_name") or "").strip() or "Блюдо"
        serving = raw.get("serving_size")
        try:
            serving_size = float(serving) if serving is not None else None
            if serving_size is not None and serving_size <= 0:
                serving_size = None
        except (TypeError, ValueError):
            serving_size = None
        return FoodAnalysisResult(
            food_name=food_name,
            calories=total_calories,
            protein=total_protein if total_protein > 0 else None,
            carbs=total_carbs if total_carbs > 0 else None,
            fat=total_fat if total_fat > 0 else None,
            serving_size=serving_size,
        )

    async def analyze_by_image(self, image_url: str) -> Optional[FoodAnalysisResult]:
        """
        Анализ по фото. OpenRouter возвращает структуру с ингредиентами;
        при возможности калории считаются по USDA, иначе — fallback OpenRouter.
        """
        raw = await self._nlp.analyze_food_image(image_url)
        if not raw:
            return None
        ingredients = _parse_ingredients(raw)
        if ingredients:
            result = await self._try_usda_calculation(raw, ingredients)
            if result is not None:
                return result
        return FoodAnalysisResult.from_raw(raw, default_name="Блюдо по фото")

    async def analyze_by_text(self, description: str) -> Optional[FoodAnalysisResult]:
        """
        Анализ по текстовому описанию. Аналогично фото: при успехе USDA — расчёт по ингредиентам,
        иначе — fallback OpenRouter.
        """
        raw = await self._nlp.analyze_food_text(description)
        if not raw:
            return None
        ingredients = _parse_ingredients(raw)
        if ingredients:
            result = await self._try_usda_calculation(raw, ingredients)
            if result is not None:
                return result
        return FoodAnalysisResult.from_raw(raw, default_name=description.strip() or "Блюдо")
