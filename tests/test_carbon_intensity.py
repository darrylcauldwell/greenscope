from unittest.mock import AsyncMock, patch

import pytest

from app.services.carbon_intensity import CarbonIntensityClient, CarbonIntensityResult


def _make_regional_response(forecast=150, index="moderate", region="South England"):
    """Build a mock regional API response."""
    return {
        "data": [
            {
                "regionid": 12,
                "dnoregion": "SSE South",
                "shortname": region,
                "postcode": "SL1",
                "data": [
                    {
                        "from": "2026-03-03T12:00Z",
                        "to": "2026-03-03T12:30Z",
                        "intensity": {"forecast": forecast, "index": index},
                        "generationmix": [
                            {"fuel": "gas", "perc": 40.0},
                            {"fuel": "wind", "perc": 30.0},
                            {"fuel": "nuclear", "perc": 20.0},
                            {"fuel": "solar", "perc": 10.0},
                        ],
                    }
                ],
            }
        ]
    }


def _make_national_response(actual=200, forecast=210):
    """Build a mock national API response."""
    return {
        "data": [
            {
                "from": "2026-03-03T12:00Z",
                "to": "2026-03-03T12:30Z",
                "intensity": {"forecast": forecast, "actual": actual, "index": "high"},
            }
        ]
    }


class _MockResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


@pytest.mark.asyncio
@patch("app.services.carbon_intensity.settings")
async def test_regional_endpoint_used(mock_settings):
    """Should use regional endpoint and return generation mix."""
    mock_settings.carbon_intensity_api_url = "https://api.carbonintensity.org.uk"
    mock_settings.datacenter_postcode = "SL1"
    mock_settings.carbon_intensity_fallback = 230.0

    client = CarbonIntensityClient()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=_MockResponse(_make_regional_response(150, "moderate")))
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.carbon_intensity.httpx.AsyncClient", return_value=mock_http):
        result = await client.get_current_intensity()

    assert isinstance(result, CarbonIntensityResult)
    assert result.intensity == 150.0
    assert "South England" in result.source
    assert result.region_name == "South England"
    assert result.index == "moderate"
    assert len(result.generation_mix) == 4
    assert result.generation_mix[0]["fuel"] == "gas"


@pytest.mark.asyncio
@patch("app.services.carbon_intensity.settings")
async def test_falls_back_to_national(mock_settings):
    """Should fall back to national when regional fails."""
    mock_settings.carbon_intensity_api_url = "https://api.carbonintensity.org.uk"
    mock_settings.datacenter_postcode = "SL1"
    mock_settings.carbon_intensity_fallback = 230.0

    client = CarbonIntensityClient()

    call_count = 0

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "regional" in url:
            raise Exception("regional unavailable")
        return _MockResponse(_make_national_response(actual=180))

    mock_http = AsyncMock()
    mock_http.get = mock_get
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.carbon_intensity.httpx.AsyncClient", return_value=mock_http):
        result = await client.get_current_intensity()

    assert result.intensity == 180.0
    assert "national" in result.source
    assert result.generation_mix == []


@pytest.mark.asyncio
@patch("app.services.carbon_intensity.settings")
async def test_falls_back_to_static(mock_settings):
    """Should fall back to static value when both APIs fail."""
    mock_settings.carbon_intensity_api_url = "https://api.carbonintensity.org.uk"
    mock_settings.datacenter_postcode = "SL1"
    mock_settings.carbon_intensity_fallback = 230.0

    client = CarbonIntensityClient()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=Exception("all APIs down"))
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.carbon_intensity.httpx.AsyncClient", return_value=mock_http):
        result = await client.get_current_intensity()

    assert result.intensity == 230.0
    assert "fallback" in result.source.lower()
    assert result.generation_mix == []
