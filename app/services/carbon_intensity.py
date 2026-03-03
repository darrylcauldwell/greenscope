import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CarbonIntensityResult:
    intensity: float
    source: str
    region_name: str = ""
    index: str = ""
    generation_mix: list[dict] = field(default_factory=list)


class CarbonIntensityClient:
    """Async client for the UK Carbon Intensity API.

    Uses the regional endpoint for the datacenter's grid region,
    falling back to the national endpoint, then a static value.
    """

    def __init__(self) -> None:
        self.base_url = settings.carbon_intensity_api_url
        self.postcode = settings.datacenter_postcode
        self.fallback_value = settings.carbon_intensity_fallback

    async def get_current_intensity(self) -> CarbonIntensityResult:
        """Fetch current carbon intensity with generation mix.

        Fallback chain: regional postcode → national → static value.
        """
        # Try regional endpoint first
        result = await self._try_regional()
        if result:
            return result

        # Fall back to national endpoint
        result = await self._try_national()
        if result:
            return result

        # Static fallback
        logger.warning("All carbon intensity sources failed, using static fallback")
        return CarbonIntensityResult(
            intensity=self.fallback_value,
            source=f"Static fallback ({self.fallback_value} gCO2eq/kWh UK average)",
        )

    async def _try_regional(self) -> CarbonIntensityResult | None:
        """Query regional endpoint by datacenter postcode."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/regional/postcode/{self.postcode}",
                )
                response.raise_for_status()
                data = response.json()

                region = data["data"][0]
                period = region["data"][0]
                intensity = period["intensity"]

                forecast = intensity.get("forecast")
                if forecast is None:
                    return None

                generation_mix = period.get("generationmix", [])

                return CarbonIntensityResult(
                    intensity=float(forecast),
                    source=f"UK Carbon Intensity API — {region['shortname']} ({self.postcode})",
                    region_name=region.get("shortname", ""),
                    index=intensity.get("index", ""),
                    generation_mix=generation_mix,
                )

        except Exception as e:
            logger.warning("Regional carbon intensity query failed (%s): %s", self.postcode, e)
            return None

    async def _try_national(self) -> CarbonIntensityResult | None:
        """Query national endpoint as fallback."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/intensity",
                )
                response.raise_for_status()
                data = response.json()

                intensity_data = data["data"][0]["intensity"]
                actual = intensity_data.get("actual")
                forecast = intensity_data.get("forecast")

                value = actual if actual is not None else forecast
                if value is None:
                    return None

                source_type = "actual" if actual is not None else "forecast"

                return CarbonIntensityResult(
                    intensity=float(value),
                    source=f"UK Carbon Intensity API — national ({source_type})",
                )

        except Exception as e:
            logger.warning("National carbon intensity query failed: %s", e)
            return None
