from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.sql import func

from app.config import settings
from app.database import async_session
from app.models import SCIScore
from app.schemas import (
    AggregatedAppScore,
    AggregatedSCIResponse,
    DropletSummary,
    GenerationMixEntry,
    SCIComponent,
    SCICurrentResponse,
    SCIHistoryResponse,
)
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


@router.get("/aggregated", response_model=AggregatedSCIResponse)
async def get_aggregated_sci(
    minutes: int = Query(15, ge=15, le=1440, description="Time window in minutes"),
):
    """Get aggregated SCI scores over a time window."""
    configured_apps = list(settings.get_app_boundaries().keys())
    boundaries = settings.get_app_boundaries()
    display_names = settings.get_app_display_names()

    async with async_session() as session:
        if minutes <= 15:
            # Latest single snapshot per app (current behaviour)
            latest_subq = (
                select(SCIScore.app_name, func.max(SCIScore.timestamp).label("max_ts"))
                .where(SCIScore.app_name.in_(configured_apps))
                .group_by(SCIScore.app_name)
                .subquery()
            )
            query = select(SCIScore).join(
                latest_subq,
                (SCIScore.app_name == latest_subq.c.app_name)
                & (SCIScore.timestamp == latest_subq.c.max_ts),
            )
            result = await session.execute(query)
            rows = result.scalars().all()

            app_scores = []
            for r in rows:
                app_scores.append(
                    AggregatedAppScore(
                        app_name=r.app_name,
                        energy_kwh=r.energy_kwh,
                        carbon_intensity=r.carbon_intensity,
                        operational_emissions=r.operational_emissions,
                        embodied_emissions=r.embodied_emissions,
                        total_carbon=r.total_carbon,
                        request_count=r.request_count,
                        sci_score=r.sci_score,
                        cpu_seconds=r.cpu_seconds,
                        snapshot_count=1,
                    )
                )
        else:
            # Aggregate all snapshots in the window
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            query = (
                select(
                    SCIScore.app_name,
                    func.sum(SCIScore.energy_kwh).label("energy_kwh"),
                    func.avg(SCIScore.carbon_intensity).label("carbon_intensity"),
                    func.sum(SCIScore.operational_emissions).label("operational_emissions"),
                    func.sum(SCIScore.embodied_emissions).label("embodied_emissions"),
                    func.sum(SCIScore.total_carbon).label("total_carbon"),
                    func.sum(SCIScore.request_count).label("request_count"),
                    func.sum(SCIScore.cpu_seconds).label("cpu_seconds"),
                    func.count().label("snapshot_count"),
                )
                .where(SCIScore.app_name.in_(configured_apps), SCIScore.timestamp >= cutoff)
                .group_by(SCIScore.app_name)
            )
            result = await session.execute(query)
            rows = result.all()

            app_scores = []
            for r in rows:
                total_c = float(r.total_carbon)
                req_count = int(r.request_count)
                sci = total_c / req_count if req_count > 0 else 0
                app_scores.append(
                    AggregatedAppScore(
                        app_name=r.app_name,
                        energy_kwh=float(r.energy_kwh),
                        carbon_intensity=float(r.carbon_intensity),
                        operational_emissions=float(r.operational_emissions),
                        embodied_emissions=float(r.embodied_emissions),
                        total_carbon=total_c,
                        request_count=req_count,
                        sci_score=sci,
                        cpu_seconds=float(r.cpu_seconds),
                        snapshot_count=int(r.snapshot_count),
                    )
                )

    # Compute droplet-level aggregate
    droplet = None
    if app_scores:
        total_energy = sum(s.energy_kwh for s in app_scores)
        total_operational = sum(s.operational_emissions for s in app_scores)
        total_embodied = sum(s.embodied_emissions for s in app_scores)
        total_carbon = total_operational + total_embodied
        all_containers = [c for containers in boundaries.values() for c in containers]
        container_count = len(all_containers)
        droplet = DropletSummary(
            energy_kwh=total_energy,
            operational_emissions=total_operational,
            embodied_emissions=total_embodied,
            total_carbon=total_carbon,
            request_count=sum(s.request_count for s in app_scores),
            sci_score=total_carbon / container_count if container_count > 0 else 0,
            container_count=container_count,
        )

    return AggregatedSCIResponse(
        window_minutes=minutes,
        scores=app_scores,
        droplet=droplet,
        display_names=display_names,
        boundaries=boundaries,
    )
