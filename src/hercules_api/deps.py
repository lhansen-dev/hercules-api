"""FastAPI dependencies: shared HTTP client, external-service clients, DB session."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.config import settings
from hercules_api.db import SessionLocal
from hercules_api.services.food_clients import OpenFoodFactsClient, USDAClient


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_http_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient | None = getattr(request.app.state, "http_client", None)
    if client is None:
        raise RuntimeError("HTTP client not initialized on app.state")
    return client


def get_off_client(
    http: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> OpenFoodFactsClient:
    return OpenFoodFactsClient(http)


def get_usda_client(
    http: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> USDAClient:
    return USDAClient(http, settings.usda_api_key)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
OFFDep = Annotated[OpenFoodFactsClient, Depends(get_off_client)]
USDADep = Annotated[USDAClient, Depends(get_usda_client)]
