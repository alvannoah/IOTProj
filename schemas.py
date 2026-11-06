from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Resource = Literal["electricity", "water"]
Interval = Literal["minute", "hour", "day"]

# Sums of floats pick up noise like 0.30000000000000004, so aggregates are rounded on the way out.
Rounded = Annotated[float, AfterValidator(lambda value: round(value, 4))]


class ElectricityReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    voltage: float
    current: float
    power: float
    energy: float
    frequency: float
    power_factor: float
    recorded_at: datetime


class WaterReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flow_rate: float
    total_volume: float
    recorded_at: datetime


class ElectricityBucket(BaseModel):
    timestamp: datetime
    avg_voltage: Rounded
    avg_current: Rounded
    avg_power: Rounded
    max_power: Rounded
    avg_frequency: Rounded
    avg_power_factor: Rounded
    energy_kwh: Rounded
    cost: Rounded | None


class WaterBucket(BaseModel):
    timestamp: datetime
    avg_flow_rate: Rounded
    max_flow_rate: Rounded
    volume_litres: Rounded
    cost: Rounded | None


class ValveCommand(BaseModel):
    open: bool


class ValveEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_open: bool
    changed_at: datetime


class TariffUpdate(BaseModel):
    price_per_unit: float = Field(ge=0, allow_inf_nan=False)


class TariffOut(BaseModel):
    resource: Resource
    unit: str
    currency: str
    price_per_unit: float | None
    effective_from: datetime | None


class UsageFigures(BaseModel):
    energy_kwh: Rounded
    water_litres: Rounded
    electricity_cost: Rounded | None
    water_cost: Rounded | None
    total_cost: Rounded | None


class SummaryOut(BaseModel):
    currency: str
    today: UsageFigures
    month: UsageFigures
    projected_month: UsageFigures | None


class SensorStatus(BaseModel):
    online: bool
    last_seen: datetime | None


class StatusOut(BaseModel):
    valve_open: bool
    electricity: SensorStatus
    water: SensorStatus
    latest_electricity: ElectricityReadingOut | None
    latest_water: WaterReadingOut | None
