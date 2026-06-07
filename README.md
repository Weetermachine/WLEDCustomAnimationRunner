# WLED Custom Animation Runner

A single-container web app that drives a custom **Flag Shimmer** animation on a
1378-LED WLED strip over the **DDP** protocol (UDP), with a scheduler for
clock-time and sunset-based automation. When the animation stops, WLED resumes
its own playlist automatically after its DDP timeout (~2500 ms).

## Stack

- **FastAPI** backend (`main.py`)
- **SQLite** persistence (`database.py`)
- **APScheduler** schedule evaluation, re-checked every minute (`scheduler.py`)
- **astral** for sunset/sunrise (`scheduler.py`)
- **Plain HTML/JS** dark-theme frontend (`static/index.html`)
- Single `Dockerfile` + `docker-compose.yml`, exposed on **port 8093**

## The animation — Flag Shimmer

`strip_colors.py` holds `stripColors`, a 1378-element list of `'RED'`,
`'WHITE'`, `'BLUE'`. A brightness wave (11 levels, ping-ponging 0→10→0) scrolls
across the strip at 30 FPS. Colors are `RED=(b,0,0)`, `WHITE=(b,b,b)`,
`BLUE=(0,0,b)`, scaled by master brightness.

> The `strip_colors.py` in this repo is a **placeholder** that generates a
> runnable banded pattern. Replace it with the real 1378-element map.

## DDP transport

10-byte header, ≤480-byte payload (160 RGB pixels) per packet, rolling sequence
number, big-endian byte offset and length. Sent to the WLED IP on UDP port
**4048**.

## Settings (persisted)

- WLED IP (default `192.168.50.250`)
- Latitude / longitude (default Salt Lake City `40.7608, -111.8910`)
- Speed multiplier (0.5×–3×)
- Master brightness (0–255)

## Schedules (persisted)

Each schedule has a name, a start (clock `HH:MM` **or** `sunset` ± offset
minutes), a clock end time, active weekdays and/or specific calendar dates, and
an enable toggle. Manual start/stop is always available and is not fought by the
scheduler minute-to-minute.

## Deploy (TrueNAS SCALE via shell)

```sh
git clone git@github.com:Weetermachine/WLEDCustomAnimationRunner.git
cd WLEDCustomAnimationRunner
# replace strip_colors.py with the real color map
docker compose up -d --build
```

Open `http://<host>:8093`. The SQLite DB lives in the `wled_data` named volume
and survives container restarts. Set `TZ` in `docker-compose.yml` so sunset
times and schedules use your local timezone.
