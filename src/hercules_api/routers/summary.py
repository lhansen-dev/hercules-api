from datetime import date

from fastapi import APIRouter, Query

from hercules_api.deps import SessionDep
from hercules_api.schemas.summary import DailySummary, WeeklySummary
from hercules_api.services.summary_service import get_daily_summary, get_weekly_summary

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/daily", response_model=DailySummary)
async def daily_summary(
    session: SessionDep,
    date: date | None = Query(default=None, description="ISO date, defaults to today"),
) -> DailySummary:
    return await get_daily_summary(session, date)


@router.get("/weekly", response_model=WeeklySummary)
async def weekly_summary(
    session: SessionDep,
    end_date: date | None = Query(
        default=None, description="Last day of the 7-day window, defaults to today"
    ),
) -> WeeklySummary:
    return await get_weekly_summary(session, end_date)
