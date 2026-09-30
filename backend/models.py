"""
Pydantic schemas.

Two layers on purpose:
  1. Raw* models mirror the OpenAQ v3 JSON exactly. They are the "validate the
     contract" step — if OpenAQ changes a field, parsing fails here with a clear
     error instead of producing garbage rows three steps later.
  2. CleanReading is OUR shape: flat, enriched with severity, ready to store and
     to serve to the frontend. The pipeline's job is to turn (1) into (2).
"""
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ---------- Layer 1: raw OpenAQ v3 contract ----------

class RawCoordinates(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class RawParameter(BaseModel):
    id: int
    name: str
    units: str | None = None
    displayName: str | None = None


class RawSensor(BaseModel):
    id: int
    name: str | None = None
    parameter: RawParameter


class RawLocation(BaseModel):
    id: int
    name: str | None = None
    locality: str | None = None
    timezone: str | None = None
    coordinates: RawCoordinates = Field(default_factory=RawCoordinates)
    sensors: list[RawSensor] = Field(default_factory=list)
    provider: dict | None = None


class RawDatetime(BaseModel):
    utc: datetime
    local: str | None = None


class RawLatest(BaseModel):
    datetime: RawDatetime
    value: float | None = None
    coordinates: RawCoordinates = Field(default_factory=RawCoordinates)
    sensorsId: int
    locationsId: int


class OpenAQResponse(BaseModel):
    """Generic envelope: {"meta": {...}, "results": [...]}"""
    meta: dict = Field(default_factory=dict)
    results: list = Field(default_factory=list)


# ---------- Layer 2: our clean, enriched shape ----------

class CleanReading(BaseModel):
    location_id: int
    location_name: str | None
    sensors_id: int
    parameter: str
    value: float
    units: str | None
    latitude: float
    longitude: float
    datetime_utc: datetime
    datetime_local: str | None
    # enrichment (from aqi.classify)
    category_index: int | None
    category_label: str | None
    color_hex: str | None
    sub_index: float | None
    arrondissement: int | None = None  # filled in Phase C (point-in-polygon)

    @field_validator("parameter")
    @classmethod
    def lower_param(cls, v: str) -> str:
        return v.lower()
