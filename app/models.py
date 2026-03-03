from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SCIScore(Base):
    __tablename__ = "sci_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    energy_kwh: Mapped[float] = mapped_column(Float)
    carbon_intensity: Mapped[float] = mapped_column(Float)
    operational_emissions: Mapped[float] = mapped_column(Float)
    embodied_emissions: Mapped[float] = mapped_column(Float)
    total_carbon: Mapped[float] = mapped_column(Float)
    request_count: Mapped[int] = mapped_column(Integer)
    sci_score: Mapped[float] = mapped_column(Float)
    cpu_seconds: Mapped[float] = mapped_column(Float)
    calculation_period_seconds: Mapped[int] = mapped_column(Integer)

    __table_args__ = (Index("ix_sci_scores_app_timestamp", "app_name", "timestamp"),)
