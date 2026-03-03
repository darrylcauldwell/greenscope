from unittest.mock import patch

from app.services.embodied import calculate_embodied_per_period


class MockSettings:
    host_embodied_co2_kg = 1205.52
    host_lifespan_years = 4.0


@patch("app.services.embodied.settings", MockSettings())
def test_embodied_basic():
    """1 hour period, using 2 of 16 available core-hours."""
    period_seconds = 3600.0
    # total_cpu_available = host_cores * period_seconds
    # For eShoppen: 16 cores * 3600s = 57600 core-seconds available
    total_cpu_available = 16 * 3600.0
    # App used 2 cores fully for 1 hour = 7200 cpu-seconds
    cpu_seconds = 2 * 3600.0

    result = calculate_embodied_per_period(cpu_seconds, total_cpu_available, period_seconds)

    # TE = 1205.52 * 1000 = 1205520 gCO2e
    # TS = 3600 / (4 * 365.25 * 24 * 3600) = 3600 / 126230400 = 2.8519e-5
    # RS = 7200 / 57600 = 0.125
    # M = 1205520 * 2.8519e-5 * 0.125 = 4.296
    assert abs(result - 4.296) < 0.1


@patch("app.services.embodied.settings", MockSettings())
def test_embodied_zero_cpu_available():
    result = calculate_embodied_per_period(100.0, 0.0, 3600.0)
    assert result == 0.0


@patch("app.services.embodied.settings", MockSettings())
def test_embodied_zero_usage():
    result = calculate_embodied_per_period(0.0, 57600.0, 3600.0)
    assert result == 0.0
