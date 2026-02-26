"""
Оркестрация определения калорийности: единственный источник — OpenRouter (калории, БЖУ из ответа модели).
Расчёт через USDA отключён (код сохранён для возможного включения позже).
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from app.schemas.analysis import FoodAnalysisResult
from app.services.nlp_service import NLPService
from app.services.usda_service import USDAClient

logger = logging.getLogger(__name__)


def _pretty(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return repr(data)


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
    Калории и БЖУ берутся только из ответа OpenRouter. Расчёт через USDA отключён.
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
        logger.info(
            "CALORIES_FLOW: USDA расчёт по ингредиентам. Блюдо=%r, ингредиентов=%d",
            raw.get("food_name"),
            len(ingredients),
        )
        logger.debug("CALORIES_FLOW: ингредиенты от OpenRouter:\n%s", _pretty(ingredients))

        nutrients_per_ingredient = await asyncio.gather(
            *[
                self._usda.search_with_fallback(
                    ing["search_names_en"],
                    expected_weight_grams=ing["weight_grams"],
                )
                for ing in ingredients
            ]
        )
        if any(n is None for n in nutrients_per_ingredient):
            failed_indexes = [i for i, n in enumerate(nutrients_per_ingredient) if n is None]
            logger.warning(
                "CALORIES_FLOW: не удалось получить данные USDA по всем ингредиентам, "
                "fallback на OpenRouter. Индексы проблемных ингредиентов: %s",
                failed_indexes,
            )
            return None
        total_calories = 0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        for idx, (ing, nut) in enumerate(zip(ingredients, nutrients_per_ingredient)):
            scaled = _scale_nutrients(nut, ing["weight_grams"])
            total_calories += scaled["calories"]
            total_protein += scaled["protein"]
            total_carbs += scaled["carbs"]
            total_fat += scaled["fat"]
            logger.info(
                "CALORIES_FLOW: ингредиент #%d, вес=%.1f г, имена=%s, "
                "USDA per100g=%s, scaled=%s",
                idx,
                ing["weight_grams"],
                ing["search_names_en"],
                nut,
                scaled,
            )
        food_name = (raw.get("food_name") or "").strip() or "Блюдо"
        serving = raw.get("serving_size")
        try:
            serving_size = float(serving) if serving is not None else None
            if serving_size is not None and serving_size <= 0:
                serving_size = None
        except (TypeError, ValueError):
            serving_size = None

        openrouter_cal = None
        try:
            oc = raw.get("calories")
            if oc is not None:
                openrouter_cal = int(float(oc))
        except (TypeError, ValueError):
            pass

        if openrouter_cal is not None and openrouter_cal > 0:
            ratio = total_calories / openrouter_cal
            if ratio > 2.5 or ratio < 0.4:
                logger.warning(
                    "CALORIES_FLOW: итог USDA отклоняется от оценки OpenRouter: USDA=%d, OpenRouter=%d, "
                    "ratio=%.2f — используем fallback OpenRouter",
                    total_calories,
                    openrouter_cal,
                    ratio,
                )
                return None

        logger.info(
            "CALORIES_FLOW: итог по USDA: блюдо=%r, calories=%d, protein=%.2f, carbs=%.2f, fat=%.2f, "
            "serving_size=%s (OpenRouter оценка: %s)",
            food_name,
            total_calories,
            total_protein,
            total_carbs,
            total_fat,
            serving_size,
            openrouter_cal,
        )

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
        Анализ по фото. Калории считаются только по ответу OpenRouter (USDA расчёт отключён).
        """
        logger.info("CALORIES_FLOW: старт анализа по фото. image_url=%s", image_url)
        raw = await self._nlp.analyze_food_image(image_url)
        if not raw:
            logger.warning("CALORIES_FLOW: OpenRouter не вернул данных для фото")
            return None
        logger.debug("CALORIES_FLOW: сырые данные OpenRouter по фото:\n%s", _pretty(raw))
        result = FoodAnalysisResult.from_raw(raw, default_name="Блюдо по фото")
        logger.info(
            "CALORIES_FLOW: итог по фото (OpenRouter): блюдо=%r, calories=%d",
            result.food_name,
            result.calories,
        )
        return result

    async def analyze_by_text(self, description: str) -> Optional[FoodAnalysisResult]:
        """
        Анализ по текстовому описанию. Калории считаются только по ответу OpenRouter (USDA расчёт отключён).
        """
        logger.info(
            "CALORIES_FLOW: старт анализа по тексту. description_preview=%r",
            (description or "")[:120],
        )
        raw = await self._nlp.analyze_food_text(description)
        if not raw:
            logger.warning("CALORIES_FLOW: OpenRouter не вернул данных для текстового описания")
            return None
        logger.debug("CALORIES_FLOW: сырые данные OpenRouter по тексту:\n%s", _pretty(raw))
        result = FoodAnalysisResult.from_raw(raw, default_name=description.strip() or "Блюдо")
        logger.info(
            "CALORIES_FLOW: итог по тексту (OpenRouter): блюдо=%r, calories=%d",
            result.food_name,
            result.calories,
        )
        return result
