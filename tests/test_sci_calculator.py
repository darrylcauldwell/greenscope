from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sci_calculator import _calculate_app_sci


class MockSettings:
    host_tdp_watts = 205.0
    host_cores = 2
    host_pue = 1.2
    host_embodied_co2_kg = 1205.52
    host_lifespan_years = 4.0
    calculation_interval_minutes = 15


@pytest.mark.asyncio
@patch("app.services.embodied.settings", MockSettings())
@patch("app.services.energy.settings", MockSettings())
async def test_calculate_app_sci_with_traffic():
    """Integration test with mocked Prometheus responses."""
    prom_client = MagicMock()
    prom_client.get_container_cpu_seconds = AsyncMock(return_value={"evm-backend": 120.0, "evm-frontend": 30.0})
    prom_client.get_request_count = AsyncMock(return_value=500)

    score = await _calculate_app_sci(
        app_name="evm",
        container_names=["evm-backend", "evm-frontend", "evm-db"],
        request_job="evm-backend",
        carbon_intensity=200.0,
        period_seconds=900,
        prom_client=prom_client,
    )

    assert score.app_name == "evm"
    assert score.cpu_seconds == 150.0
    assert score.carbon_intensity == 200.0
    assert score.energy_kwh > 0
    assert score.operational_emissions > 0
    assert score.embodied_emissions > 0
    assert score.request_count == 500
    assert score.sci_score > 0
    assert score.total_carbon == score.operational_emissions + score.embodied_emissions


@pytest.mark.asyncio
@patch("app.services.embodied.settings", MockSettings())
@patch("app.services.energy.settings", MockSettings())
async def test_calculate_app_sci_zero_requests():
    """SCI score should be 0 when there are no requests."""
    prom_client = MagicMock()
    prom_client.get_container_cpu_seconds = AsyncMock(return_value={"caddy": 50.0})
    prom_client.get_request_count = AsyncMock(return_value=0)

    score = await _calculate_app_sci(
        app_name="meweb",
        container_names=["caddy"],
        request_job="caddy",
        carbon_intensity=230.0,
        period_seconds=900,
        prom_client=prom_client,
    )

    assert score.sci_score == 0.0
    assert score.request_count == 0
    assert score.total_carbon > 0


@pytest.mark.asyncio
@patch("app.services.embodied.settings", MockSettings())
@patch("app.services.energy.settings", MockSettings())
async def test_calculate_app_sci_no_cpu_usage():
    """All values should be 0 when no CPU usage is reported."""
    prom_client = MagicMock()
    prom_client.get_container_cpu_seconds = AsyncMock(return_value={})
    prom_client.get_request_count = AsyncMock(return_value=100)

    score = await _calculate_app_sci(
        app_name="evm",
        container_names=["evm-backend"],
        request_job="evm-backend",
        carbon_intensity=200.0,
        period_seconds=900,
        prom_client=prom_client,
    )

    assert score.cpu_seconds == 0.0
    assert score.energy_kwh == 0.0
    assert score.sci_score == 0.0
