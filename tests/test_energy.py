from unittest.mock import patch

from app.services.energy import cpu_seconds_to_kwh


class MockSettings:
    host_tdp_watts = 205.0
    host_cores = 2
    host_pue = 1.2


@patch("app.services.energy.settings", MockSettings())
def test_cpu_seconds_to_kwh_basic():
    # 1 hour of 1 core at full utilisation on a 2-core 205W system
    # watts_per_core = 205 / 2 = 102.5
    # joules = 3600 * 102.5 = 369000
    # kwh = 369000 / 3600000 = 0.1025
    # with PUE 1.2: 0.1025 * 1.2 = 0.123
    result = cpu_seconds_to_kwh(3600.0)
    assert abs(result - 0.123) < 0.001


@patch("app.services.energy.settings", MockSettings())
def test_cpu_seconds_to_kwh_zero():
    result = cpu_seconds_to_kwh(0.0)
    assert result == 0.0


@patch("app.services.energy.settings", MockSettings())
def test_cpu_seconds_to_kwh_eshoppen_reference():
    """Validate against eShoppen case study reference values.

    2 cores, 205W TDP, ~18.39% utilisation for 1 hour = ~662 cpu-seconds
    Expected: ~0.023 kWh (before PUE)
    """
    # 18.39% of 1 core for 1 hour = 0.1839 * 3600 = 662.04 cpu-seconds
    cpu_seconds = 662.04
    result = cpu_seconds_to_kwh(cpu_seconds)
    # watts_per_core = 102.5, joules = 662.04 * 102.5 = 67859.1
    # kwh = 67859.1 / 3600000 = 0.018850
    # with PUE 1.2: 0.02262
    assert abs(result - 0.02262) < 0.001
