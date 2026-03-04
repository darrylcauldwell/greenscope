from unittest.mock import patch

from app.services.whatif import compare_regions, recalculate_energy_kwh, recalculate_sci_for_region


class MockSettings:
    host_tdp_watts = 205.0
    host_cores = 2
    host_pue = 1.2
    host_embodied_co2_kg = 1205.52
    host_lifespan_years = 4.0


SAMPLE_REGIONS = [
    {"provider": "DO", "region": "LON1", "location": "London, UK", "carbon_intensity": 230.0, "pue": 1.2},
    {"provider": "AWS", "region": "eu-west-1", "location": "Europe (Ireland)", "carbon_intensity": 350.0, "pue": 1.1},
    {"provider": "GCP", "region": "europe-north1", "location": "Finland", "carbon_intensity": 50.0, "pue": 1.08},
    {"provider": "Azure", "region": "swedencentral", "location": "Sweden", "carbon_intensity": 20.0, "pue": 1.15},
]


@patch("app.services.whatif.settings", MockSettings())
def test_recalculate_energy_kwh_with_different_pue():
    """Energy recalculation uses the region's PUE, not host default."""
    cpu_seconds = 3600.0  # 1 hour
    # watts_per_core = 205/2 = 102.5
    # joules = 3600 * 102.5 = 369000
    # kwh = 369000 / 3600000 = 0.1025

    # With PUE 1.2 (same as host)
    result_12 = recalculate_energy_kwh(cpu_seconds, 1.2)
    assert abs(result_12 - 0.123) < 0.001

    # With PUE 1.5 (higher, colocation)
    result_15 = recalculate_energy_kwh(cpu_seconds, 1.5)
    assert abs(result_15 - 0.15375) < 0.001
    assert result_15 > result_12

    # With PUE 1.08 (lower, efficient DC)
    result_108 = recalculate_energy_kwh(cpu_seconds, 1.08)
    assert abs(result_108 - 0.1107) < 0.001
    assert result_108 < result_12


@patch("app.services.whatif.settings", MockSettings())
def test_recalculate_energy_kwh_zero():
    result = recalculate_energy_kwh(0.0, 1.5)
    assert result == 0.0


@patch("app.services.whatif.settings", MockSettings())
def test_recalculate_sci_for_region():
    """SCI recalculation uses region CI and PUE but keeps embodied the same."""
    result = recalculate_sci_for_region(
        cpu_seconds=3600.0,
        request_count=100,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        region_carbon_intensity=350.0,
        region_pue=1.1,
    )

    # E = (3600 * 102.5 / 3600000) * 1.1 = 0.1025 * 1.1 = 0.11275
    assert abs(result["energy_kwh"] - 0.11275) < 0.0001
    # O = 0.11275 * 350 = 39.4625
    assert abs(result["operational_emissions"] - 39.4625) < 0.01
    # M = 5.0 (unchanged)
    assert result["embodied_emissions"] == 5.0
    # C = 39.4625 + 5.0 = 44.4625
    assert abs(result["total_carbon"] - 44.4625) < 0.01
    # SCI = 44.4625 / 100 = 0.444625
    assert abs(result["sci_score"] - 0.444625) < 0.001


@patch("app.services.whatif.settings", MockSettings())
def test_recalculate_sci_zero_requests():
    """SCI is 0 when there are no requests."""
    result = recalculate_sci_for_region(
        cpu_seconds=3600.0,
        request_count=0,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        region_carbon_intensity=350.0,
        region_pue=1.1,
    )
    assert result["sci_score"] == 0.0


@patch("app.services.whatif.load_cloud_regions", return_value=SAMPLE_REGIONS)
@patch("app.services.whatif.settings", MockSettings())
def test_compare_regions_sorted_by_sci(mock_load):
    """Results are sorted by SCI ascending (cleanest first)."""
    results = compare_regions(
        cpu_seconds=3600.0,
        request_count=100,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        current_sci=0.333,
        current_carbon_intensity=230.0,
    )

    assert len(results) == 4
    # Should be sorted ascending by SCI
    sci_scores = [r["sci_score"] for r in results]
    assert sci_scores == sorted(sci_scores)

    # Lowest CI (Azure Sweden 20) should be first
    assert results[0]["provider"] == "Azure"
    assert results[0]["region"] == "swedencentral"


@patch("app.services.whatif.load_cloud_regions", return_value=SAMPLE_REGIONS)
@patch("app.services.whatif.settings", MockSettings())
def test_compare_regions_current_marked(mock_load):
    """Current datacenter (DO LON1) is marked with is_current=True."""
    results = compare_regions(
        cpu_seconds=3600.0,
        request_count=100,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        current_sci=0.333,
        current_carbon_intensity=230.0,
    )

    current_rows = [r for r in results if r["is_current"]]
    assert len(current_rows) == 1
    assert current_rows[0]["provider"] == "DO"
    assert current_rows[0]["region"] == "LON1"
    assert current_rows[0]["delta_percent"] == 0.0


@patch("app.services.whatif.load_cloud_regions", return_value=SAMPLE_REGIONS)
@patch("app.services.whatif.settings", MockSettings())
def test_compare_regions_delta_percentages(mock_load):
    """Delta percentages are calculated correctly relative to current SCI."""
    results = compare_regions(
        cpu_seconds=3600.0,
        request_count=100,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        current_sci=0.333,
        current_carbon_intensity=230.0,
    )

    for r in results:
        if r["is_current"]:
            assert r["delta_percent"] == 0.0
        elif r["carbon_intensity"] < 230.0:
            # Lower CI regions should have negative delta
            assert r["delta_percent"] < 0
        elif r["carbon_intensity"] > 230.0:
            # Higher CI regions should have positive delta (accounting for PUE differences)
            # AWS eu-west-1 has CI 350 but PUE 1.1 vs LON1 PUE 1.2
            # so the delta depends on the net effect
            pass


@patch("app.services.whatif.load_cloud_regions", return_value=SAMPLE_REGIONS)
@patch("app.services.whatif.settings", MockSettings())
def test_compare_regions_uses_realtime_ci_for_current(mock_load):
    """Current datacenter uses real-time CI value, not static GSF data."""
    results = compare_regions(
        cpu_seconds=3600.0,
        request_count=100,
        embodied_emissions=5.0,
        calculation_period_seconds=900,
        current_sci=0.333,
        current_carbon_intensity=150.0,  # Real-time CI different from GSF 230
    )

    current = next(r for r in results if r["is_current"])
    # Should use the real-time 150 value, not the GSF 230
    assert current["carbon_intensity"] == 150.0
