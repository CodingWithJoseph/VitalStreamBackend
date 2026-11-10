from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: UUID
    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:-]+$")
    source_record_id: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1, le=9_007_199_254_740_991)
    metric: Literal["resting_heart_rate"] = "resting_heart_rate"
    value: float = Field(ge=10, le=300)
    unit: Literal["bpm"] = "bpm"
    observed_at: AwareDatetime
    synthetic: bool

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[ObservationInput] = Field(min_length=1, max_length=100)


class RecordResult(BaseModel):
    id: UUID
    status: Literal["created", "updated", "unchanged", "stale", "conflict", "deleted", "rejected"]


class BatchResult(BaseModel):
    results: list[RecordResult]


class ObservationOutput(ObservationInput):
    received_at: AwareDatetime


class ObservationPage(BaseModel):
    items: list[ObservationOutput]
    next_cursor: int | None


class Identity(BaseModel):
    id: str


class Insight(BaseModel):
    status: Literal["ready", "insufficient_data", "stale"]
    source: str
    method: str = "daily-median-mad-v1"
    metric: str = "resting_heart_rate"
    unit: str = "bpm"
    latest_value: float | None = None
    baseline: float | None = None
    deviation: float | None = None
    robust_score: float | None = None
    history_days: int = 0
    window_start: AwareDatetime
    generated_at: AwareDatetime
    explanation: str
