# IOTProj
 IOT project for Group 4 tracking electricity and water usage

FastAPI backend that stores readings from an Arduino (PZEM AC meter, YF-S201 water flow
meter), controls the solenoid valve, and serves graph and pricing data to the frontend.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # then fill in DATABASE_URL, UTC_OFFSET_MINUTES and CURRENCY
```

Create the database once (tables are created automatically when the app starts):

```sql
CREATE DATABASE iot_system;
```

Run it. `--host 0.0.0.0` is what lets the Arduino reach it over WiFi:

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

The Arduino uses this computer's LAN IP (`hostname -I`) rather than `localhost`.
Interactive API docs are at http://127.0.0.1:8000/docs.

Set both prices with `PUT /api/tariffs/...` before collecting data. A reading's cost is
fixed when it arrives, so readings received with no tariff set stay unpriced (`null`).

## Arduino endpoints

All are GET requests with plain-text replies. A reply of `OK` means the reading was stored.

| Request | Purpose |
| --- | --- |
| `/api/device/electricity?voltage=&current=&power=&energy=&frequency=&power_factor=` | Send a PZEM reading |
| `/api/device/water?flow_rate=&total_volume=` | Send a flow meter reading |
| `/api/valve` | Poll the valve: `1` = open, `0` = closed |

Units: V, A, W, kWh, Hz, L/min, L. `energy` and `total_volume` are running totals, and
a total going backwards (e.g. after a reboot) is handled as a counter reset. A failed
PZEM read gives `NaN`, which gets a 422 reply and is not stored.

## Frontend endpoints

All are JSON. Timestamps are UTC; convert them for display.

| Request | Purpose |
| --- | --- |
| `GET /api/status` | Valve state, sensors online/offline, latest readings |
| `GET /api/summary` | Usage and cost for today and this month, plus projected month |
| `GET /api/electricity/history` | Graph data: averages, peak, kWh and cost per bucket |
| `GET /api/water/history` | Graph data: flow, litres and cost per bucket |
| `GET /api/electricity/latest`, `GET /api/water/latest` | Most recent reading (404 if none) |
| `POST /api/valve` `{"open": true}` | Open or close the solenoid |
| `GET /api/valve/history?limit=50` | Past valve changes, newest first |
| `GET /api/tariffs` | Current prices |
| `PUT /api/tariffs/{electricity\|water}` `{"price_per_unit": 0.2}` | Set a price (per kWh / per m3) |

History takes `interval` (`minute`, `hour`, `day`; default `hour`) and optional `start`
and `end` (ISO 8601, e.g. `2026-11-01T00:00:00Z`; default last 24 hours). Periods with
no readings are left out, so gaps in the data stay visible. A `cost` is `null` when no
tariff was set.

## Tests

```bash
.venv/bin/python -m pytest
```

These use a temporary SQLite file. To run them on MySQL, set `TEST_DATABASE_URL` to a
**throwaway** database; every table in it is dropped.
