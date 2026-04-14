from sqlalchemy.ext.asyncio import create_async_engine

from hercules_api import models  # noqa: F401 — register tables
from hercules_api.db import Base


async def test_metadata_creates_all_tables() -> None:
    """Sanity check that every model's schema is self-consistent by running
    create_all against an in-memory sqlite DB. Prod uses postgres; postgres-
    specific index options are silently ignored on sqlite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    expected = {
        "foods",
        "recipes",
        "recipe_ingredients",
        "meal_entries",
        "meal_entry_items",
        "user_profile",
        "goals",
        "weight_entries",
        "activity_entries",
    }
    assert expected <= set(Base.metadata.tables.keys())
