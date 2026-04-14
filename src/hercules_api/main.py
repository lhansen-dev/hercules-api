import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from hercules_api.config import settings
from hercules_api.db import create_all
from hercules_api.routers import foods, goals, meals, profile, recipes, summary, tracking

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await create_all()
    async with httpx.AsyncClient(
        headers={"User-Agent": "hercules-api/0.1 (homelab)"},
    ) as http:
        app.state.http_client = http
        yield


app = FastAPI(title="Hercules API", version="0.1.0", lifespan=lifespan)
app.include_router(foods.router)
app.include_router(meals.router)
app.include_router(summary.router)
app.include_router(tracking.router)
app.include_router(goals.router)
app.include_router(recipes.router)
app.include_router(profile.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
