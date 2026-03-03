from app.config import settings


def calculate_embodied_per_period(
    cpu_seconds: float,
    total_cpu_available: float,
    period_seconds: float,
) -> float:
    """Calculate embodied emissions share for an app over a measurement period.

    Formula: M = TE * TS * RS
    Where:
        TE = Total Embodied Emissions (kgCO2e converted to gCO2e)
        TS = Time Share = period_seconds / (lifespan_years * 365.25 * 24 * 3600)
        RS = Resource Share = cpu_seconds / total_cpu_available
    """
    if total_cpu_available == 0:
        return 0.0

    te_grams = settings.host_embodied_co2_kg * 1000
    lifespan_seconds = settings.host_lifespan_years * 365.25 * 24 * 3600
    time_share = period_seconds / lifespan_seconds
    resource_share = cpu_seconds / total_cpu_available

    return te_grams * time_share * resource_share
