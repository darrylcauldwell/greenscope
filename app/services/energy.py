from app.config import settings


def cpu_seconds_to_kwh(cpu_seconds: float) -> float:
    """Convert CPU seconds to kilowatt-hours using configured host hardware values.

    Formula: E = (cpu_seconds * (TDP_watts / num_cores)) / 3_600_000 * PUE
    """
    watts_per_core = settings.host_tdp_watts / settings.host_cores
    joules = cpu_seconds * watts_per_core
    kwh = joules / 3_600_000
    return kwh * settings.host_pue
