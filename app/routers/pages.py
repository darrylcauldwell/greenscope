from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.sql import func

from app.config import settings
from app.database import async_session
from app.models import SCIScore
from app.services.sci_calculator import latest_carbon_info
from app.services.whatif import compare_regions, get_reference_workload, recalculate_sci_for_region

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard page."""
    configured_apps = list(settings.get_app_boundaries().keys())

    async with async_session() as session:
        # Get latest scores per app — only configured apps
        latest_subq = (
            select(SCIScore.app_name, func.max(SCIScore.timestamp).label("max_ts"))
            .where(SCIScore.app_name.in_(configured_apps))
            .group_by(SCIScore.app_name)
            .subquery()
        )

        query = select(SCIScore).join(
            latest_subq,
            (SCIScore.app_name == latest_subq.c.app_name) & (SCIScore.timestamp == latest_subq.c.max_ts),
        )

        result = await session.execute(query)
        current_scores = result.scalars().all()

        # Get 24h history for trend chart — only configured apps
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        history_query = (
            select(SCIScore)
            .where(SCIScore.app_name.in_(configured_apps), SCIScore.timestamp >= cutoff)
            .order_by(SCIScore.timestamp.asc())
        )

        history_result = await session.execute(history_query)
        history_scores = history_result.scalars().all()

    # Group history by app for Chart.js
    history_by_app: dict[str, list[dict]] = {}
    for score in history_scores:
        if score.app_name not in history_by_app:
            history_by_app[score.app_name] = []
        history_by_app[score.app_name].append(
            {
                "timestamp": score.timestamp.isoformat(),
                "sci_score": score.sci_score,
                "operational_emissions": score.operational_emissions,
                "embodied_emissions": score.embodied_emissions,
            }
        )

    # Compute droplet-level aggregate from per-app scores
    droplet: dict | None = None
    if current_scores:
        total_energy = sum(s.energy_kwh for s in current_scores)
        total_operational = sum(s.operational_emissions for s in current_scores)
        total_embodied = sum(s.embodied_emissions for s in current_scores)
        total_carbon = total_operational + total_embodied
        total_requests = sum(s.request_count for s in current_scores)
        droplet = {
            "energy_kwh": total_energy,
            "operational_emissions": total_operational,
            "embodied_emissions": total_embodied,
            "total_carbon": total_carbon,
            "request_count": total_requests,
            "sci_score": total_carbon / total_requests if total_requests > 0 else 0,
        }

    boundaries = settings.get_app_boundaries()
    all_containers = [c for containers in boundaries.values() for c in containers]

    # Recompute droplet SCI using containers as the functional unit
    if droplet and all_containers:
        container_count = len(all_containers)
        droplet["container_count"] = container_count
        droplet["sci_score"] = droplet["total_carbon"] / container_count if container_count > 0 else 0

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "scores": current_scores,
            "droplet": droplet,
            "all_containers": all_containers,
            "history_by_app": history_by_app,
            "app_names": configured_apps,
            "carbon_info": latest_carbon_info,
            "display_names": settings.get_app_display_names(),
            "boundaries": boundaries,
            "calc_interval_minutes": settings.calculation_interval_minutes,
        },
    )


@router.get("/what-if", response_class=HTMLResponse)
async def what_if(request: Request):
    """Render the What-If cross-cloud comparison page."""
    boundaries = settings.get_app_boundaries()
    app_names = list(boundaries.keys())
    active_app = app_names[0] if app_names else None

    # Pre-fetch initial comparison data for the first app
    initial_data: dict = {
        "app_name": None, "app_names": app_names, "estimated": False, "current_sci": 0, "regions": [],
    }

    if active_app:
        async with async_session() as session:
            query = (
                select(SCIScore)
                .where(SCIScore.app_name == active_app)
                .order_by(SCIScore.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(query)
            score = result.scalar_one_or_none()

        # Determine whether to use real data or reference workload
        estimated = False
        if score is not None and score.request_count > 0 and score.cpu_seconds > 0:
            workload = {
                "cpu_seconds": score.cpu_seconds,
                "request_count": score.request_count,
                "embodied_emissions": score.embodied_emissions,
                "calculation_period_seconds": score.calculation_period_seconds,
            }
            current_sci = score.sci_score
            current_ci = score.carbon_intensity
        else:
            estimated = True
            workload = get_reference_workload()
            current_ci = score.carbon_intensity if score else 230.0
            current_result = recalculate_sci_for_region(
                region_pue=settings.host_pue,
                region_carbon_intensity=current_ci,
                **workload,
            )
            current_sci = current_result["sci_score"]

        regions = compare_regions(current_sci=current_sci, current_carbon_intensity=current_ci, **workload)
        greenest = None
        for r in regions:
            if not r["is_current"] and r["sci_score"] > 0:
                greenest = r
                break
        initial_data = {
            "app_name": active_app,
            "app_names": app_names,
            "estimated": estimated,
            "current_sci": current_sci,
            "current_carbon_intensity": current_ci,
            "greenest": greenest,
            "regions": regions,
        }

    return templates.TemplateResponse(
        "whatif.html",
        {
            "request": request,
            "settings": settings,
            "app_names": app_names,
            "active_app": active_app,
            "initial_data": initial_data,
            "carbon_info": latest_carbon_info,
            "display_names": settings.get_app_display_names(),
        },
    )


@router.get("/methodology", response_class=HTMLResponse)
async def methodology(request: Request):
    """Render the methodology transparency page."""
    return templates.TemplateResponse(
        "methodology.html",
        {
            "request": request,
            "settings": settings,
            "boundaries": settings.get_app_boundaries(),
        },
    )
