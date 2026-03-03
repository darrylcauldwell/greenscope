import logging
from datetime import datetime, timezone

from app.config import settings
from app.database import async_session
from app.models import SCIScore
from app.services.carbon_intensity import CarbonIntensityClient
from app.services.embodied import calculate_embodied_per_period
from app.services.energy import cpu_seconds_to_kwh
from app.services.prometheus import PrometheusClient

logger = logging.getLogger(__name__)


async def calculate_all_sci_scores() -> list[SCIScore]:
    """Run the full SCI calculation pipeline for all configured apps."""
    period_seconds = settings.calculation_interval_minutes * 60
    boundaries = settings.get_app_boundaries()
    request_jobs = settings.get_app_request_jobs()

    carbon_client = CarbonIntensityClient()
    prom_client = PrometheusClient()

    # Step 1: Fetch current carbon intensity (shared across all apps)
    carbon_intensity, carbon_source = await carbon_client.get_current_intensity()
    logger.info("Carbon intensity: %.1f gCO2eq/kWh (%s)", carbon_intensity, carbon_source)

    scores: list[SCIScore] = []

    # Step 2: Calculate SCI for each app
    for app_name, container_names in boundaries.items():
        try:
            score = await _calculate_app_sci(
                app_name=app_name,
                container_names=container_names,
                request_job=request_jobs.get(app_name, app_name),
                carbon_intensity=carbon_intensity,
                period_seconds=period_seconds,
                prom_client=prom_client,
            )
            scores.append(score)

            logger.info(
                "SCI [%s]: score=%.4f gCO2e/req | E=%.6f kWh | O=%.4f gCO2e | M=%.4f gCO2e | R=%d reqs | cpu=%.1fs",
                app_name,
                score.sci_score,
                score.energy_kwh,
                score.operational_emissions,
                score.embodied_emissions,
                score.request_count,
                score.cpu_seconds,
            )

        except Exception:
            logger.exception("SCI calculation failed for %s, skipping", app_name)
            continue

    # Step 3: Store results in database
    if scores:
        async with async_session() as session:
            session.add_all(scores)
            await session.commit()

    # Step 4: Update Prometheus gauges
    _update_prometheus_gauges(scores, carbon_intensity)

    return scores


async def _calculate_app_sci(
    app_name: str,
    container_names: list[str],
    request_job: str,
    carbon_intensity: float,
    period_seconds: int,
    prom_client: PrometheusClient,
) -> SCIScore:
    """Calculate SCI score for a single app."""
    # 2a: Query Prometheus for container CPU seconds
    cpu_by_container = await prom_client.get_container_cpu_seconds(container_names, period_seconds)
    total_cpu_seconds = sum(cpu_by_container.values())

    # 2b: Convert CPU seconds to energy (kWh)
    energy_kwh = cpu_seconds_to_kwh(total_cpu_seconds)

    # 2c: Calculate operational emissions: O = E * I
    operational_emissions = energy_kwh * carbon_intensity

    # 2d: Calculate embodied emissions share
    total_cpu_available = settings.host_cores * period_seconds
    embodied_emissions = calculate_embodied_per_period(total_cpu_seconds, total_cpu_available, period_seconds)

    # 2e: Total carbon: C = O + M
    total_carbon = operational_emissions + embodied_emissions

    # 2f: Query Prometheus for HTTP request count
    request_count = await prom_client.get_request_count(request_job, period_seconds)

    # 2g: Calculate SCI = C / R
    sci_score = total_carbon / request_count if request_count > 0 else 0.0

    return SCIScore(
        app_name=app_name,
        timestamp=datetime.now(timezone.utc),
        energy_kwh=energy_kwh,
        carbon_intensity=carbon_intensity,
        operational_emissions=operational_emissions,
        embodied_emissions=embodied_emissions,
        total_carbon=total_carbon,
        request_count=request_count,
        sci_score=sci_score,
        cpu_seconds=total_cpu_seconds,
        calculation_period_seconds=period_seconds,
    )


def _update_prometheus_gauges(scores: list[SCIScore], carbon_intensity: float) -> None:
    """Update custom Prometheus gauges with latest SCI results."""
    try:
        from app.metrics import (
            CARBON_INTENSITY_GAUGE,
            EMBODIED_EMISSIONS_GAUGE,
            ENERGY_GAUGE,
            OPERATIONAL_EMISSIONS_GAUGE,
            REQUEST_COUNT_GAUGE,
            SCI_SCORE_GAUGE,
        )

        CARBON_INTENSITY_GAUGE.set(carbon_intensity)

        for score in scores:
            SCI_SCORE_GAUGE.labels(app=score.app_name).set(score.sci_score)
            ENERGY_GAUGE.labels(app=score.app_name).set(score.energy_kwh)
            REQUEST_COUNT_GAUGE.labels(app=score.app_name).set(score.request_count)
            OPERATIONAL_EMISSIONS_GAUGE.labels(app=score.app_name).set(score.operational_emissions)
            EMBODIED_EMISSIONS_GAUGE.labels(app=score.app_name).set(score.embodied_emissions)

    except Exception:
        logger.exception("Failed to update Prometheus gauges")
