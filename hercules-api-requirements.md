# Hercules API Nutrition Coach — Requirements Document

## Overview

A headless nutrition tracking API designed to be driven entirely by a Hermes LLM agent (NousResearch Hermes, running on MiniMax M2.7 via OpenRouter). The agent acts as a conversational fitness coach — the API is the persistence and data layer, not the UI. Deployed on a Debian homelab running k3s with ArgoCD.


## Core Features

### 1. Barcode Scanning
Decode UPC/EAN barcodes from user-submitted photos using a deterministic CV library (pyzbar or zxing), not a vision model. The decoded barcode number is used to look up the product on Open Food Facts. Results are cached locally so repeated scans don't hit the external API.

Inputs: image (base64 or multipart upload), or raw barcode string.
Outputs: food item with full nutritional data (calories, protein, carbs, fat, and optionally fiber, sodium, sugar).

### 2. Meal Photo Scanning
For when the user sends a photo of food (not a barcode), route the image to a vision-capable model (MiniMax-01 or similar via OpenRouter) to identify the food and estimate portions. The agent then resolves the description to nutritional data and logs it. Expected to be rarely used — most logging will be text-based.

### 3. Food Search & Resolution
Search for foods by name across multiple databases. The agent uses this to resolve natural language meal descriptions (e.g., "I had two eggs and toast") into structured nutritional data.

Data sources (priority order):
- Local cache (previously looked-up foods)
- Open Food Facts (no API key, strong on Canadian packaged goods)
- USDA FoodData Central (free API key, strong on generic/unpackaged foods)

### 4. Meal Logging
Three logging modes:
- **Structured log**: Agent resolves foods via search/barcode, then logs with food_id references and quantities.
- **Quick-add**: Agent estimates macros from natural language description and logs raw calorie/macro values with a text note. Used when exact food matches aren't found or the user wants speed over precision.
- **Re-log**: Copy a previous meal to today. Handles "same as yesterday's breakfast" or "the usual." Requires access to recent meal history.

Each meal entry has a type (breakfast, lunch, dinner, snack), a timestamp, optional notes, and one or more items. Item macros are denormalized at log time so historical entries remain accurate even if food records are updated later.

### 5. Recipe / Composite Meal Support
Save named recipes as collections of food items with quantities. Recipes track how many servings they produce so the agent can log "1 serving of my chicken stir fry" and compute macros correctly. Useful for meal prep and frequently repeated home-cooked meals.

### 6. Calorie & Macro Tracking
Track daily totals for calories, protein, carbs, and fat. Compare against user-defined goals. Provide daily and weekly summary endpoints that the agent uses as its primary coaching context.

Daily summary includes: all meals with itemized macros, daily totals, remaining budget vs. goals, weight entry (if any), and activity (if any).

Weekly summary includes: daily averages, weight trend, days logged, and days on target (within ±10% of calorie goal).

### 7. Weight Tracking
Log weigh-ins with date and optional notes (e.g., "morning, fasted"). Provide trend analysis over configurable time windows — direction (losing/gaining/stable), total change, and data point count.

### 8. Goal Setting & TDEE
Store calorie and macro targets. Only one goal active at a time — setting a new goal deactivates the previous one. Optionally compute TDEE/BMR from user profile (height, weight, age, sex, activity level) using Mifflin-St Jeor, but allow manual override.

### 9. Activity Logging (Lightweight)
Not a workout tracker — just enough context for the coaching agent to know training vs. rest days and adjust advice accordingly. A simple description ("upper body," "30min run") and optional calorie estimate.

### 10. Text-Based Food & Portion Derivation
The agent (not the API) handles natural language parsing. When the user says "I had a chicken wrap with a side of rice," the agent should:
1. Break the description into individual food items
2. Search the food database for each item
3. Estimate reasonable portions if the user doesn't specify (e.g., "a chicken breast" → ~170g)
4. Present the breakdown to the user for confirmation before logging
5. Log the confirmed items

This is an agent-side concern, not an API feature — the API just needs good search and flexible logging endpoints.


## Data Model (Key Entities)

- **UserProfile**: height, age, sex, activity level, goal type. Single-user.
- **Goal**: calorie/macro targets, TDEE/BMR snapshots, start/end dates.
- **Food**: name, brand, barcode, per-serving macros, source (OFF/USDA/manual), source_id. Cached from external lookups.
- **Recipe**: name, servings, list of (food_id, quantity) ingredients. Macros computed from ingredients.
- **MealEntry**: timestamp, meal type, notes. Contains MealEntryItems.
- **MealEntryItem**: references food or recipe, quantity, denormalized macros.
- **WeightEntry**: date, weight_kg, notes.
- **ActivityEntry**: date, description, estimated calories.


## Agent Tool Interface

The Hermes agent interacts with the API via tool/function calling. Key tools:

| Tool | Purpose |
|---|---|
| `scan_barcode` | Decode barcode image → food lookup |
| `lookup_barcode` | Look up barcode by number string |
| `search_food` | Search OFF + USDA by name |
| `log_meal` | Log structured meal with food/recipe refs |
| `quick_log_meal` | Log meal with estimated macros + description |
| `relog_meal` | Copy a previous meal to today |
| `get_recent_meals` | Fetch recent meals (for re-log or context) |
| `get_daily_summary` | Full day overview — the primary coaching context tool |
| `get_weekly_summary` | Weekly averages and trends |
| `log_weight` | Record a weigh-in |
| `get_weight_trend` | Weight direction and change over N days |
| `log_activity` | Record a workout/activity |
| `set_goal` | Set calorie/macro targets |
| `create_recipe` | Save a composite recipe |
| `search_recipes` | Find saved recipes by name |
| `update_profile` | Set/update user stats |


## Tech Stack

- **API**: FastAPI (Python), async
- **Database**: PostgreSQL (running in k3s or standalone on the homelab)
- **ORM**: SQLAlchemy (async with asyncpg)
- **Barcode decoding**: pyzbar + Pillow
- **External APIs**: Open Food Facts (no key), USDA FoodData Central (free key)
- **Containerization**: Docker
- **Deployment**: k3s with ArgoCD (gitops from repo)
- **Agent**: Hermes (NousResearch) on MiniMax M2.7 via OpenRouter


## Non-Goals (v1)

- Micronutrient tracking (vitamins, minerals) — noisy data, diminishing returns
- Water intake tracking
- Social/sharing features
- Full workout tracking (reps, sets, weights) — just context for coaching
- Mobile app — the agent IS the interface
- Multi-user support — single-user homelab deployment
- Auth — accessible only on local network / tailnet


## Future Considerations (v2+)

- Alembic migrations (v1 can use `create_all`)
- Food deduplication (same barcode from multiple searches)
- CSV/JSON export for data portability
- Meal timing analysis ("you tend to undereat until dinner then overcompensate")
- Photo-based meal logging via vision model
- Prometheus metrics endpoint for Grafana dashboards
