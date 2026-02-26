"""
Клиент USDA FoodData Central API для поиска продуктов и получения нутриентов.
Используется для расчёта калорий по ингредиентам (названия от OpenRouter) и как fallback по тексту.
Улучшения: фильтр dataType (Foundation/SR Legacy), подсказки порции для напитков,
проверка servingSize, пост-фильтрация по оценке OpenRouter.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

import aiohttp

from app.config import Config

logger = logging.getLogger(__name__)

USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

# Приоритетные типы данных: базовые продукты с данными на 100 г (меньше «шума» от брендов)
USDA_PREFERRED_DATA_TYPES = ["Foundation Foods", "SR Legacy"]
# Ключевые слова для напитков — добавляем к запросу подсказку размера порции (чашка ~240 мл)
BEVERAGE_KEYWORDS = re.compile(
    r"\b(cappuccino|latte|espresso|coffee|tea|juice|smoothie|milk|drink|beverage|cocoa|hot chocolate|soda|cola)\b",
    re.IGNORECASE,
)

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


def expand_search_names_with_portion_hints(search_names: List[str]) -> List[str]:
    """
    Для названий, похожих на напитки, добавляет варианты с размером порции (8 oz, 240 ml),
    чтобы USDA чаще возвращал «чашку», а не крупную упаковку.
    """
    result: List[str] = []
    seen: Set[str] = set()
    for name in search_names:
        name = (name or "").strip()
        if not name or name in seen:
            continue
        if BEVERAGE_KEYWORDS.search(name):
            for suffix in ("8 oz", "240 ml", "1 cup"):
                candidate = f"{name} {suffix}".strip()
                if candidate not in seen:
                    result.append(candidate)
                    seen.add(candidate)
        if name not in seen:
            result.append(name)
            seen.add(name)
    return result if result else list(search_names)


def _get_serving_size_grams(food_item: Dict[str, Any], details: Optional[Dict[str, Any]]) -> Optional[float]:
    """Извлекает размер порции в граммах из элемента поиска или деталей (Branded)."""
    # В элементах поиска иногда есть servingSize и servingSizeUnit
    for src in (food_item, details or {}):
        size = src.get("servingSize")
        unit = (src.get("servingSizeUnit") or "").strip().lower()
        if size is not None:
            try:
                val = float(size)
                if unit in ("g", "gram", "grams"):
                    return val
                if unit in ("ml", "ml (milliliter)", "milliliter"):
                    return val  # для жидкостей ~1:1 по массе
                if unit in ("oz", "fl oz", "fluid ounce"):
                    return val * 28.35
                if not unit or unit == "serving":
                    return val
            except (TypeError, ValueError):
                pass
    return None


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

    async def search_foods(
        self,
        query: str,
        page_size: int = 10,
        data_type: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Поиск продуктов по запросу. GET или POST /v1/foods/search.
        data_type: при указании используется POST и фильтр по типам (Foundation Foods, SR Legacy и т.д.).
        """
        if not (self.api_key and (query or "").strip()):
            return []
        url = f"{self.base_url}/foods/search"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                if data_type:
                    payload: Dict[str, Any] = {
                        "query": query.strip(),
                        "pageSize": page_size,
                        "dataType": data_type,
                    }
                    async with session.post(
                        url,
                        params={"api_key": self.api_key},
                        json=payload,
                        headers=self._headers,
                    ) as response:
                        body = await response.text()
                        if response.status != 200:
                            logger.error(
                                "CALORIES_FLOW: USDA search error: status=%s body=%s",
                                response.status,
                                body[:300],
                            )
                            return []
                        data = json.loads(body) if body else {}
                else:
                    params = {
                        "query": query.strip(),
                        "api_key": self.api_key,
                        "pageSize": page_size,
                    }
                    async with session.get(url, params=params, headers=self._headers) as response:
                        body = await response.text()
                        if response.status != 200:
                            logger.error(
                                "CALORIES_FLOW: USDA search error: status=%s body=%s",
                                response.status,
                                body[:300],
                            )
                            return []
                        data = json.loads(body) if body else {}
                foods = data.get("foods") or []
                logger.debug(
                    "CALORIES_FLOW: USDA search results for query=%r, dataType=%s, count=%d",
                    query,
                    data_type,
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

    async def search_with_fallback(
        self,
        search_names: List[str],
        expected_weight_grams: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Параллельный поиск по списку названий. Сначала пробует Foundation/SR Legacy,
        затем без фильтра. Для напитков добавляет варианты «8 oz», «240 ml».
        expected_weight_grams: если задан, результаты с servingSize сильно отличающимся
        (больше 2.5x или меньше 0.4x) отбрасываются.
        Возвращает нутриенты на 100 г.
        """
        if not self.api_key or not search_names:
            return None
        names = [n.strip() for n in search_names if isinstance(n, str) and (n or "").strip()]
        if not names:
            return None
        names = expand_search_names_with_portion_hints(names)
        logger.info(
            "CALORIES_FLOW: USDA search_with_fallback names=%s, expected_weight_g=%s",
            names,
            expected_weight_grams,
        )

        async def search_one(query: str, use_data_type: bool) -> List[Dict[str, Any]]:
            if use_data_type:
                return await self.search_foods(query, page_size=8, data_type=USDA_PREFERRED_DATA_TYPES)
            return await self.search_foods(query, page_size=8)

        def _serving_ratio_ok(details: Optional[Dict[str, Any]], food_item: Dict[str, Any]) -> bool:
            if expected_weight_grams is None or expected_weight_grams <= 0:
                return True
            serving_g = _get_serving_size_grams(food_item, details)
            if serving_g is None:
                return True
            ratio = serving_g / expected_weight_grams
            if ratio > 2.5 or ratio < 0.4:
                logger.info(
                    "CALORIES_FLOW: USDA отброшен по servingSize: serving_g=%.0f, expected=%.0f, ratio=%.2f",
                    serving_g,
                    expected_weight_grams,
                    ratio,
                )
                return False
            return True

        for use_preferred in (True, False):
            data_type_hint = "Foundation/SR Legacy" if use_preferred else "any"
            results: List[List[Dict[str, Any]]] = await asyncio.gather(
                *[search_one(name, use_preferred) for name in names]
            )
            for name, food_list in zip(names, results):
                if not food_list:
                    continue
                for food_item in food_list:
                    fdc_id = food_item.get("fdcId")
                    desc = food_item.get("description")
                    data_type = food_item.get("dataType") or food_item.get("data_type")
                    if fdc_id is None:
                        continue
                    details = await self.get_food_details(int(fdc_id))
                    if not details:
                        continue
                    if not _serving_ratio_ok(details, food_item):
                        continue
                    nutrition = self.get_nutrients_per_100g(details)
                    if nutrition.get("calories", 0) <= 0 and not any(
                        nutrition.get(k) for k in ("protein", "carbs", "fat")
                    ):
                        continue
                    serving_g = _get_serving_size_grams(food_item, details)
                    logger.info(
                        "CALORIES_FLOW: USDA search_with_fallback — матч для %r: fdc_id=%s, dataType=%s, "
                        "servingSize_g=%s, per100g: cal=%s, p=%s, c=%s, f=%s",
                        name,
                        fdc_id,
                        data_type,
                        serving_g,
                        nutrition.get("calories"),
                        nutrition.get("protein"),
                        nutrition.get("carbs"),
                        nutrition.get("fat"),
                    )
                    return nutrition
            if use_preferred:
                logger.info(
                    "CALORIES_FLOW: USDA нет результатов с %s, пробуем без фильтра dataType",
                    data_type_hint,
                )
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
