from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.metrics import PZEMReading, utc_now
from services.aggregation import bucket_column, bucket_start, counter_delta
from services.BillingService import current_price


class ElectricityTelemetryService:
    def __init__(self, db: Session):
        self.db = db

    def read(self) -> PZEMReading | None:
        """The most recent reading."""
        return self.db.scalar(select(PZEMReading).order_by(PZEMReading.id.desc()).limit(1))

    def write(
        self,
        voltage: float,
        current: float,
        power: float,
        energy: float,
        frequency: float,
        power_factor: float,
        recorded_at: datetime | None = None,
    ) -> PZEMReading:
        previous = self.read()
        delta = counter_delta(previous.energy if previous else None, energy)
        price = current_price(self.db, "electricity")

        reading = PZEMReading(
            voltage=voltage,
            current=current,
            power=power,
            energy=energy,
            frequency=frequency,
            power_factor=power_factor,
            energy_delta=delta,
            cost=None if price is None else delta * price,
            recorded_at=recorded_at or utc_now(),
        )
        self.db.add(reading)
        self.db.commit()
        self.db.refresh(reading)
        return reading

    def history(self, start: datetime, end: datetime, interval: str) -> list[dict]:
        bucket = bucket_column(PZEMReading.recorded_at, interval)
        rows = self.db.execute(
            select(
                bucket,
                func.avg(PZEMReading.voltage).label("avg_voltage"),
                func.avg(PZEMReading.current).label("avg_current"),
                func.avg(PZEMReading.power).label("avg_power"),
                func.max(PZEMReading.power).label("max_power"),
                func.avg(PZEMReading.frequency).label("avg_frequency"),
                func.avg(PZEMReading.power_factor).label("avg_power_factor"),
                func.sum(PZEMReading.energy_delta).label("energy_kwh"),
                func.sum(PZEMReading.cost).label("cost"),
            )
            .where(PZEMReading.recorded_at >= start, PZEMReading.recorded_at < end)
            .group_by(bucket)
            .order_by(bucket)
        ).all()
        return [
            {**row._asdict(), "timestamp": bucket_start(row.bucket)} for row in rows
        ]
