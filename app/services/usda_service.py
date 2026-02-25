import aiohttp
from typing import Dict, Any, List, Optional
from app.config import Config
import logging

logger = logging.getLogger(__name__)


class USDAClient:
    def __init__(self):
        self.api_key = Config.USDA_API_KEY
        self.base_url = "https://api.nal.usda.gov/fdc/v1"
        self.headers = {"Content-Type": "application/json"}

    async def search_foods(self, query: str) -> List[Dict[str, Any]]:
        """Search for foods in the USDA database"""
        url = f"{self.base_url}/foods/search"
        params = {
            "query": query,
            "api_key": self.api_key,
            "pageSize": 10
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("foods", [])
                    else:
                        logger.error(f"USDA API error: {response.status} - {await response.text()}")
                        return []
        except Exception as e:
            logger.error(f"Error searching USDA database: {e}")
            return []

    async def get_food_details(self, fdc_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed nutrition info for a specific food item"""
        url = f"{self.base_url}/food/{fdc_id}"
        params = {"api_key": self.api_key}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"USDA API error: {response.status} - {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error getting food details: {e}")
            return None

    def parse_nutrition_info(self, food_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse nutrition information from USDA food data"""
        nutrients_map = {
            "Energy": "calories",
            "Protein": "protein",
            "Carbohydrate, by difference": "carbs",
            "Total lipid (fat)": "fat"
        }
        
        result = {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0
        }
        
        # Parse nutrient information
        food_components = food_data.get("foodComponents", [])
        for component in food_components:
            name = component.get("name", "")
            if name in nutrients_map:
                unit_name = nutrients_map[name]
                # Get the first value found for the nutrient
                if component.get("nutrients"):
                    nutrient_value = component["nutrients"][0].get("amount", 0)
                    result[unit_name] = float(nutrient_value)
        
        # Alternative nutrient parsing
        if "labelNutrients" in food_data:
            label_nutrients = food_data["labelNutrients"]
            for nutrient_name, nutrient_data in label_nutrients.items():
                if nutrient_name in nutrients_map:
                    unit_name = nutrients_map[nutrient_name]
                    result[unit_name] = float(nutrient_data.get("value", 0))
        
        # Try to get calories from energy specifically
        for nutrient in food_data.get("foodNutrients", []):
            if nutrient.get("nutrientName") == "Energy":
                result["calories"] = int(nutrient.get("value", 0))
                break
        
        return result