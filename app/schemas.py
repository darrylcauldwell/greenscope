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


class SCICurrentResponse(BaseModel):
    scores: list[SCIComponent]
    carbon_intensity_source: str
    calculated_at: datetime


class SCIHistoryResponse(BaseModel):
    app_name: str
    scores: list[SCIComponent]
    hours: int
