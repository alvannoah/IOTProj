import calendar
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.metrics import PZEMReading, Tariff, YFS201Reading, utc_now
from services.aggregation import as_utc, local_tz

UNITS = {"electricity": "kWh", "water": "m3"}


def latest_tariff(db: Session, resource: str) -> Tariff | None:
    return db.scalar(
        select(Tariff).where(Tariff.resource == resource).order_by(Tariff.id.desc()).limit(1)
    )


def current_price(db: Session, resource: str) -> float | None:
    tariff = latest_tariff(db, resource)
    return tariff.price_per_unit if tariff else None


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def get_tariff(self, resource: str) -> Tariff | None:
        return latest_tariff(self.db, resource)

    def set_tariff(self, resource: str, price_per_unit: float) -> Tariff:
        """Applies to new readings only; costs are fixed when a reading arrives."""
        tariff = Tariff(resource=resource, price_per_unit=price_per_unit)
        self.db.add(tariff)
        self.db.commit()
        self.db.refresh(tariff)
        return tariff

    def usage(self, start: datetime, end: datetime) -> dict:
        energy, electricity_cost = self.db.execute(
            select(func.sum(PZEMReading.energy_delta), func.sum(PZEMReading.cost)).where(
                PZEMReading.recorded_at >= start, PZEMReading.recorded_at < end
            )
        ).one()
        litres, water_cost = self.db.execute(
            select(func.sum(YFS201Reading.volume_delta), func.sum(YFS201Reading.cost)).where(
                YFS201Reading.recorded_at >= start, YFS201Reading.recorded_at < end
            )
        ).one()
        return _usage_figures(energy or 0.0, litres or 0.0, electricity_cost, water_cost)

    def summary(self, now: datetime | None = None) -> dict:
        now = as_utc(now) if now else utc_now()
        local_now = now.astimezone(local_tz())
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        days_in_month = calendar.monthrange(local_now.year, local_now.month)[1]

        # The end is exclusive, so step past "now" to include a reading from this very second.
        end = now + timedelta(seconds=1)
        month = self.usage(month_start, end)

        elapsed = (local_now - month_start).total_seconds()
        scale = (days_in_month * 86400) / elapsed if elapsed > 0 else None

        return {
            "today": self.usage(day_start, end),
            "month": month,
            "projected_month": _project(month, scale),
        }


def _usage_figures(energy, litres, electricity_cost, water_cost) -> dict:
    known = [cost for cost in (electricity_cost, water_cost) if cost is not None]
    return {
        "energy_kwh": energy,
        "water_litres": litres,
        "electricity_cost": electricity_cost,
        "water_cost": water_cost,
        "total_cost": sum(known) if known else None,
    }


def _project(month: dict, scale: float | None) -> dict | None:
    """Straight-line estimate of the full month from the month so far."""
    if scale is None:
        return None
    return {
        key: None if value is None else value * scale
        for key, value in month.items()
    }
