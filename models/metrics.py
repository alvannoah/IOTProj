from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Double, Integer, String
from sqlalchemy.types import TypeDecorator

from config.database import Base


def utc_now() -> datetime:
    # Whole seconds: MySQL DATETIME has no fraction and would round up otherwise.
    return datetime.now(UTC).replace(microsecond=0)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in the database and always returns aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class PZEMReading(Base):
    __tablename__ = "electricity_telemetry"

    id = Column(Integer, primary_key=True)
    voltage = Column(Double, nullable=False)  # V
    current = Column(Double, nullable=False)  # A
    power = Column(Double, nullable=False)  # W
    energy = Column(Double, nullable=False)  # kWh, the meter's running total
    frequency = Column(Double, nullable=False)  # Hz
    power_factor = Column(Double, nullable=False)
    energy_delta = Column(Double, nullable=False, default=0.0)  # kWh used since the last reading
    cost = Column(Double, nullable=True)  # price of energy_delta; NULL if no tariff was set
    recorded_at = Column(UTCDateTime, nullable=False, default=utc_now, index=True)


class YFS201Reading(Base):
    __tablename__ = "water_telemetry"

    id = Column(Integer, primary_key=True)
    flow_rate = Column(Double, nullable=False)  # L/min
    total_volume = Column(Double, nullable=False)  # L, the Arduino's running total
    volume_delta = Column(Double, nullable=False, default=0.0)  # L used since the last reading
    cost = Column(Double, nullable=True)  # price of volume_delta; NULL if no tariff was set
    recorded_at = Column(UTCDateTime, nullable=False, default=utc_now, index=True)


class ValveEvent(Base):
    """Every solenoid change. The newest row is the current state, so it survives restarts."""

    __tablename__ = "valve_events"

    id = Column(Integer, primary_key=True)
    is_open = Column(Boolean, nullable=False)
    changed_at = Column(UTCDateTime, nullable=False, default=utc_now, index=True)


class Tariff(Base):
    """Price history. The newest row per resource applies to incoming readings."""

    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True)
    resource = Column(String(20), nullable=False, index=True)  # electricity | water
    price_per_unit = Column(Double, nullable=False)  # per kWh | per m3
    effective_from = Column(UTCDateTime, nullable=False, default=utc_now)
