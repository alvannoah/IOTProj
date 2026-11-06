"""JSON endpoints for the frontend. All timestamps are UTC."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config.database import get_db
from config.settings import settings
from models.metrics import utc_now
from schemas import (
    ElectricityBucket,
    ElectricityReadingOut,
    Interval,
    Resource,
    StatusOut,
    SummaryOut,
    TariffOut,
    TariffUpdate,
    ValveCommand,
    ValveEventOut,
    WaterBucket,
    WaterReadingOut,
)
from services.aggregation import INTERVAL_SECONDS, as_utc
from services.BillingService import UNITS, BillingService
from services.ElectricityService import ElectricityTelemetryService
from services.WaterService import WaterTelemetryService

router = APIRouter(prefix="/api", tags=["dashboard"])

MAX_BUCKETS = 5000


def resolve_range(
    start: datetime | None, end: datetime | None, interval: str
) -> tuple[datetime, datetime]:
    """Default to the last 24 hours, and refuse ranges too large to graph."""
    # The end is exclusive, so step past "now" to include a reading from this very second.
    end = as_utc(end) if end else utc_now() + timedelta(seconds=1)
    start = as_utc(start) if start else end - timedelta(hours=24)
    if start >= end:
        raise HTTPException(status_code=422, detail="start must be before end")
    if (end - start).total_seconds() / INTERVAL_SECONDS[interval] > MAX_BUCKETS:
        raise HTTPException(
            status_code=422,
            detail=f"Range is over {MAX_BUCKETS} {interval}s; use a shorter range or larger interval",
        )
    return start, end


def sensor_status(last_seen: datetime | None) -> dict:
    limit = timedelta(seconds=settings.device_offline_after_seconds)
    return {
        "online": last_seen is not None and utc_now() - last_seen <= limit,
        "last_seen": last_seen,
    }


@router.get("/status", response_model=StatusOut)
def status(db: Session = Depends(get_db)):
    water_service = WaterTelemetryService(db)
    electricity = ElectricityTelemetryService(db).read()
    water = water_service.read_water()
    return {
        "valve_open": water_service.read_valve(),
        "electricity": sensor_status(electricity.recorded_at if electricity else None),
        "water": sensor_status(water.recorded_at if water else None),
        "latest_electricity": electricity,
        "latest_water": water,
    }


@router.get("/electricity/history", response_model=list[ElectricityBucket])
def electricity_history(
    interval: Interval = "hour",
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    start, end = resolve_range(start, end, interval)
    return ElectricityTelemetryService(db).history(start, end, interval)


@router.get("/electricity/latest", response_model=ElectricityReadingOut)
def electricity_latest(db: Session = Depends(get_db)):
    reading = ElectricityTelemetryService(db).read()
    if reading is None:
        raise HTTPException(status_code=404, detail="No electricity readings yet")
    return reading


@router.get("/water/history", response_model=list[WaterBucket])
def water_history(
    interval: Interval = "hour",
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    start, end = resolve_range(start, end, interval)
    return WaterTelemetryService(db).water_history(start, end, interval)


@router.get("/water/latest", response_model=WaterReadingOut)
def water_latest(db: Session = Depends(get_db)):
    reading = WaterTelemetryService(db).read_water()
    if reading is None:
        raise HTTPException(status_code=404, detail="No water readings yet")
    return reading


@router.post("/valve", response_model=ValveEventOut)
def set_valve(command: ValveCommand, db: Session = Depends(get_db)):
    return WaterTelemetryService(db).write_valve(command.open)


@router.get("/valve/history", response_model=list[ValveEventOut])
def valve_history(limit: int = Query(50, ge=1, le=1000), db: Session = Depends(get_db)):
    return WaterTelemetryService(db).valve_history(limit)


@router.get("/summary", response_model=SummaryOut)
def summary(db: Session = Depends(get_db)):
    return {"currency": settings.currency, **BillingService(db).summary()}


def _tariff_out(resource: str, tariff) -> dict:
    return {
        "resource": resource,
        "unit": UNITS[resource],
        "currency": settings.currency,
        "price_per_unit": tariff.price_per_unit if tariff else None,
        "effective_from": tariff.effective_from if tariff else None,
    }


@router.get("/tariffs", response_model=list[TariffOut])
def get_tariffs(db: Session = Depends(get_db)):
    service = BillingService(db)
    return [_tariff_out(resource, service.get_tariff(resource)) for resource in UNITS]


@router.put("/tariffs/{resource}", response_model=TariffOut)
def set_tariff(resource: Resource, update: TariffUpdate, db: Session = Depends(get_db)):
    return _tariff_out(resource, BillingService(db).set_tariff(resource, update.price_per_unit))
