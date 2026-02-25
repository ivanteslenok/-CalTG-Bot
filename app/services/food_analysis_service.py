"""
Оркестрация определения калорийности: OpenRouter (текст/фото) и fallback USDA (только текст).
"""
import logging
from typing import Optional

from app.schemas.analysis import FoodAnalysisResult
from app.services.nlp_service import NLPService
from app.services.usda_service import USDAClient

logger = logging.getLogger(__name__)


class FoodAnalysisService:
    """
    Единая точка для определения калорийности блюда по описанию или фото.
    - По фото: только OpenRouter (модель с vision).
    - По тексту: OpenRouter, при неудаче — USDA.
    """

    def __init__(
        self,
        nlp_service: Optional[NLPService] = None,
        usda_client: Optional[USDAClient] = None,
    ):
        self._nlp = nlp_service or NLPService()
        self._usda = usda_client or USDAClient()

    async def analyze_by_image(self, image_url: str) -> Optional[FoodAnalysisResult]:
        """
        Анализ по фото. Только OpenRouter (USDA не поддерживает изображения).
        image_url должен быть публичным (например, file_path от Telegram).
        """
        raw = await self._nlp.analyze_food_image(image_url)
        if not raw:
            return None
        return FoodAnalysisResult.from_raw(raw, default_name="Блюдо по фото")

    async def analyze_by_text(self, description: str) -> Optional[FoodAnalysisResult]:
        """
        Анализ по текстовому описанию. Сначала OpenRouter, при неудаче — USDA.
        """
        raw = await self._nlp.analyze_food_text(description)
        if raw:
            return FoodAnalysisResult.from_raw(raw, default_name=description.strip() or "Блюдо")
        raw_usda = await self._usda.analyze_food_text(description)
        if not raw_usda:
            return None
        return FoodAnalysisResult.from_raw(raw_usda, default_name=description.strip() or "Блюдо")
