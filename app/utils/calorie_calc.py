def calculate_bmr(gender: str, weight: float, height: int, age: int) -> float:
    """
    Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation
    BMR = 10 * weight(kg) + 6.25 * height(cm) - 5 * age(y) + s (s is +5 for males, -161 for females)
    """
    if not all([weight, height, age]):
        return 0.0
    
    if gender.lower() == 'male':
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    elif gender.lower() == 'female':
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
    else:
        # Default to male calculation if gender is unknown
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    
    return bmr


def calculate_daily_calories(bmr: float, activity_level: str) -> int:
    """
    Calculate daily calorie needs based on activity level
    """
    activity_multipliers = {
        'sedentary': 1.2,      # Little or no exercise
        'light': 1.375,        # Light exercise 1-3 days/week
        'moderate': 1.55,      # Moderate exercise 3-5 days/week
        'active': 1.725,       # Hard exercise 6-7 days/week
        'very_active': 1.9     # Very hard exercise, physical job
    }
    
    multiplier = activity_multipliers.get(activity_level, 1.2)  # Default to sedentary
    return int(bmr * multiplier)


def calculate_macros_from_calories(calories: int, goal: str = 'maintenance') -> dict:
    """
    Calculate recommended macronutrient distribution from total calories
    """
    # Default distribution: 30% protein, 40% carbs, 30% fat
    protein_ratio = 0.3
    carbs_ratio = 0.4
    fat_ratio = 0.3
    
    # Adjust based on goal
    if goal == 'weight_loss':
        protein_ratio = 0.35
        carbs_ratio = 0.3
        fat_ratio = 0.35
    elif goal == 'muscle_gain':
        protein_ratio = 0.35
        carbs_ratio = 0.45
        fat_ratio = 0.2
    
    protein_calories = calories * protein_ratio
    carbs_calories = calories * carbs_ratio
    fat_calories = calories * fat_ratio
    
    # Convert to grams (4 cal/g for protein/carbs, 9 cal/g for fat)
    protein_g = round(protein_calories / 4)
    carbs_g = round(carbs_calories / 4)
    fat_g = round(fat_calories / 9)
    
    return {
        'protein_g': protein_g,
        'carbs_g': carbs_g,
        'fat_g': fat_g,
        'protein_calories': protein_calories,
        'carbs_calories': carbs_calories,
        'fat_calories': fat_calories
    }