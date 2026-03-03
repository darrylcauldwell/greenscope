import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Caddy uses a different metric name than FastAPI apps
CADDY_REQUEST_METRIC = "caddy_http_requests_total"
FASTAPI_REQUEST_METRIC = "http_request_duration_seconds_count"


class PrometheusClient:
    """Async client for querying the Prometheus HTTP API."""

    def __init__(self) -> None:
        self.base_url = settings.prometheus_url

    async def get_container_cpu_seconds(
        self,
        container_names: list[str],
        period_seconds: int,
    ) -> dict[str, float]:
        """Get CPU seconds consumed per container over the measurement period."""
        names_regex = "|".join(container_names)
        query = f'sum by (name) (increase(container_cpu_usage_seconds_total{{name=~"{names_regex}"}}[{period_seconds}s]))'

        result = await self._query(query)
        cpu_by_container: dict[str, float] = {}

        for item in result:
            name = item["metric"].get("name", "")
            value = float(item["value"][1])
            cpu_by_container[name] = value

        return cpu_by_container

    async def get_request_count(self, job: str, period_seconds: int) -> int:
        """Get total HTTP request count for an app over the measurement period."""
        # Try FastAPI metric first, then Caddy metric
        for metric in [FASTAPI_REQUEST_METRIC, CADDY_REQUEST_METRIC]:
            query = f'sum(increase({metric}{{job="{job}"}}[{period_seconds}s]))'
            result = await self._query(query)

            if result:
                return int(float(result[0]["value"][1]))

        return 0

    async def _query(self, promql: str) -> list[dict]:
        """Execute a PromQL instant query."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": promql},
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    logger.warning("Prometheus query failed: %s", data.get("error", "unknown"))
                    return []

                return data.get("data", {}).get("result", [])

        except Exception as e:
            logger.warning("Prometheus query error (%s): %s", promql[:80], e)
            return []
