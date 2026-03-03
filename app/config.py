import json

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Prometheus
    prometheus_url: str = "http://greenscope-prometheus:9090/prometheus"

    # UK Carbon Intensity API
    carbon_intensity_api_url: str = "https://api.carbonintensity.org.uk"
    carbon_intensity_fallback: float = 230.0
    datacenter_postcode: str = "SL1"  # DO LON1 = Equinix LD5, Slough

    # Host hardware configuration
    host_tdp_watts: float = 205.0
    host_cores: int = 2
    host_pue: float = 1.2
    host_embodied_co2_kg: float = 1205.52
    host_lifespan_years: float = 4.0

    # App boundaries — JSON string mapping app name to container names
    app_boundaries: str = '{"evm": ["evm-backend", "evm-frontend", "evm-db"], "equicalendar": ["compgather"], "meweb": ["caddy"]}'

    # App request jobs — JSON string mapping app name to Prometheus job name
    app_request_jobs: str = '{"evm": "evm-backend", "equicalendar": "compgather", "meweb": "caddy"}'

    # Calculation interval
    calculation_interval_minutes: int = 15

    # Database
    database_url: str = "sqlite+aiosqlite:///data/greenscope.db"

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": "GREENSCOPE_", "case_sensitive": False}

    def get_app_boundaries(self) -> dict[str, list[str]]:
        return json.loads(self.app_boundaries)

    def get_app_request_jobs(self) -> dict[str, str]:
        return json.loads(self.app_request_jobs)


settings = Settings()
