import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class CarbonIntensityClient:
    """Async client for the UK Carbon Intensity API."""

    def __init__(self) -> None:
        self.api_url = settings.carbon_intensity_api_url
        self.fallback_value = settings.carbon_intensity_fallback

    async def get_current_intensity(self) -> tuple[float, str]:
        """Fetch current carbon intensity in gCO2eq/kWh.

        Returns (intensity, source_description).
        Falls back to configured static value when API is unreachable.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url)
                response.raise_for_status()
                data = response.json()

                intensity_data = data["data"][0]["intensity"]
                actual = intensity_data.get("actual")
                forecast = intensity_data.get("forecast")

                if actual is not None:
                    return float(actual), "UK Carbon Intensity API (actual)"
                elif forecast is not None:
                    return float(forecast), "UK Carbon Intensity API (forecast)"
                else:
                    logger.warning("Carbon intensity API returned no actual or forecast value, using fallback")
                    return self.fallback_value, f"Fallback ({self.fallback_value} gCO2eq/kWh UK annual average)"

        except Exception as e:
            logger.warning("Carbon intensity API unavailable (%s), using fallback", e)
            return self.fallback_value, f"Fallback ({self.fallback_value} gCO2eq/kWh UK annual average)"
