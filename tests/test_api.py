from datetime import UTC, datetime

import pytest

from services.aggregation import counter_delta
from services.BillingService import BillingService
from services.ElectricityService import ElectricityTelemetryService
from services.WaterService import WaterTelemetryService

ELECTRICITY = dict(voltage=230.1, current=1.5, power=340.0, energy=10.0, frequency=50.0, power_factor=0.95)


def at(*args):
    return datetime(*args, tzinfo=UTC)


def write_energy(db, energy, recorded_at, power=100.0):
    return ElectricityTelemetryService(db).write(230.0, 1.0, power, energy, 50.0, 0.9, recorded_at)


@pytest.mark.parametrize(
    "previous,current,expected",
    [(None, 500.0, 0.0), (10.0, 12.5, 2.5), (10.0, 10.0, 0.0), (10.0, 3.0, 3.0)],
)
def test_counter_delta(previous, current, expected):
    assert counter_delta(previous, current) == expected


def test_device_reading_is_stored_and_shown_as_latest(client):
    response = client.get("/api/device/electricity", params=ELECTRICITY)
    assert (response.status_code, response.text) == (200, "OK")

    latest = client.get("/api/electricity/latest").json()
    assert latest["voltage"] == 230.1
    assert latest["recorded_at"].endswith("Z")


def test_nan_from_failed_pzem_read_is_rejected(client):
    response = client.get("/api/device/electricity", params={**ELECTRICITY, "voltage": "nan"})
    assert response.status_code == 422
    assert client.get("/api/electricity/latest").status_code == 404


def test_out_of_range_power_factor_is_rejected(client):
    response = client.get("/api/device/electricity", params={**ELECTRICITY, "power_factor": 1.5})
    assert response.status_code == 422


def test_valve_defaults_closed_and_uses_plain_text_for_the_arduino(client):
    assert client.get("/api/valve").text == "0"
    assert client.post("/api/valve", json={"open": True}).json()["is_open"] is True
    assert client.get("/api/valve").text == "1"
    assert client.get("/api/status").json()["valve_open"] is True
    assert client.post("/api/valve", json={"open": False}).status_code == 200
    assert client.get("/api/valve").text == "0"
    assert [e["is_open"] for e in client.get("/api/valve/history").json()] == [False, True]


def test_status_reports_sensors_online_and_offline(client, db):
    assert client.get("/api/status").json()["electricity"] == {"online": False, "last_seen": None}

    client.get("/api/device/electricity", params=ELECTRICITY)
    WaterTelemetryService(db).write_water(1.0, 1.0, at(2020, 1, 1))

    body = client.get("/api/status").json()
    assert body["electricity"]["online"] is True
    assert body["water"]["online"] is False
    assert body["latest_water"]["total_volume"] == 1.0


def test_first_reading_of_a_lifetime_meter_is_not_billed(client, db):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 2.0})
    reading = write_energy(db, 5000.0, at(2026, 1, 1, 10))
    assert reading.energy_delta == 0
    assert reading.cost == 0


def test_cost_keeps_the_price_in_force_when_the_reading_arrived(client, db):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 2.0})
    write_energy(db, 10.0, at(2026, 1, 1, 10))
    write_energy(db, 11.0, at(2026, 1, 1, 11))
    client.put("/api/tariffs/electricity", json={"price_per_unit": 5.0})
    db.commit()  # real requests get a new session; end this one's MySQL read snapshot
    write_energy(db, 12.0, at(2026, 1, 1, 12))

    rows = client.get(
        "/api/electricity/history",
        params={"interval": "hour", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
    ).json()
    assert [row["cost"] for row in rows] == [0, 2.0, 5.0]


def test_price_change_applies_to_the_next_device_request(client):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 2.0})
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 10.0})
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 11.0})
    client.put("/api/tariffs/electricity", json={"price_per_unit": 5.0})
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 12.0})

    assert client.get("/api/summary").json()["today"]["electricity_cost"] == 7.0


def test_cost_noise_is_rounded_in_responses(client):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 0.2})
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 100.0})
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 101.5})

    assert client.get("/api/summary").json()["today"]["electricity_cost"] == 0.3
    assert client.get("/api/electricity/history").json()[0]["cost"] == 0.3


def test_cost_is_null_without_a_tariff_rather_than_a_fake_zero(client, db):
    write_energy(db, 10.0, at(2026, 1, 1, 10))
    write_energy(db, 11.0, at(2026, 1, 1, 11))
    usage = BillingService(db).usage(at(2026, 1, 1), at(2026, 1, 2))
    assert usage["energy_kwh"] == 1.0
    assert usage["electricity_cost"] is None
    assert usage["total_cost"] is None


