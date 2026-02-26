"""
Клиент USDA FoodData Central API для поиска продуктов и получения нутриентов.
Используется для расчёта калорий по ингредиентам (названия от OpenRouter) и как fallback по тексту.
"""
import asyncio
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
                        logger.error(
                            "CALORIES_FLOW: USDA search error: status=%s body=%s",
                            response.status,
                            body[:300],
                        )
                        return []
                    data = await response.json()
                    foods = data.get("foods") or []
                    logger.debug(
                        "CALORIES_FLOW: USDA search results for query=%r, count=%d",
                        query,
                        len(foods),
                    )
                    return foods
        except aiohttp.ClientError as e:
            logger.error("CALORIES_FLOW: USDA search request failed: %s", e)
            return []
        except Exception as e:
            logger.exception("CALORIES_FLOW: Error searching USDA: %s", e)
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
                        logger.error(
                            "CALORIES_FLOW: USDA food details error: fdc_id=%s status=%s body=%s",
                            fdc_id,
                            response.status,
                            body[:300],
                        )
                        return None
                    details = await response.json()
                    logger.debug(
                        "CALORIES_FLOW: USDA food details loaded for fdc_id=%s (has keys=%s)",
                        fdc_id,
                        list(details.keys()),
                    )
                    return details
        except aiohttp.ClientError as e:
            logger.error("CALORIES_FLOW: USDA get_food_details failed: %s", e)
            return None
        except Exception as e:
            logger.exception("CALORIES_FLOW: Error getting USDA food details: %s", e)
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

    def get_nutrients_per_100g(self, food_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Возвращает нутриенты из ответа USDA (калории, БЖУ).
        Для SR Legacy / Foundation данные в API уже на 100 г.
        """
        return self.parse_nutrition_info(food_data)

    async def search_with_fallback(self, search_names: List[str]) -> Optional[Dict[str, Any]]:
        """
        Параллельный поиск по списку названий. Возвращает нутриенты на 100 г для первого
        найденного продукта (первый непустой результат поиска по порядку названий).
        Возвращает None, если ни один поиск не дал продукта с калориями.
        """
        if not self.api_key or not search_names:
            return None
        names = [n.strip() for n in search_names if isinstance(n, str) and (n or "").strip()]
        if not names:
            return None

        logger.info("CALORIES_FLOW: USDA search_with_fallback names=%s", names)

        async def search_one(query: str) -> List[Dict[str, Any]]:
            return await self.search_foods(query, page_size=5)

        results: List[List[Dict[str, Any]]] = await asyncio.gather(
            *[search_one(name) for name in names]
        )
        for name, food_list in zip(names, results):
            if not food_list:
                logger.info(
                    "CALORIES_FLOW: USDA search_with_fallback — нет результатов для %r", name
                )
                continue
            first = food_list[0]
            fdc_id = first.get("fdcId")
            desc = first.get("description")
            if fdc_id is None:
                logger.info(
                    "CALORIES_FLOW: USDA search_with_fallback — первый результат без fdcId для %r (%r)",
                    name,
                    desc,
                )
                continue
            logger.info(
                "CALORIES_FLOW: USDA search_with_fallback — кандидат для %r: fdc_id=%s, description=%r",
                name,
                fdc_id,
                desc,
            )
            details = await self.get_food_details(int(fdc_id))
            if not details:
                continue
            nutrition = self.get_nutrients_per_100g(details)
            if nutrition.get("calories", 0) > 0 or any(
                nutrition.get(k) for k in ("protein", "carbs", "fat")
            ):
                logger.info(
                    "CALORIES_FLOW: USDA search_with_fallback — успешный матч для %r: calories=%s, "
                    "protein=%s, carbs=%s, fat=%s",
                    name,
                    nutrition.get("calories"),
                    nutrition.get("protein"),
                    nutrition.get("carbs"),
                    nutrition.get("fat"),
                )
                return nutrition
        logger.warning(
            "CALORIES_FLOW: USDA search_with_fallback — ни один вариант не дал валидных нутриентов. names=%s",
            names,
        )
        return None

    async def analyze_food_text(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Поиск по запросу, взятие первого результата и разбор нутриентов.
        Возвращает словарь в формате, совместимом с FoodAnalysisResult.from_raw.
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
        }
