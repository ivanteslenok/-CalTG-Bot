import aiohttp
import json
from typing import Dict, Any, Optional
from app.config import Config
import logging

logger = logging.getLogger(__name__)


class NLPService:
    def __init__(self):
        self.api_key = Config.OPENROUTER_API_KEY
        self.model = Config.OPENROUTER_MODEL
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def analyze_food_image(self, image_url: str) -> Optional[Dict[str, Any]]:
        """Analyze food image using OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = """
        Analyze this food image and provide the following information in JSON format:
        - food_name: Name of the food/dish
        - calories: Estimated total calories
        - protein: Estimated protein in grams (if possible)
        - carbs: Estimated carbohydrates in grams (if possible)
        - fat: Estimated fat in grams (if possible)
        - serving_size: Estimated serving size in grams (if possible)
        - meal_type: Type of meal (breakfast, lunch, dinner, snack)
        
        Respond only with the JSON object, no other text.
        """
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        return json.loads(content)
                    else:
                        logger.error(f"OpenRouter API error: {response.status} - {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error analyzing food image: {e}")
            return None

    async def analyze_food_text(self, food_description: str) -> Optional[Dict[str, Any]]:
        """Analyze food description using OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
        Analyze this food description: '{food_description}'
        
        Provide the following information in JSON format:
        - food_name: Name of the food/dish
        - calories: Estimated total calories
        - protein: Estimated protein in grams (if possible)
        - carbs: Estimated carbohydrates in grams (if possible)
        - fat: Estimated fat in grams (if possible)
        - serving_size: Estimated serving size in grams (if possible)
        - meal_type: Type of meal (breakfast, lunch, dinner, snack)
        
        Respond only with the JSON object, no other text.
        """
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        return json.loads(content)
                    else:
                        logger.error(f"OpenRouter API error: {response.status} - {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error analyzing food text: {e}")
            return None