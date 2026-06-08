"""APScheduler-driven schedule evaluation + sunset calculation.

All time math runs in the configured IANA timezone (default America/Denver, i.e.
Mountain), independent of the host clock. Runs every minute. A schedule is
"active now" when the current local time is within its [start, end) window on a
matching day. Rising/falling edges start and stop the animation, so a manual
override is never fought minute-to-minute: a manual stop during an active window
stays stopped until the next window.
"""
import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from astral import LocationInfo
from astral.sun import sun

import database

DEFAULT_TZ = "America/Denver"


def _tz(settings):
    try:
        return ZoneInfo(settings.get("timezone") or DEFAULT_TZ)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def sunset_for(date, settings, tz):
    """Return sunset on `date` as a timezone-aware datetime in `tz`."""
    loc = LocationInfo(latitude=settings["latitude"], longitude=settings["longitude"])
    s = sun(loc.observer, date=date, tzinfo=tz)
    return s["sunset"]


def _day_matches(sched, ref_date):
    """Does the schedule apply on this calendar date?"""
    date_str = ref_date.strftime("%Y-%m-%d")
    # Explicit one-off dates always count, regardless of range/weekdays.
    if date_str in sched["dates"]:
        return True
    # Date-range bounds (inclusive). String compare works for YYYY-MM-DD.
    sd, ed = sched.get("start_date"), sched.get("end_date")
    if sd and date_str < sd:
        return False
    if ed and date_str > ed:
        return False
    if sched["days"]:
        return ref_date.weekday() in sched["days"]  # Mon=0
    # No weekdays chosen: match every day, but only if a range bounds it.
    return bool(sd or ed)


def _window_for(sched, ref_date, settings, tz):
    """Return (start_dt, end_dt) aware datetimes for ref_date, or None if the
    day doesn't match. end may roll past midnight (overnight windows)."""
    if not _day_matches(sched, ref_date):
        return None

    if sched["start_type"] == "sunset":
        start_dt = sunset_for(ref_date, settings, tz) + datetime.timedelta(
            minutes=sched.get("sunset_offset", 0) or 0
        )
        start_dt = start_dt.replace(second=0, microsecond=0)
    else:
        h, m = map(int, sched["start_time"].split(":"))
        start_dt = datetime.datetime.combine(ref_date, datetime.time(h, m), tzinfo=tz)

    eh, em = map(int, sched["end_time"].split(":"))
    end_dt = datetime.datetime.combine(ref_date, datetime.time(eh, em), tzinfo=tz)
    if end_dt <= start_dt:
        end_dt += datetime.timedelta(days=1)  # overnight window
    return start_dt, end_dt


class ScheduleManager:
    def __init__(self, animator):
        self.animator = animator
        # Let APScheduler detect the local zone for its 1-minute interval; the
        # evaluation itself computes time in the configured timezone.
        self.scheduler = BackgroundScheduler()
        self.prev_active = False
        self.active_name = None

    def start(self):
        self.scheduler.add_job(
            self.evaluate,
            "interval",
            minutes=1,
            id="evaluate",
            next_run_time=datetime.datetime.now(),
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()

    # -- core --------------------------------------------------------------
    def active_schedule(self, now, settings, tz):
        for sched in database.list_schedules():
            if not sched["enabled"]:
                continue
            # today's window and yesterday's (for overnight spillover)
            for ref in (now.date(), now.date() - datetime.timedelta(days=1)):
                win = _window_for(sched, ref, settings, tz)
                if win and win[0] <= now < win[1]:
                    return sched
        return None

    def evaluate(self):
        settings = database.get_settings()
        tz = _tz(settings)
        self.animator.update_settings(
            wled_ip=settings["wled_ip"],
            speed=settings["speed"],
            master_brightness=settings["master_brightness"],
            animation=settings.get("animation"),
        )

        now = datetime.datetime.now(tz).replace(microsecond=0)
        active = self.active_schedule(now, settings, tz)
        is_active = active is not None

        if is_active and not self.prev_active:
            self.animator.start()
        elif not is_active and self.prev_active:
            self.animator.stop()

        self.prev_active = is_active
        self.active_name = active["name"] if active else None

    # -- status helper -----------------------------------------------------
    def next_event(self, settings, horizon_days=400):
        """Return {'type','name','at'} for the next start/end boundary, or None."""
        tz = _tz(settings)
        now = datetime.datetime.now(tz).replace(microsecond=0)
        best = None
        for offset in range(horizon_days + 1):
            ref = now.date() + datetime.timedelta(days=offset)
            for sched in database.list_schedules():
                if not sched["enabled"]:
                    continue
                win = _window_for(sched, ref, settings, tz)
                if not win:
                    continue
                start_dt, end_dt = win
                for kind, when in (("start", start_dt), ("end", end_dt)):
                    if when > now and (best is None or when < best[1]):
                        best = (kind, when, sched["name"])
        if best is None:
            return None
        return {
            "type": best[0],
            "name": best[2],
            "at": best[1].strftime("%Y-%m-%d %H:%M %Z"),
        }
