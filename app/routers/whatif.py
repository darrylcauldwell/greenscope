from fastapi import APIRouter, Query
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import SCIScore
from app.services.whatif import compare_regions, get_reference_workload

router = APIRouter(prefix="/api/whatif", tags=["whatif"])


@router.get("/compare")
async def compare(
    app_name: str = Query(None, description="App name to compare (defaults to first configured app)"),
):
    """Compare SCI scores across cloud regions for a given app.

    Uses the latest actual measurements (cpu_seconds, request_count, embodied_emissions)
    and recalculates SCI with each region's carbon intensity and PUE.
    """
    boundaries = settings.get_app_boundaries()
    app_names = list(boundaries.keys())

    if not app_names:
        return {"app_name": None, "app_names": [], "current_sci": 0, "regions": []}

    # Default to first app if not specified
    if app_name is None or app_name not in app_names:
        app_name = app_names[0]

    # Fetch latest SCI score for this app
    async with async_session() as session:
        query = select(SCIScore).where(SCIScore.app_name == app_name).order_by(SCIScore.timestamp.desc()).limit(1)
        result = await session.execute(query)
        score = result.scalar_one_or_none()

    # Determine whether to use real data or a reference workload estimate
    estimated = False
    if score is not None and score.request_count > 0 and score.cpu_seconds > 0:
        # Real workload data available
        workload = {
            "cpu_seconds": score.cpu_seconds,
            "request_count": score.request_count,
            "embodied_emissions": score.embodied_emissions,
            "calculation_period_seconds": score.calculation_period_seconds,
        }
        current_sci = score.sci_score
        current_ci = score.carbon_intensity
    else:
        # No meaningful data — use reference workload for relative comparison
        estimated = True
        workload = get_reference_workload()
        current_ci = score.carbon_intensity if score else 230.0
        # Calculate current SCI from reference workload at current datacenter
        from app.services.whatif import recalculate_sci_for_region

        current_result = recalculate_sci_for_region(
            region_pue=settings.host_pue,
            region_carbon_intensity=current_ci,
            **workload,
        )
        current_sci = current_result["sci_score"]

    # Compare across all regions
    regions = compare_regions(
        current_sci=current_sci,
        current_carbon_intensity=current_ci,
        **workload,
    )

    # Find the greenest region
    greenest = None
    for r in regions:
        if not r["is_current"] and r["sci_score"] > 0:
            greenest = r
            break

    return {
        "app_name": app_name,
        "app_names": app_names,
        "estimated": estimated,
        "current_sci": current_sci,
        "current_carbon_intensity": current_ci,
        "greenest": greenest,
        "regions": regions,
    }
