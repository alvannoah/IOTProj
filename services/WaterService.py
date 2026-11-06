from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.metrics import ValveEvent, YFS201Reading, utc_now
from services.aggregation import bucket_column, bucket_start, counter_delta
from services.BillingService import current_price

LITRES_PER_M3 = 1000


class WaterTelemetryService:
    def __init__(self, db: Session):
        self.db = db

    def read_water(self) -> YFS201Reading | None:
        """The most recent reading."""
        return self.db.scalar(select(YFS201Reading).order_by(YFS201Reading.id.desc()).limit(1))

    def write_water(
        self, flow_rate: float, total_volume: float, recorded_at: datetime | None = None
    ) -> YFS201Reading:
        previous = self.read_water()
        delta = counter_delta(previous.total_volume if previous else None, total_volume)
        price = current_price(self.db, "water")

        reading = YFS201Reading(
            flow_rate=flow_rate,
            total_volume=total_volume,
            volume_delta=delta,
            cost=None if price is None else delta / LITRES_PER_M3 * price,
            recorded_at=recorded_at or utc_now(),
        )
        self.db.add(reading)
        self.db.commit()
        self.db.refresh(reading)
        return reading

    def water_history(self, start: datetime, end: datetime, interval: str) -> list[dict]:
        bucket = bucket_column(YFS201Reading.recorded_at, interval)
        rows = self.db.execute(
            select(
                bucket,
                func.avg(YFS201Reading.flow_rate).label("avg_flow_rate"),
                func.max(YFS201Reading.flow_rate).label("max_flow_rate"),
                func.sum(YFS201Reading.volume_delta).label("volume_litres"),
                func.sum(YFS201Reading.cost).label("cost"),
            )
            .where(YFS201Reading.recorded_at >= start, YFS201Reading.recorded_at < end)
            .group_by(bucket)
            .order_by(bucket)
        ).all()
        return [
            {**row._asdict(), "timestamp": bucket_start(row.bucket)} for row in rows
        ]

    def read_valve(self) -> bool:
        """Whether the solenoid should be open. Closed until first told otherwise."""
        latest = self.db.scalar(select(ValveEvent).order_by(ValveEvent.id.desc()).limit(1))
        return latest.is_open if latest else False

    def write_valve(self, is_open: bool) -> ValveEvent:
        event = ValveEvent(is_open=is_open)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def valve_history(self, limit: int) -> list[ValveEvent]:
        return list(
            self.db.scalars(select(ValveEvent).order_by(ValveEvent.id.desc()).limit(limit))
        )
