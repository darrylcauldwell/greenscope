from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.sql import func

from app.config import settings
from app.database import async_session
from app.models import SCIScore
from app.schemas import GenerationMixEntry, SCIComponent, SCICurrentResponse, SCIHistoryResponse
from app.services.sci_calculator import latest_carbon_info

router = APIRouter(prefix="/api/sci", tags=["sci"])


@router.get("/current", response_model=SCICurrentResponse)
async def get_current_sci():
    """Get the latest SCI score for each monitored app."""
    configured_apps = list(settings.get_app_boundaries().keys())

    async with async_session() as session:
        # Subquery: latest timestamp per app — only configured apps
        latest_subq = (
            select(SCIScore.app_name, func.max(SCIScore.timestamp).label("max_ts"))
            .where(SCIScore.app_name.in_(configured_apps))
            .group_by(SCIScore.app_name)
            .subquery()
        )

        # Join to get full records
        query = select(SCIScore).join(
            latest_subq,
            (SCIScore.app_name == latest_subq.c.app_name) & (SCIScore.timestamp == latest_subq.c.max_ts),
        )

        result = await session.execute(query)
        scores = result.scalars().all()

    generation_mix = [
        GenerationMixEntry(**entry) for entry in latest_carbon_info.get("generation_mix", [])
    ]

    if not scores:
        return SCICurrentResponse(
            scores=[],
            carbon_intensity_source=latest_carbon_info.get("source", "No data yet"),
            carbon_intensity_region=latest_carbon_info.get("region_name", ""),
            carbon_intensity_index=latest_carbon_info.get("index", ""),
            generation_mix=generation_mix,
            calculated_at=datetime.now(timezone.utc),
        )

    return SCICurrentResponse(
        scores=[SCIComponent.model_validate(s) for s in scores],
        carbon_intensity_source=latest_carbon_info.get("source", f"{scores[0].carbon_intensity} gCO2eq/kWh"),
        carbon_intensity_region=latest_carbon_info.get("region_name", ""),
        carbon_intensity_index=latest_carbon_info.get("index", ""),
        generation_mix=generation_mix,
        calculated_at=scores[0].timestamp,
    )


@router.get("/history", response_model=SCIHistoryResponse)
async def get_sci_history(
    app_name: str = Query(..., description="App name to get history for"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history to return"),
):
    """Get historical SCI scores for trend charts."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as session:
        query = (
            select(SCIScore)
            .where(SCIScore.app_name == app_name, SCIScore.timestamp >= cutoff)
            .order_by(SCIScore.timestamp.asc())
        )

        result = await session.execute(query)
        scores = result.scalars().all()

    return SCIHistoryResponse(
        app_name=app_name,
        scores=[SCIComponent.model_validate(s) for s in scores],
        hours=hours,
    )


@router.get("/breakdown/{app_name}", response_model=SCIComponent)
async def get_sci_breakdown(app_name: str):
    """Get detailed SCI breakdown for a single app (latest calculation)."""
    async with async_session() as session:
        query = select(SCIScore).where(SCIScore.app_name == app_name).order_by(SCIScore.timestamp.desc()).limit(1)

        result = await session.execute(query)
        score = result.scalar_one_or_none()

    if score is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"No SCI data found for app '{app_name}'")

    return SCIComponent.model_validate(score)
