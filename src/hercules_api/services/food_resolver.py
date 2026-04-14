"""Tiered food resolver: local cache → Open Food Facts → USDA.

Exported entry points are cache-first and persist anything fetched from an
external source so repeat lookups hit the DB.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.models.food import Food
from hercules_api.schemas.food import FoodCandidate
from hercules_api.services.food_clients import OpenFoodFactsClient, USDAClient

log = logging.getLogger(__name__)


async def _get_food_by_barcode(session: AsyncSession, barcode: str) -> Food | None:
    return await session.scalar(select(Food).where(Food.barcode == barcode))


async def _get_food_by_source(
    session: AsyncSession, source: str, source_id: str
) -> Food | None:
    return await session.scalar(
        select(Food).where(Food.source == source, Food.source_id == source_id)
    )


async def _upsert_candidate(session: AsyncSession, cand: FoodCandidate) -> Food:
    existing: Food | None = None
    if cand.source_id:
        existing = await _get_food_by_source(session, cand.source.value, cand.source_id)
    if not existing and cand.barcode:
        existing = await _get_food_by_barcode(session, cand.barcode)

    values = {
        "name": cand.name,
        "brand": cand.brand,
        "barcode": cand.barcode,
        "serving_size_g": cand.serving_size_g,
        "serving_display": cand.serving_display,
        "calories": cand.calories,
        "protein_g": cand.protein_g,
        "carbs_g": cand.carbs_g,
        "fat_g": cand.fat_g,
        "fiber_g": cand.fiber_g,
        "sodium_mg": cand.sodium_mg,
        "sugar_g": cand.sugar_g,
        "source": cand.source.value,
        "source_id": cand.source_id,
    }

    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
        await session.flush()
        return existing

    food = Food(**values)
    session.add(food)
    await session.flush()
    return food


async def lookup_barcode(
    session: AsyncSession,
    barcode: str,
    off: OpenFoodFactsClient,
    usda: USDAClient,
) -> Food | None:
    cached = await _get_food_by_barcode(session, barcode)
    if cached:
        return cached

    cand = await off.get_by_barcode(barcode)
    if not cand and usda.enabled:
        cand = await usda.get_by_barcode(barcode)
    if not cand:
        return None

    food = await _upsert_candidate(session, cand)
    await session.commit()
    return food


async def search_foods(
    session: AsyncSession,
    query: str,
    limit: int,
    off: OpenFoodFactsClient,
    usda: USDAClient,
) -> list[Food]:
    """Hit cache + OFF + USDA in parallel, upsert externals, dedupe by
    (source, source_id). Cache matches are returned in addition to externals."""
    like = f"%{query}%"
    cache_stmt = (
        select(Food)
        .where(or_(Food.name.ilike(like), Food.brand.ilike(like)))
        .order_by(Food.created_at.desc())
        .limit(limit)
    )

    cache_task = session.scalars(cache_stmt)
    off_task = off.search(query, limit=limit)
    usda_task = usda.search(query, limit=limit)

    cache_res, off_res, usda_res = await asyncio.gather(cache_task, off_task, usda_task)
    cached_foods = list(cache_res.all())

    seen: set[tuple[str, str | None]] = {(f.source, f.source_id) for f in cached_foods}
    results: list[Food] = list(cached_foods)

    for cand in [*off_res, *usda_res]:
        key = (cand.source.value, cand.source_id)
        if key in seen:
            continue
        seen.add(key)
        food = await _upsert_candidate(session, cand)
        results.append(food)

    await session.commit()
    return results[:limit]
