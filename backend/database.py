"""
SQLAlchemy ORM + storage layer.

Schema is deliberately shaped for the three downstream consumers:

  * 3D map columns      -> Reading has lat/lon, sub_index (height),
                           category_index/color_hex (colour)
  * historical slider   -> every Reading is timestamped (datetime_utc) and we
                           keep history; (sensors_id, datetime_utc) is unique so
                           re-refreshing doesn't create duplicates
  * arrondissement agg  -> Location has an `arrondissement` column ready to fill

Locations and Readings are split (normalised) so station metadata isn't
repeated on every reading and the map can draw stations even before values load.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, String, Integer, Float, DateTime, ForeignKey,
    UniqueConstraint, func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker,
)

from config import settings


class Base(DeclarativeBase):
    pass


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # OpenAQ location id
    name: Mapped[str | None] = mapped_column(String)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str | None] = mapped_column(String)
    provider: Mapped[str | None] = mapped_column(String)
    arrondissement: Mapped[int | None] = mapped_column(Integer)  # Phase C
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    readings: Mapped[list["Reading"]] = relationship(back_populates="location")


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        # idempotent ingestion: same sensor + same timestamp == same reading
        UniqueConstraint("sensors_id", "datetime_utc", name="uq_sensor_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    sensors_id: Mapped[int] = mapped_column(Integer, index=True)
    parameter: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float] = mapped_column(Float)
    units: Mapped[str | None] = mapped_column(String)
    datetime_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    datetime_local: Mapped[str | None] = mapped_column(String)
    category_index: Mapped[int | None] = mapped_column(Integer)
    category_label: Mapped[str | None] = mapped_column(String)
    color_hex: Mapped[str | None] = mapped_column(String)
    sub_index: Mapped[float | None] = mapped_column(Float)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    location: Mapped["Location"] = relationship(back_populates="readings")


# SQLite needs check_same_thread=False to be used across FastAPI's threadpool.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    Base.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
