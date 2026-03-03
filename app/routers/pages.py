from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.sql import func

from app.config import settings
from app.database import async_session
from app.models import SCIScore

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard page."""
    async with async_session() as session:
        # Get latest scores per app
        latest_subq = (
            select(SCIScore.app_name, func.max(SCIScore.timestamp).label("max_ts"))
            .group_by(SCIScore.app_name)
            .subquery()
        )

        query = select(SCIScore).join(
            latest_subq,
            (SCIScore.app_name == latest_subq.c.app_name) & (SCIScore.timestamp == latest_subq.c.max_ts),
        )

        result = await session.execute(query)
        current_scores = result.scalars().all()

        # Get 24h history for trend chart
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        history_query = select(SCIScore).where(SCIScore.timestamp >= cutoff).order_by(SCIScore.timestamp.asc())

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

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "scores": current_scores,
            "history_by_app": history_by_app,
            "app_names": list(settings.get_app_boundaries().keys()),
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
