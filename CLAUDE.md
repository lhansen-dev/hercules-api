# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

v1 complete. `hercules-api-requirements.md` remains the source of truth for scope and design decisions — read it before proposing changes.

## Commands

```bash
# Start local postgres
docker compose up -d

# Install dependencies
uv sync

# Run dev server (auto-reload)
uv run uvicorn hercules_api.main:app --reload

# Run all tests
uv run pytest

# Lint
uv run ruff check .

# Build Docker image
docker build -t hercules-api:latest .
```

## Source Layout

```
src/hercules_api/
├── main.py          # FastAPI app, lifespan (create_all + httpx client)
├── config.py        # pydantic-settings (.env)
├── db.py            # engine, SessionLocal, create_all
├── deps.py          # FastAPI dependencies (session, OFF/USDA clients)
├── cli.py           # uvicorn entry point
├── models/          # SQLAlchemy ORM (food.py, meal.py, profile.py, tracking.py, enums.py)
├── schemas/         # Pydantic request/response (food.py, meal.py, profile.py, tracking.py, summary.py)
├── routers/         # FastAPI routers (foods, meals, summary, tracking, goals, recipes, profile)
└── services/        # Business logic
    ├── food_clients.py       # OFF + USDA async HTTP clients + response normalisation
    ├── food_resolver.py      # tiered cache→OFF→USDA lookup + upsert
    ├── barcode_decode.py     # pyzbar barcode decode from base64 image
    ├── meal_service.py       # log/quick-log/relog + macro denormalization
    ├── summary_service.py    # daily + weekly summaries
    └── profile_service.py    # goals, profile, weight, activity, recipes
```

## What This Is

A **headless** nutrition-tracking API. The interface is a Hermes LLM agent (NousResearch Hermes on MiniMax M2.7 via OpenRouter) calling the API as tools — there is no UI, no mobile app, and no human-facing frontend. Every endpoint exists to serve an agent tool listed in the requirements doc's "Agent Tool Interface" table.

Deployment target: single-user homelab, Debian + k3s + ArgoCD, reachable only over LAN/tailnet.

## Tech Stack

- FastAPI (async), SQLAlchemy async + asyncpg, PostgreSQL
- `pyzbar` + Pillow for barcode decode (deterministic CV, **not** a vision model)
- Open Food Facts (no key) + USDA FoodData Central (free key) as external food DBs
- Docker → k3s via ArgoCD gitops

## Architectural Decisions Baked Into the Requirements

These aren't obvious from a fresh read of code, so keep them in mind:

- **Single-user, no auth.** Don't add user scoping, login, multi-tenancy, or RBAC. Access control is the network.
- **Agent owns NL parsing.** The API does not parse "two eggs and toast." It exposes good search + flexible logging endpoints; the agent decomposes, resolves, confirms, then logs.
- **Barcode decode is deterministic.** Never route barcodes through a vision model. Only free-form meal photos (rare path) go to the vision model.
- **Food lookups are tiered and cached**: local cache → Open Food Facts → USDA. Cache externally-fetched foods so repeat scans don't hit the network.
- **Meal item macros are denormalized at log time.** Historical entries must stay accurate even if the referenced `Food` row is later updated or re-fetched. Do not recompute historical macros from current food data.
- **One active `Goal` at a time.** Setting a new goal deactivates the previous one — this is state, not history replacement; old goals are retained.
- **TDEE/BMR via Mifflin-St Jeor** with manual override allowed.
- **v1 uses `create_all`, not Alembic.** Migrations are a v2 concern.
- **The primary coaching tool is `get_daily_summary`.** It's the main context surface for the agent — design it to be self-contained (meals + totals + remaining budget + weight + activity in one response).

## Explicit Non-Goals (v1)

Don't build these unless the user changes scope: micronutrients, water tracking, social features, full workout tracking (reps/sets/weights), mobile app, multi-user, auth, Alembic migrations, Prometheus metrics, CSV export, photo meal logging beyond the basic passthrough.

## Key Entities

`UserProfile`, `Goal`, `Food`, `Recipe`, `MealEntry` → `MealEntryItem`, `WeightEntry`, `ActivityEntry`. Full field lists are in the requirements doc §"Data Model".