def test_water_is_priced_per_m3_and_survives_an_arduino_reboot(client, db):
    client.put("/api/tariffs/water", json={"price_per_unit": 10.0})
    service = WaterTelemetryService(db)
    service.write_water(5.0, 100.0, at(2026, 1, 1, 10, 0))
    service.write_water(5.0, 150.0, at(2026, 1, 1, 10, 10))
    service.write_water(5.0, 20.0, at(2026, 1, 1, 10, 20))  # total went back to ~0: reboot

    rows = client.get(
        "/api/water/history",
        params={"interval": "day", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
    ).json()
    assert len(rows) == 1
    assert rows[0]["volume_litres"] == 70.0
    assert rows[0]["cost"] == pytest.approx(0.7)


def test_daily_buckets_split_at_local_midnight(client, db):
    # 20:30 and 21:30 UTC are either side of midnight at UTC+3.
    write_energy(db, 1.0, at(2026, 1, 1, 18))
    write_energy(db, 2.0, at(2026, 1, 1, 20, 30))
    write_energy(db, 4.0, at(2026, 1, 1, 21, 30))

    rows = client.get(
        "/api/electricity/history",
        params={"interval": "day", "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
    ).json()
    assert [row["timestamp"] for row in rows] == ["2025-12-31T21:00:00Z", "2026-01-01T21:00:00Z"]
    assert [row["energy_kwh"] for row in rows] == [1.0, 2.0]


def test_history_averages_and_peak_within_a_bucket(client, db):
    write_energy(db, 1.0, at(2026, 1, 1, 10, 0), power=100.0)
    write_energy(db, 2.0, at(2026, 1, 1, 10, 30), power=300.0)

    rows = client.get(
        "/api/electricity/history",
        params={"interval": "hour", "start": "2026-01-01T10:00:00Z", "end": "2026-01-01T11:00:00Z"},
    ).json()
    assert rows[0]["avg_power"] == 200.0
    assert rows[0]["max_power"] == 300.0


def test_history_end_is_exclusive(client, db):
    write_energy(db, 1.0, at(2026, 1, 1, 10))
    params = {"interval": "hour", "start": "2026-01-01T09:00:00Z", "end": "2026-01-01T10:00:00Z"}
    assert client.get("/api/electricity/history", params=params).json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"interval": "minute", "start": "2020-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"interval": "hour", "start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"interval": "fortnight"},
    ],
)
def test_bad_history_ranges_are_rejected(client, params):
    assert client.get("/api/electricity/history", params=params).status_code == 422


def test_summary_splits_today_from_month_and_projects_the_bill(client, db):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 1.0})
    write_energy(db, 0.0, at(2026, 3, 31, 20))  # previous local month, baseline only
    write_energy(db, 10.0, at(2026, 4, 1, 12))  # earlier this local month
    write_energy(db, 13.0, at(2026, 4, 15, 22))  # local 01:00 on the 16th

    # Local time 12:00 on 16 April: 15.5 of 30 days elapsed.
    result = BillingService(db).summary(now=at(2026, 4, 16, 9))
    assert result["today"]["energy_kwh"] == 3.0
    assert result["month"]["energy_kwh"] == 13.0
    assert result["projected_month"]["electricity_cost"] == pytest.approx(13.0 * 30 / 15.5)
    assert result["projected_month"]["water_cost"] is None


def test_summary_endpoint_includes_currency(client):
    body = client.get("/api/summary").json()
    assert body["currency"] == "TEST"
    assert body["today"]["energy_kwh"] == 0


def test_summary_includes_a_reading_from_the_current_second(client):
    client.put("/api/tariffs/electricity", json={"price_per_unit": 1.0})
    client.get("/api/device/electricity", params=ELECTRICITY)
    client.get("/api/device/electricity", params={**ELECTRICITY, "energy": 12.0})
    assert client.get("/api/summary").json()["today"]["energy_kwh"] == 2.0


def test_tariffs_start_unset_then_show_the_latest_price(client):
    assert [t["price_per_unit"] for t in client.get("/api/tariffs").json()] == [None, None]
    assert client.put("/api/tariffs/water", json={"price_per_unit": -1}).status_code == 422
    assert client.put("/api/tariffs/gas", json={"price_per_unit": 1}).status_code == 422

    client.put("/api/tariffs/water", json={"price_per_unit": 3.0})
    updated = client.put("/api/tariffs/water", json={"price_per_unit": 4.0}).json()
    assert updated["price_per_unit"] == 4.0
    assert updated["unit"] == "m3"
    water = next(t for t in client.get("/api/tariffs").json() if t["resource"] == "water")
    assert water["price_per_unit"] == 4.0
