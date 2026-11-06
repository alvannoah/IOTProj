"""Endpoints the Arduino calls.

These are GET requests with plain-text replies because that is the easiest thing to
send and parse over a WiFi module. A failed PZEM read gives NaN, which is rejected with
a 422 instead of being stored.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from config.database import get_db
from services.ElectricityService import ElectricityTelemetryService
from services.WaterService import WaterTelemetryService

router = APIRouter(prefix="/api", tags=["device"])

Measurement = Annotated[float, Query(ge=0, allow_inf_nan=False)]


@router.get("/device/electricity", response_class=PlainTextResponse)
def post_electricity(
    voltage: Measurement,
    current: Measurement,
    power: Measurement,
    energy: Measurement,
    frequency: Measurement,
    power_factor: Annotated[float, Query(ge=0, le=1, allow_inf_nan=False)],
    db: Session = Depends(get_db),
):
    ElectricityTelemetryService(db).write(voltage, current, power, energy, frequency, power_factor)
    return "OK"


@router.get("/device/water", response_class=PlainTextResponse)
def post_water(
    flow_rate: Measurement,
    total_volume: Measurement,
    db: Session = Depends(get_db),
):
    WaterTelemetryService(db).write_water(flow_rate, total_volume)
    return "OK"


@router.get("/valve", response_class=PlainTextResponse)
def get_valve(db: Session = Depends(get_db)):
    """Polled by the Arduino: "1" means open the solenoid, "0" means close it."""
    return "1" if WaterTelemetryService(db).read_valve() else "0"
