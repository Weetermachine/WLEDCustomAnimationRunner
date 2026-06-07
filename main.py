"""FastAPI app: status, manual control, settings, schedule CRUD."""
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database
from animator import animator
from scheduler import ScheduleManager

schedule_manager = ScheduleManager(animator)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    s = database.get_settings()
    animator.update_settings(
        wled_ip=s["wled_ip"], speed=s["speed"], master_brightness=s["master_brightness"]
    )
    schedule_manager.start()
    yield
    animator.stop()
    schedule_manager.scheduler.shutdown(wait=False)


app = FastAPI(title="WLED Custom Animation Runner", lifespan=lifespan)


# ---- models ---------------------------------------------------------------

class SettingsIn(BaseModel):
    wled_ip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = Field(default=None, ge=0.5, le=3.0)
    master_brightness: Optional[int] = Field(default=None, ge=0, le=255)


class ScheduleIn(BaseModel):
    name: str
    start_type: str = "clock"            # 'clock' | 'sunset'
    start_time: Optional[str] = None     # 'HH:MM'
    sunset_offset: int = 0
    end_time: str                        # 'HH:MM'
    days: List[int] = []                 # weekday ints, Mon=0
    dates: List[str] = []                # 'YYYY-MM-DD'
    enabled: bool = True


# ---- status / control -----------------------------------------------------

@app.get("/api/status")
def status():
    settings = database.get_settings()
    return {
        "running": animator.is_running(),
        "active_schedule": schedule_manager.active_name,
        "next_event": schedule_manager.next_event(settings),
        "wled_ip": settings["wled_ip"],
    }


@app.post("/api/start")
def manual_start():
    animator.start()
    return {"running": animator.is_running()}


@app.post("/api/stop")
def manual_stop():
    animator.stop()
    return {"running": animator.is_running()}


# ---- settings -------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return database.get_settings()


@app.post("/api/settings")
def set_settings(payload: SettingsIn):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        database.update_settings(updates)
    s = database.get_settings()
    animator.update_settings(
        wled_ip=s["wled_ip"], speed=s["speed"], master_brightness=s["master_brightness"]
    )
    return s


# ---- schedules ------------------------------------------------------------

@app.get("/api/schedules")
def list_schedules():
    return database.list_schedules()


@app.post("/api/schedules")
def create_schedule(payload: ScheduleIn):
    _validate(payload)
    return database.create_schedule(payload.model_dump())


@app.put("/api/schedules/{sched_id}")
def update_schedule(sched_id: int, payload: ScheduleIn):
    _validate(payload)
    updated = database.update_schedule(sched_id, payload.model_dump())
    if not updated:
        raise HTTPException(404, "schedule not found")
    return updated


@app.post("/api/schedules/{sched_id}/toggle")
def toggle_schedule(sched_id: int):
    sched = database.get_schedule(sched_id)
    if not sched:
        raise HTTPException(404, "schedule not found")
    return database.update_schedule(sched_id, {"enabled": not sched["enabled"]})


@app.delete("/api/schedules/{sched_id}")
def delete_schedule(sched_id: int):
    if not database.get_schedule(sched_id):
        raise HTTPException(404, "schedule not found")
    database.delete_schedule(sched_id)
    return {"deleted": sched_id}


def _validate(payload: ScheduleIn):
    if payload.start_type not in ("clock", "sunset"):
        raise HTTPException(400, "start_type must be 'clock' or 'sunset'")
    if payload.start_type == "clock" and not payload.start_time:
        raise HTTPException(400, "start_time required for clock schedules")
    if not payload.days and not payload.dates:
        raise HTTPException(400, "select at least one weekday or calendar date")


# ---- frontend -------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/", StaticFiles(directory="static"), name="static")
