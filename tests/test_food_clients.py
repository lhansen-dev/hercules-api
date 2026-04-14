from hercules_api.models.enums import FoodSource
from hercules_api.services.food_clients import (
    _off_product_to_candidate,
    _parse_off_serving_grams,
    _usda_food_to_candidate,
)


def test_parse_off_serving_grams_extracts_numeric_grams() -> None:
    assert _parse_off_serving_grams("30 g") == 30.0
    assert _parse_off_serving_grams("1 slice (27g)") == 27.0
    assert _parse_off_serving_grams("240 ml") is None
    assert _parse_off_serving_grams(None) is None


def test_off_candidate_scales_per_100g_to_serving() -> None:
    product = {
        "code": "1234567890123",
        "product_name": "Example Bread",
        "brands": "Acme, OtherBrand",
        "serving_size": "50 g",
        "nutriments": {
            "energy-kcal_100g": 250.0,
            "proteins_100g": 8.0,
            "carbohydrates_100g": 40.0,
            "fat_100g": 3.0,
            "fiber_100g": 2.0,
            "sugars_100g": 5.0,
            "sodium_100g": 0.5,  # grams
        },
    }
    cand = _off_product_to_candidate(product)
    assert cand is not None
    assert cand.source == FoodSource.OFF
    assert cand.barcode == "1234567890123"
    assert cand.name == "Example Bread"
    assert cand.brand == "Acme"  # only first brand retained
    assert cand.serving_size_g == 50.0
    # Scaled from per-100g to per-50g:
    assert cand.calories == 125.0
    assert cand.protein_g == 4.0
    assert cand.carbs_g == 20.0
    assert cand.fat_g == 1.5
    assert cand.fiber_g == 1.0
    assert cand.sugar_g == 2.5
    # 0.5g per 100g -> 0.25g per 50g -> 250mg
    assert cand.sodium_mg == 250.0


def test_off_candidate_defaults_to_100g_serving_when_unparseable() -> None:
    product = {
        "code": "000",
        "product_name": "Generic Item",
        "nutriments": {
            "energy-kcal_100g": 100.0,
            "proteins_100g": 5.0,
            "carbohydrates_100g": 10.0,
            "fat_100g": 2.0,
        },
    }
    cand = _off_product_to_candidate(product)
    assert cand is not None
    assert cand.serving_size_g == 100.0
    assert cand.calories == 100.0


def test_off_candidate_skipped_when_no_kcal() -> None:
    product = {"code": "x", "product_name": "no-macros", "nutriments": {}}
    assert _off_product_to_candidate(product) is None


def test_usda_candidate_parses_branded_food() -> None:
    food = {
        "fdcId": 123,
        "description": "Protein Bar",
        "brandOwner": "Brandco",
        "gtinUpc": "999",
        "servingSize": 60,
        "servingSizeUnit": "g",
        "householdServingFullText": "1 bar",
        "foodNutrients": [
            {"nutrientId": 1008, "value": 200.0},  # kcal per 100g
            {"nutrientId": 1003, "value": 20.0},
            {"nutrientId": 1005, "value": 25.0},
            {"nutrientId": 1004, "value": 5.0},
            {"nutrientId": 1093, "value": 150.0},  # sodium mg
        ],
    }
    cand = _usda_food_to_candidate(food)
    assert cand is not None
    assert cand.source == FoodSource.USDA
    assert cand.source_id == "123"
    assert cand.barcode == "999"
    assert cand.name == "Protein Bar"
    assert cand.serving_size_g == 60.0
    # Scaled to per-60g:
    assert cand.calories == 120.0
    assert cand.protein_g == 12.0
    assert cand.carbs_g == 15.0
    assert cand.fat_g == 3.0
    assert cand.sodium_mg == 90.0


def test_usda_candidate_falls_back_to_100g() -> None:
    food = {
        "fdcId": 1,
        "description": "Generic",
        "servingSize": 1,
        "servingSizeUnit": "cup",  # unsupported unit → fall back
        "foodNutrients": [{"nutrientId": 1008, "value": 200.0}],
    }
    cand = _usda_food_to_candidate(food)
    assert cand is not None
    assert cand.serving_size_g == 100.0
    assert cand.calories == 200.0
