from datetime import datetime

from pydantic import BaseModel


class SCIComponent(BaseModel):
    app_name: str
    timestamp: datetime
    energy_kwh: float
    carbon_intensity: float
    operational_emissions: float
    embodied_emissions: float
    total_carbon: float
    request_count: int
    sci_score: float
    cpu_seconds: float
    calculation_period_seconds: int

    model_config = {"from_attributes": True}


class GenerationMixEntry(BaseModel):
    fuel: str
    perc: float


class SCICurrentResponse(BaseModel):
    scores: list[SCIComponent]
    carbon_intensity_source: str
    carbon_intensity_region: str = ""
    carbon_intensity_index: str = ""
    generation_mix: list[GenerationMixEntry] = []
    calculated_at: datetime


class SCIHistoryResponse(BaseModel):
    app_name: str
    scores: list[SCIComponent]
    hours: int


class AggregatedAppScore(BaseModel):
    app_name: str
    energy_kwh: float
    carbon_intensity: float
    operational_emissions: float
    embodied_emissions: float
    total_carbon: float
    request_count: int
    sci_score: float
    cpu_seconds: float
    snapshot_count: int


class DropletSummary(BaseModel):
    energy_kwh: float
    operational_emissions: float
    embodied_emissions: float
    total_carbon: float
    request_count: int
    sci_score: float
    container_count: int


class AggregatedSCIResponse(BaseModel):
    window_minutes: int
    scores: list[AggregatedAppScore]
    droplet: DropletSummary | None = None
    display_names: dict[str, str]
    boundaries: dict[str, list[str]]
