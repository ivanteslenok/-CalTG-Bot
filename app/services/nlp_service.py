"""
Сервис анализа блюд через OpenRouter API (текст и изображения).
Используется для определения калорийности по описанию или фото.
"""
import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from app.config import Config

logger = logging.getLogger(__name__)

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)


def _parse_json_content(content: str) -> Optional[Dict[str, Any]]:
    """Парсит JSON из ответа модели. Допускает обёртку в markdown code block."""
    content = (content or "").strip()
    if not content:
        return None
    # Убираем возможный markdown ```json ... ```
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("OpenRouter returned invalid JSON: %s", e)
        return None


def _validate_analysis_dict(data: Optional[Dict[str, Any]]) -> bool:
    """
    Проверяет минимально необходимые поля ответа OpenRouter: food_name (RU), calories.
    Наличие и валидность ingredients проверяется в FoodAnalysisService при попытке USDA.
    """
    if not data or not isinstance(data, dict):
        return False
    if not isinstance(data.get("food_name"), str) or not (data.get("food_name") or "").strip():
        return False
    try:
        cal = data.get("calories")
        if cal is None:
            return False
        return int(float(cal)) >= 0
    except (TypeError, ValueError):
        return False


class NLPService:
    """Клиент OpenRouter для анализа текста и изображений еды."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = OPENROUTER_CHAT_URL,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or Config.OPENROUTER_API_KEY
        self.model = model or Config.OPENROUTER_MODEL
        self.base_url = base_url
        self.timeout = timeout

    async def analyze_food_image(self, image_url: str) -> Optional[Dict[str, Any]]:
        """
        Анализирует фото еды через OpenRouter (модель с поддержкой vision).
        image_url — публичный URL изображения (например, file_path от Telegram).
        """
        if not (self.api_key and image_url and image_url.startswith(("http://", "https://"))):
            logger.warning("analyze_food_image: missing api_key or invalid image_url")
            return None

        logger.info(
            "CALORIES_FLOW: OpenRouter image request. model=%s, image_url=%s",
            self.model,
            image_url,
        )

        prompt = (
            "You are a nutrition assistant. Analyze the food in this image and reply with exactly one JSON object (no array, no markdown, no extra text).\n\n"
            'Required keys:\n'
            '- "food_name" (string, dish name for display in Russian), "calories" (integer, total kcal estimate).\n'
            '- "protein", "carbs", "fat", "serving_size" (numbers, total grams).\n\n'
            '- "ingredients" (array): list of ingredients for lookup in a nutrition database. Each item must have:\n'
            '  - "weight_grams" (number): weight of this ingredient in grams.\n'
            '  - "search_names_en" (array of 3 strings, or at least 1): English names to search for this ingredient (e.g. ["chicken breast", "chicken fillet", "grilled chicken"]).\n\n'
            'Example (output only this JSON, nothing else):\n'
            '{"food_name": "Салат Цезарь с курицей", "calories": 450, "protein": 35, "carbs": 15, "fat": 28, "serving_size": 350, '
            '"ingredients": [{"weight_grams": 120, "search_names_en": ["chicken breast", "chicken fillet", "grilled chicken"]}, '
            '{"weight_grams": 30, "search_names_en": ["caesar dressing", "salad dressing creamy", "parmesan dressing"]}]}'
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                ) as response:
                    body = await response.text()
                    if response.status != 200:
                        logger.error(
                            "OpenRouter API error: status=%s body=%s",
                            response.status,
                            body[:500],
                        )
                        return None
                    data = json.loads(body)
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
                    if not content:
                        logger.warning("OpenRouter returned empty content")
                        return None
                    logger.debug("CALORIES_FLOW: OpenRouter raw content (image): %s", content)
                    parsed = _parse_json_content(content)
                    if not _validate_analysis_dict(parsed):
                        logger.warning(
                            "OpenRouter response for image missing required fields (food_name, calories)"
                        )
                        return None
                    logger.info(
                        "CALORIES_FLOW: OpenRouter parsed response (image): %s",
                        json.dumps(parsed, ensure_ascii=False, indent=2),
                    )
                    return parsed
        except aiohttp.ClientError as e:
            logger.error("OpenRouter request failed: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("OpenRouter response not JSON: %s", e)
            return None
        except Exception as e:
            logger.exception("Error analyzing food image: %s", e)
            return None

    async def analyze_food_text(self, food_description: str) -> Optional[Dict[str, Any]]:
        """
        Анализирует текстовое описание еды через OpenRouter.
        """
        if not self.api_key:
            logger.warning("analyze_food_text: OPENROUTER_API_KEY not set")
            return None
        description = (food_description or "").strip()
        if not description:
            return None

        logger.info(
            "CALORIES_FLOW: OpenRouter text request. model=%s, description_preview=%r",
            self.model,
            description[:120],
        )

        prompt = (
            "You are a nutrition assistant. From the food description below, estimate nutrition and reply with exactly one JSON object (no array, no markdown, no extra text).\n\n"
            f'Food description: "{description}"\n\n'
            'Required keys:\n'
            '- "food_name" (string, dish name for display in Russian), "calories" (integer, total kcal estimate).\n'
            '- "protein", "carbs", "fat", "serving_size" (numbers, total grams).\n\n'
            '- "ingredients" (array): list of ingredients for lookup in a nutrition database. Each item must have:\n'
            '  - "weight_grams" (number): weight of this ingredient in grams.\n'
            '  - "search_names_en" (array of 3 strings, or at least 1): English names to search for this ingredient (e.g. ["chicken breast", "chicken fillet", "grilled chicken"]).\n\n'
            'Example (output only this JSON, nothing else):\n'
            '{"food_name": "Овсянка с бананом", "calories": 250, "protein": 8, "carbs": 45, "fat": 5, "serving_size": 350, '
            '"ingredients": [{"weight_grams": 200, "search_names_en": ["oatmeal", "rolled oats", "oats cooked"]}, '
            '{"weight_grams": 100, "search_names_en": ["banana", "banana raw", "banana fresh"]}]}'
        )

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                ) as response:
                    body = await response.text()
                    if response.status != 200:
                        logger.error(
                            "OpenRouter API error: status=%s body=%s",
                            response.status,
                            body[:500],
                        )
                        return None
                    data = json.loads(body)
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
                    if not content:
                        logger.warning("OpenRouter returned empty content")
                        return None
                    logger.debug("CALORIES_FLOW: OpenRouter raw content (text): %s", content)
                    parsed = _parse_json_content(content)
                    if not _validate_analysis_dict(parsed):
                        logger.warning(
                            "OpenRouter response for text missing required fields (food_name, calories)"
                        )
                        return None
                    logger.info(
                        "CALORIES_FLOW: OpenRouter parsed response (text): %s",
                        json.dumps(parsed, ensure_ascii=False, indent=2),
                    )
                    return parsed
        except aiohttp.ClientError as e:
            logger.error("OpenRouter request failed: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("OpenRouter response not JSON: %s", e)
            return None
        except Exception as e:
            logger.exception("Error analyzing food text: %s", e)
            return None
