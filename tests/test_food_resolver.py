from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.models.enums import FoodSource
from hercules_api.models.food import Food
from hercules_api.schemas.food import FoodCandidate
from hercules_api.services.food_resolver import lookup_barcode, search_foods


@dataclass
class FakeOFF:
    by_barcode: dict[str, FoodCandidate] = field(default_factory=dict)
    by_search: list[FoodCandidate] = field(default_factory=list)
    barcode_calls: int = 0
    search_calls: int = 0

    async def get_by_barcode(self, barcode: str) -> FoodCandidate | None:
        self.barcode_calls += 1
        return self.by_barcode.get(barcode)

    async def search(self, query: str, limit: int = 10) -> list[FoodCandidate]:
        self.search_calls += 1
        return self.by_search[:limit]


@dataclass
class FakeUSDA:
    by_barcode: dict[str, FoodCandidate] = field(default_factory=dict)
    by_search: list[FoodCandidate] = field(default_factory=list)
    barcode_calls: int = 0
    search_calls: int = 0
    enabled: bool = True

    async def get_by_barcode(self, barcode: str) -> FoodCandidate | None:
        self.barcode_calls += 1
        return self.by_barcode.get(barcode)

    async def search(self, query: str, limit: int = 10) -> list[FoodCandidate]:
        self.search_calls += 1
        return self.by_search[:limit]


def _cand(source: FoodSource, source_id: str, name: str, barcode: str | None = None) -> FoodCandidate:
    return FoodCandidate(
        source=source,
        source_id=source_id,
        barcode=barcode,
        name=name,
        serving_size_g=100.0,
        calories=200.0,
        protein_g=10.0,
        carbs_g=20.0,
        fat_g=5.0,
    )


async def test_lookup_barcode_persists_off_hit(session: AsyncSession) -> None:
    off = FakeOFF(by_barcode={"1111": _cand(FoodSource.OFF, "1111", "Bread", barcode="1111")})
    usda = FakeUSDA()
    food = await lookup_barcode(session, "1111", off, usda)  # type: ignore[arg-type]
    assert food is not None
    assert food.barcode == "1111"
    assert food.name == "Bread"
    # USDA is NOT queried when OFF already returned a hit.
    assert usda.barcode_calls == 0

    # Second call hits the cache, no external calls at all.
    food2 = await lookup_barcode(session, "1111", off, usda)  # type: ignore[arg-type]
    assert food2 is not None
    assert food2.id == food.id
    assert off.barcode_calls == 1  # still just the first one


async def test_lookup_barcode_falls_back_to_usda(session: AsyncSession) -> None:
    off = FakeOFF()  # no OFF result
    usda = FakeUSDA(by_barcode={"2222": _cand(FoodSource.USDA, "2222", "Cheese", barcode="2222")})
    food = await lookup_barcode(session, "2222", off, usda)  # type: ignore[arg-type]
    assert food is not None
    assert food.source == FoodSource.USDA.value
    assert food.name == "Cheese"
    assert off.barcode_calls == 1
    assert usda.barcode_calls == 1


async def test_lookup_barcode_miss_returns_none(session: AsyncSession) -> None:
    off = FakeOFF()
    usda = FakeUSDA()
    food = await lookup_barcode(session, "0000", off, usda)  # type: ignore[arg-type]
    assert food is None


async def test_search_dedupes_by_source(session: AsyncSession) -> None:
    existing = Food(
        source=FoodSource.OFF.value,
        source_id="A",
        barcode=None,
        name="Cached Apple",
        serving_size_g=100.0,
        calories=52.0,
        protein_g=0.3,
        carbs_g=14.0,
        fat_g=0.2,
    )
    session.add(existing)
    await session.commit()

    off = FakeOFF(
        by_search=[
            _cand(FoodSource.OFF, "A", "Apple v2"),  # duplicates cached by (source, source_id)
            _cand(FoodSource.OFF, "B", "Banana"),
        ]
    )
    usda = FakeUSDA(by_search=[_cand(FoodSource.USDA, "C", "Generic Apple")])

    results = await search_foods(session, "apple", 10, off, usda)  # type: ignore[arg-type]

    source_ids = sorted((r.source, r.source_id) for r in results)
    assert source_ids == [("off", "A"), ("off", "B"), ("usda", "C")]

    # Cache row for ("off", "A") was reused, not duplicated.
    off_a_count = (
        await session.scalars(
            select(Food).where(Food.source == "off", Food.source_id == "A")
        )
    ).all()
    assert len(off_a_count) == 1
