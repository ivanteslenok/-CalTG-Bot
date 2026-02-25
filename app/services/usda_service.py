"""
Клиент USDA FoodData Central API для поиска продуктов и получения нутриентов.
Используется как fallback при определении калорийности по текстовому описанию.
"""
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from app.config import Config

logger = logging.getLogger(__name__)

USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

# Маппинг имён нутриентов USDA -> наши поля (поддержка разных форматов ответа API)
NUTRIENT_NAME_TO_FIELD = {
    "energy": "calories",
    "protein": "protein",
    "carbohydrate, by difference": "carbs",
    "carbohydrates": "carbs",
    "total lipid (fat)": "fat",
    "fat": "fat",
}


def _float_value(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int_calories(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


class USDAClient:
    """Клиент USDA FDC API v1."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = USDA_BASE_URL,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or Config.USDA_API_KEY
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {"Content-Type": "application/json"}

    async def search_foods(self, query: str, page_size: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск продуктов по запросу. GET /v1/foods/search.
        Возвращает список элементов с полями fdcId, description и др.
        """
        if not (self.api_key and (query or "").strip()):
            return []
        url = f"{self.base_url}/foods/search"
        params = {"query": query.strip(), "api_key": self.api_key, "pageSize": page_size}
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params=params, headers=self._headers) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.error("USDA API search error: status=%s body=%s", response.status, body[:300])
                        return []
                    data = await response.json()
                    return data.get("foods") or []
        except aiohttp.ClientError as e:
            logger.error("USDA search request failed: %s", e)
            return []
        except Exception as e:
            logger.exception("Error searching USDA: %s", e)
            return []

    async def get_food_details(self, fdc_id: int) -> Optional[Dict[str, Any]]:
        """Получение деталей продукта по FDC ID. GET /v1/food/{fdcId}."""
        if not self.api_key or fdc_id is None:
            return None
        url = f"{self.base_url}/food/{fdc_id}"
        params = {"api_key": self.api_key}
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params=params, headers=self._headers) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.error("USDA API food details error: status=%s body=%s", response.status, body[:300])
                        return None
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error("USDA get_food_details failed: %s", e)
            return None
        except Exception as e:
            logger.exception("Error getting USDA food details: %s", e)
            return None

    def parse_nutrition_info(self, food_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает калории и БЖУ из ответа USDA.
        Учитывает форматы: foodNutrients, labelNutrients, foodComponents.
        Калории в USDA приходят в ккал (Energy).
        """
        result = {"calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

        # 1) foodNutrients — основной формат FDC API (массив с nutrient.name или nutrientName и amount/value)
        for item in food_data.get("foodNutrients") or []:
            name = (item.get("nutrient") or {}).get("name") or item.get("nutrientName") or ""
            name_lower = name.lower().strip()
            if name_lower not in NUTRIENT_NAME_TO_FIELD:
                continue
            field = NUTRIENT_NAME_TO_FIELD[name_lower]
            amount = item.get("amount") is not None and item.get("amount") or item.get("value")
            if amount is None:
                continue
            if field == "calories":
                result["calories"] = _int_calories(amount)
            else:
                result[field] = _float_value(amount)

        # 2) labelNutrients — заполняем только если ещё не задано (foodNutrients приоритетнее)
        for nutrient_name, nutrient_data in (food_data.get("labelNutrients") or {}).items():
            if not isinstance(nutrient_data, dict):
                continue
            name_lower = (nutrient_name or "").lower().strip()
            if name_lower not in NUTRIENT_NAME_TO_FIELD:
                continue
            field = NUTRIENT_NAME_TO_FIELD[name_lower]
            value = nutrient_data.get("value")
            if value is None:
                continue
            if field == "calories" and result["calories"] == 0:
                result["calories"] = _int_calories(value)
            elif field != "calories" and result[field] == 0:
                result[field] = _float_value(value)

        # 3) foodComponents — заполняем только если ещё не задано
        for component in food_data.get("foodComponents") or []:
            name = (component.get("name") or "").strip()
            name_lower = name.lower()
            if name_lower not in NUTRIENT_NAME_TO_FIELD:
                continue
            field = NUTRIENT_NAME_TO_FIELD[name_lower]
            nutrients = component.get("nutrients") or []
            amount = nutrients[0].get("amount") if nutrients else None
            if amount is None:
                continue
            if field == "calories" and result["calories"] == 0:
                result["calories"] = _int_calories(amount)
            elif field != "calories" and result[field] == 0:
                result[field] = _float_value(amount)

        return result

    async def analyze_food_text(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Поиск по запросу, взятие первого результата и разбор нутриентов.
        Возвращает словарь в формате, совместимом с FoodAnalysisResult.from_raw:
        food_name, calories, protein, carbs, fat, serving_size, meal_type.
        """
        foods = await self.search_foods(query, page_size=5)
        if not foods:
            return None
        first = foods[0]
        fdc_id = first.get("fdcId")
        if fdc_id is None:
            return None
        details = await self.get_food_details(int(fdc_id))
        if not details:
            return None
        nutrition = self.parse_nutrition_info(details)
        food_name = first.get("description") or query.strip() or "Продукт"
        return {
            "food_name": food_name,
            "calories": nutrition.get("calories", 0),
            "protein": nutrition.get("protein") or None,
            "carbs": nutrition.get("carbs") or None,
            "fat": nutrition.get("fat") or None,
            "serving_size": None,
            "meal_type": "snack",
        }
