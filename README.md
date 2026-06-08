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

## Animations

Animations are pluggable. The `animator.py` loop owns the DDP transport and
30 FPS pacing; the per-frame pixels come from whichever animation is selected in
the Settings panel (persisted as the `animation` setting). The strip's
`strip_colors.py` holds `stripColors`, a 1378-element list of `'RED'`,
`'WHITE'`, `'BLUE'`, handed to animations as `ctx.colors`.

Ships with:

- **Flag Shimmer** (`animations/flag_shimmer.py`) — the original effect; a
  brightness wave (11 levels, ping-ponging 0→10→0) scrolls across the
  RED/WHITE/BLUE map. Written as a *generator* so its scroll phase accumulates
  smoothly even as speed changes.
- **Rainbow Scroll** (`animations/rainbow.py`) — a moving hue gradient, written
  as a *stateless frame function*.

### Adding an animation

Drop a module in `animations/` and decorate a function with `@animation(key,
label)`. Two styles, auto-detected:

```python
from animations import animation

# Stateless: pure function of the frame index. Easy to write/test.
@animation("my_fx", "My Effect")
def my_fx(frame, n_leds, ctx):
    buf = bytearray(n_leds * 3)
    ...                      # ctx.speed, ctx.brightness, ctx.colors are live
    return bytes(buf)

# Stateful: a generator (note `yield`). Good for effects that carry state.
@animation("my_gen", "My Generator")
def my_gen(ctx):
    while True:
        buf = bytearray(ctx.n_leds * 3)
        ...
        yield bytes(buf)
```

Return/yield a `bytes` buffer of length `n_leds * 3` (RGB). `ctx.speed` (0.5–3)
and `ctx.brightness` (0–255) are updated every frame — read them inside the loop
to respond to settings and schedule changes. Rebuild the image (`redeploy-wled`)
and the new animation appears in the dropdown automatically; pass `default=True`
to make one the default.

> The `strip_colors.py` in this repo is a **placeholder** that generates a
> runnable banded pattern. Replace it with the real 1378-element map.

## DDP transport

10-byte header, ≤480-byte payload (160 RGB pixels) per packet, rolling sequence
number, big-endian byte offset and length. Sent to the WLED IP on UDP port
**4048**.

## Settings (persisted)

- WLED IP (default `192.168.50.250`)
- Latitude / longitude (default Salt Lake City `40.7608, -111.8910`)
- Timezone (IANA name, default `America/Denver`)
- Speed multiplier (0.5×–3×)
- Master brightness (0–255)

## Schedules (persisted)

Each schedule has a name, a start (clock `HH:MM` **or** `sunset` ± offset
minutes), a clock end time, and an enable toggle. You choose *when* it applies
with any combination of:

- **Weekdays** (e.g. Fri/Sat)
- **A date range** — *active from* / *active until* (inclusive). A range bounds
  the chosen weekdays to that span (e.g. Fri/Sat *only June 1 – Aug 31*). A range
  with no weekdays selected means every day in the span.
- **Specific calendar dates** — one-off days (e.g. `2026-07-04`), always honored
  regardless of the range.

Manual start/stop is always available and is not fought by the scheduler
minute-to-minute.

All schedule and sunset math runs in the configured **timezone** (default
`America/Denver` / Mountain), set in the Settings panel and independent of the
host clock. The image bundles `tzdata`, so timezones resolve correctly even on
the slim base image.

## Authentication

The whole app sits behind a single-user login. The plaintext password is never
stored — only a salted **PBKDF2-HMAC-SHA256** hash in the SQLite volume (in a
separate `auth` table that the settings API never exposes).

- **First run:** open the UI and you'll get a *Create your password* screen for
  `christopher.weeter@gmail.com` (override with the `ADMIN_EMAIL` env var).
- **Sessions:** login sets an HttpOnly cookie backed by a server-side session
  token (30-day TTL, revocable on logout).
- **Change password:** in the app's *Account* card.
- **Forgot password** (needs shell access to the box):

  ```sh
  docker compose exec wled-runner python reset_password.py
  ```

  This clears the stored hash so the first-run *Create your password* screen
  reappears.

> Sessions use HttpOnly, `SameSite=Lax`, **`Secure`** cookies (the app is served
> behind an HTTPS reverse proxy). Uvicorn runs with `--proxy-headers` so it
> honors `X-Forwarded-Proto`. If you ever expose it over plain HTTP on the LAN,
> set `COOKIE_SECURE=0` — otherwise the browser will refuse to send the cookie
> and you won't be able to stay logged in.

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
