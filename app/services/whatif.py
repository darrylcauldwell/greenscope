"""What-If cross-cloud SCI comparison service.

Recalculates SCI scores for each cloud region using the same workload
measurements but different grid carbon intensity and PUE values.
"""

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

REGIONS_PATH = Path(__file__).parent.parent / "static" / "data" / "cloud_regions.json"

# Current datacenter identifier
CURRENT_PROVIDER = "DO"
CURRENT_REGION = "LON1"

# Reference workload for estimated comparisons when no real data is available.
# Represents a typical 15-minute period: 1 vCPU-hour of compute, 1000 requests,
# and a proportional embodied share.
REFERENCE_CPU_SECONDS = 3600.0
REFERENCE_REQUEST_COUNT = 1000
REFERENCE_PERIOD_SECONDS = 900


def load_cloud_regions() -> list[dict]:
    """Load cloud region data from the bundled JSON file."""
    with open(REGIONS_PATH) as f:
        return json.load(f)


def get_reference_workload() -> dict:
    """Return a reference workload for estimated comparisons.

    Used when no real measurement data is available. The absolute SCI values
    are synthetic but the relative comparison between regions is valid.
    """
    from app.services.embodied import calculate_embodied_per_period

    total_cpu_available = settings.host_cores * REFERENCE_PERIOD_SECONDS
    embodied = calculate_embodied_per_period(
        REFERENCE_CPU_SECONDS, total_cpu_available, REFERENCE_PERIOD_SECONDS
    )
    return {
        "cpu_seconds": REFERENCE_CPU_SECONDS,
        "request_count": REFERENCE_REQUEST_COUNT,
        "embodied_emissions": embodied,
        "calculation_period_seconds": REFERENCE_PERIOD_SECONDS,
    }


def recalculate_energy_kwh(cpu_seconds: float, pue: float) -> float:
    """Recalculate energy consumption with a different PUE value.

    Uses the same TDP/cores from settings but substitutes the region's PUE.
    Formula: E = (cpu_seconds * (TDP / cores) / 3_600_000) * PUE
    """
    watts_per_core = settings.host_tdp_watts / settings.host_cores
    joules = cpu_seconds * watts_per_core
    kwh = joules / 3_600_000
    return kwh * pue


def recalculate_sci_for_region(
    cpu_seconds: float,
    request_count: int,
    embodied_emissions: float,
    calculation_period_seconds: int,
    region_carbon_intensity: float,
    region_pue: float,
) -> dict:
    """Recalculate SCI score for a workload running in a different region.

    Takes actual workload measurements (cpu_seconds, request_count, embodied_emissions)
    and recalculates E and O using the region's PUE and carbon intensity.
    M (embodied) stays the same — same hardware assumption.

    Returns a dict with energy_kwh, operational_emissions, total_carbon, sci_score.
    """
    energy_kwh = recalculate_energy_kwh(cpu_seconds, region_pue)
    operational_emissions = energy_kwh * region_carbon_intensity
    total_carbon = operational_emissions + embodied_emissions
    sci_score = total_carbon / request_count if request_count > 0 else 0.0

    return {
        "energy_kwh": energy_kwh,
        "operational_emissions": operational_emissions,
        "embodied_emissions": embodied_emissions,
        "total_carbon": total_carbon,
        "request_count": request_count,
        "sci_score": sci_score,
    }


def compare_regions(
    cpu_seconds: float,
    request_count: int,
    embodied_emissions: float,
    calculation_period_seconds: int,
    current_sci: float,
    current_carbon_intensity: float | None = None,
) -> list[dict]:
    """Compare SCI scores across all cloud regions for a given workload.

    Returns a list of region comparison dicts sorted by SCI ascending (cleanest first).
    Each entry includes the region metadata, recalculated SCI, and delta vs current.
    """
    regions = load_cloud_regions()
    results = []

    for region in regions:
        ci = region.get("carbon_intensity")
        if ci is None or ci <= 0:
            continue

        # Use region PUE if available, otherwise default to current host PUE
        pue = region.get("pue") or settings.host_pue

        sci_data = recalculate_sci_for_region(
            cpu_seconds=cpu_seconds,
            request_count=request_count,
            embodied_emissions=embodied_emissions,
            calculation_period_seconds=calculation_period_seconds,
            region_carbon_intensity=ci,
            region_pue=pue,
        )

        # Calculate delta vs current datacenter
        if current_sci > 0:
            delta_percent = ((sci_data["sci_score"] - current_sci) / current_sci) * 100
        else:
            delta_percent = 0.0

        is_current = region["provider"] == CURRENT_PROVIDER and region["region"] == CURRENT_REGION

        # If this is the current datacenter, use the real-time CI value if provided
        if is_current and current_carbon_intensity is not None:
            sci_data = recalculate_sci_for_region(
                cpu_seconds=cpu_seconds,
                request_count=request_count,
                embodied_emissions=embodied_emissions,
                calculation_period_seconds=calculation_period_seconds,
                region_carbon_intensity=current_carbon_intensity,
                region_pue=pue,
            )
            ci = current_carbon_intensity
            delta_percent = 0.0

        results.append(
            {
                "provider": region["provider"],
                "region": region["region"],
                "location": region["location"],
                "carbon_intensity": ci,
                "pue": pue,
                "is_current": is_current,
                **sci_data,
                "delta_percent": round(delta_percent, 1),
            }
        )

    # Sort by SCI ascending (cleanest first)
    results.sort(key=lambda r: r["sci_score"] if r["sci_score"] > 0 else float("inf"))

    return results
