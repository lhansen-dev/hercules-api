"""Async clients for Open Food Facts and USDA FoodData Central.

Both clients normalize their responses to FoodCandidate so the resolver can
treat all sources uniformly. Per-100g macros are scaled to per-serving when a
serving size is known; otherwise serving_size_g defaults to 100 and macros are
stored as per-100g.
"""

from __future__ import annotations

import logging
import re

import httpx

from hercules_api.models.enums import FoodSource
from hercules_api.schemas.food import FoodCandidate

log = logging.getLogger(__name__)

OFF_BASE_URL = "https://world.openfoodfacts.org"
USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# USDA nutrient ids (stable across datasets).
USDA_NUTRIENT_ENERGY_KCAL = 1008
USDA_NUTRIENT_PROTEIN = 1003
USDA_NUTRIENT_CARBS = 1005
USDA_NUTRIENT_FAT = 1004
USDA_NUTRIENT_FIBER = 1079
USDA_NUTRIENT_SUGAR = 2000
USDA_NUTRIENT_SODIUM = 1093

_SERVING_GRAMS_RE = re.compile(r"([\d.]+)\s*g", re.IGNORECASE)


def _parse_off_serving_grams(serving_size: str | None) -> float | None:
    """OFF's serving_size is free text like '30 g' or '1 slice (27g)'. Grab the
    first gram figure if any; return None otherwise."""
    if not serving_size:
        return None
    match = _SERVING_GRAMS_RE.search(serving_size)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _scale(value: float | None, factor: float) -> float | None:
    return None if value is None else value * factor


def _off_product_to_candidate(product: dict) -> FoodCandidate | None:
    name = product.get("product_name") or product.get("generic_name")
    if not name:
        return None
    nutr = product.get("nutriments") or {}

    # Required macros per 100g.
    kcal_100 = nutr.get("energy-kcal_100g")
    if kcal_100 is None:
        # Fall back to energy_100g which may be in kJ; skip if ambiguous.
        return None
    protein_100 = nutr.get("proteins_100g", 0.0) or 0.0
    carbs_100 = nutr.get("carbohydrates_100g", 0.0) or 0.0
    fat_100 = nutr.get("fat_100g", 0.0) or 0.0
    fiber_100 = nutr.get("fiber_100g")
    sugar_100 = nutr.get("sugars_100g")
    sodium_100_g = nutr.get("sodium_100g")  # grams in OFF

    serving_grams = _parse_off_serving_grams(product.get("serving_size"))
    size_g = serving_grams if serving_grams else 100.0
    factor = size_g / 100.0

    return FoodCandidate(
        source=FoodSource.OFF,
        source_id=product.get("code"),
        barcode=product.get("code"),
        name=name.strip(),
        brand=(product.get("brands") or "").split(",")[0].strip() or None,
        serving_size_g=size_g,
        serving_display=product.get("serving_size"),
        calories=float(kcal_100) * factor,
        protein_g=float(protein_100) * factor,
        carbs_g=float(carbs_100) * factor,
        fat_g=float(fat_100) * factor,
        fiber_g=_scale(fiber_100, factor),
        sodium_mg=_scale(sodium_100_g, factor * 1000.0),  # g → mg
        sugar_g=_scale(sugar_100, factor),
    )


class OpenFoodFactsClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_by_barcode(self, barcode: str) -> FoodCandidate | None:
        url = f"{OFF_BASE_URL}/api/v2/product/{barcode}.json"
        try:
            resp = await self._client.get(url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("OFF barcode lookup failed for %s: %s", barcode, e)
            return None
        body = resp.json()
        if body.get("status") != 1:
            return None
        product = body.get("product") or {}
        return _off_product_to_candidate(product)

    async def search(self, query: str, limit: int = 10) -> list[FoodCandidate]:
        url = f"{OFF_BASE_URL}/cgi/search.pl"
        params = {
            "search_terms": query,
            "json": 1,
            "page_size": limit,
            "fields": "code,product_name,generic_name,brands,serving_size,nutriments",
        }
        try:
            resp = await self._client.get(url, params=params, timeout=15.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("OFF search failed for %r: %s", query, e)
            return []
        products = resp.json().get("products") or []
        out: list[FoodCandidate] = []
        for p in products:
            cand = _off_product_to_candidate(p)
            if cand:
                out.append(cand)
        return out


def _usda_food_to_candidate(food: dict) -> FoodCandidate | None:
    name = food.get("description")
    if not name:
        return None
    nutrients = {
        int(n.get("nutrientId", 0)): n.get("value")
        for n in (food.get("foodNutrients") or [])
        if n.get("nutrientId") is not None and n.get("value") is not None
    }
    kcal_100 = nutrients.get(USDA_NUTRIENT_ENERGY_KCAL)
    if kcal_100 is None:
        return None

    # USDA servingSize/Unit is only populated for branded foods; else per-100g.
    unit = (food.get("servingSizeUnit") or "").lower()
    serving_size = food.get("servingSize")
    size_g = float(serving_size) if serving_size and unit in {"g", "grm"} else 100.0
    factor = size_g / 100.0

    return FoodCandidate(
        source=FoodSource.USDA,
        source_id=str(food.get("fdcId")),
        barcode=food.get("gtinUpc") or None,
        name=name.strip(),
        brand=(food.get("brandOwner") or food.get("brandName") or "").strip() or None,
        serving_size_g=size_g,
        serving_display=food.get("householdServingFullText"),
        calories=float(kcal_100) * factor,
        protein_g=float(nutrients.get(USDA_NUTRIENT_PROTEIN, 0.0) or 0.0) * factor,
        carbs_g=float(nutrients.get(USDA_NUTRIENT_CARBS, 0.0) or 0.0) * factor,
        fat_g=float(nutrients.get(USDA_NUTRIENT_FAT, 0.0) or 0.0) * factor,
        fiber_g=_scale(nutrients.get(USDA_NUTRIENT_FIBER), factor),
        sodium_mg=_scale(nutrients.get(USDA_NUTRIENT_SODIUM), factor),  # already mg
        sugar_g=_scale(nutrients.get(USDA_NUTRIENT_SUGAR), factor),
    )


class USDAClient:
    def __init__(self, client: httpx.AsyncClient, api_key: str | None) -> None:
        self._client = client
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, limit: int = 10) -> list[FoodCandidate]:
        if not self._api_key:
            return []
        url = f"{USDA_BASE_URL}/foods/search"
        params = {
            "api_key": self._api_key,
            "query": query,
            "pageSize": limit,
        }
        try:
            resp = await self._client.get(url, params=params, timeout=15.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("USDA search failed for %r: %s", query, e)
            return []
        foods = resp.json().get("foods") or []
        out: list[FoodCandidate] = []
        for f in foods:
            cand = _usda_food_to_candidate(f)
            if cand:
                out.append(cand)
        return out

    async def get_by_barcode(self, barcode: str) -> FoodCandidate | None:
        """USDA has no dedicated barcode endpoint; search by UPC and match
        exactly against gtinUpc on the returned foods."""
        if not self._api_key:
            return None
        results = await self.search(barcode, limit=5)
        for cand in results:
            if cand.barcode == barcode:
                return cand
        return None
