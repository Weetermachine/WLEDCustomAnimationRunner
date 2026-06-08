"""FastAPI app: auth, status, manual control, settings, schedule CRUD."""
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import animations
import auth
import database
from animator import animator
from scheduler import ScheduleManager

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "christopher.weeter@gmail.com")

schedule_manager = ScheduleManager(animator)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    s = database.get_settings()
    animator.update_settings(
        wled_ip=s["wled_ip"], speed=s["speed"],
        master_brightness=s["master_brightness"], animation=s.get("animation"),
    )
    schedule_manager.start()
    yield
    animator.stop()
    schedule_manager.scheduler.shutdown(wait=False)


app = FastAPI(title="WLED Custom Animation Runner", lifespan=lifespan)


# ---- auth dependency ------------------------------------------------------

def require_auth(wled_session: Optional[str] = Cookie(default=None)):
    if not database.session_valid(wled_session):
        raise HTTPException(401, "authentication required")


def _set_session_cookie(response: Response):
    token = auth.new_session_token()
    database.create_session(token, auth.session_expiry())
    response.set_cookie(
        key=auth.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=auth.COOKIE_SECURE,
        max_age=auth.SESSION_TTL,
        path="/",
    )


# ---- auth models ----------------------------------------------------------

class SetupIn(BaseModel):
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# ---- auth routes (unprotected) -------------------------------------------

@app.get("/api/auth/status")
def auth_status(wled_session: Optional[str] = Cookie(default=None)):
    record = database.get_auth()
    return {
        "configured": record is not None,
        "authenticated": database.session_valid(wled_session),
        "email": record["email"] if record else ADMIN_EMAIL,
    }


@app.post("/api/auth/setup")
def auth_setup(payload: SetupIn, response: Response):
    if database.get_auth() is not None:
        raise HTTPException(409, "password already set; use change-password or reset")
    salt, h = auth.hash_password(payload.password)
    database.set_auth(ADMIN_EMAIL, salt, h)
    _set_session_cookie(response)
    return {"ok": True, "email": ADMIN_EMAIL}


@app.post("/api/auth/login")
def auth_login(payload: LoginIn, response: Response):
    record = database.get_auth()
    if record is None:
        raise HTTPException(409, "no password set yet")
    email_ok = payload.email.strip().lower() == record["email"].lower()
    pw_ok = auth.verify_password(payload.password, record["salt"], record["hash"])
    if not (email_ok and pw_ok):
        raise HTTPException(401, "invalid email or password")
    _set_session_cookie(response)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(response: Response, wled_session: Optional[str] = Cookie(default=None)):
    if wled_session:
        database.delete_session(wled_session)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.post("/api/auth/change-password", dependencies=[Depends(require_auth)])
def change_password(payload: ChangePasswordIn):
    record = database.get_auth()
    if record is None or not auth.verify_password(
        payload.current_password, record["salt"], record["hash"]
    ):
        raise HTTPException(401, "current password is incorrect")
    salt, h = auth.hash_password(payload.new_password)
    database.set_auth(record["email"], salt, h)
    return {"ok": True}


# ---- protected app routes -------------------------------------------------

api = APIRouter(dependencies=[Depends(require_auth)])


class SettingsIn(BaseModel):
    wled_ip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = Field(default=None, ge=0.5, le=3.0)
    master_brightness: Optional[int] = Field(default=None, ge=0, le=255)
    timezone: Optional[str] = None
    animation: Optional[str] = None


class ScheduleIn(BaseModel):
    name: str
    start_type: str = "clock"            # 'clock' | 'sunset'
    start_time: Optional[str] = None     # 'HH:MM'
    sunset_offset: int = 0
    end_time: str                        # 'HH:MM'
    days: List[int] = []                 # weekday ints, Mon=0
    dates: List[str] = []                # 'YYYY-MM-DD'
    start_date: Optional[str] = None     # 'YYYY-MM-DD' range start (inclusive)
    end_date: Optional[str] = None       # 'YYYY-MM-DD' range end (inclusive)
    enabled: bool = True


@api.get("/api/status")
def status():
    settings = database.get_settings()
    return {
        "running": animator.is_running(),
        "active_schedule": schedule_manager.active_name,
        "next_event": schedule_manager.next_event(settings),
        "wled_ip": settings["wled_ip"],
    }


@api.post("/api/start")
def manual_start():
    animator.start()
    return {"running": animator.is_running()}


@api.post("/api/stop")
def manual_stop():
    animator.stop()
    return {"running": animator.is_running()}


@api.get("/api/settings")
def get_settings():
    return database.get_settings()


@api.get("/api/animations")
def get_animations():
    return animations.list_animations()


@api.post("/api/settings")
def set_settings(payload: SettingsIn):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "animation" in updates and animations.get(updates["animation"]) is None:
        raise HTTPException(400, "unknown animation")
    if updates:
        database.update_settings(updates)
    s = database.get_settings()
    animator.update_settings(
        wled_ip=s["wled_ip"], speed=s["speed"],
        master_brightness=s["master_brightness"], animation=s.get("animation"),
    )
    return s


@api.get("/api/schedules")
def list_schedules():
    return database.list_schedules()


@api.post("/api/schedules")
def create_schedule(payload: ScheduleIn):
    _validate(payload)
    return database.create_schedule(payload.model_dump())


@api.put("/api/schedules/{sched_id}")
def update_schedule(sched_id: int, payload: ScheduleIn):
    _validate(payload)
    updated = database.update_schedule(sched_id, payload.model_dump())
    if not updated:
        raise HTTPException(404, "schedule not found")
    return updated


@api.post("/api/schedules/{sched_id}/toggle")
def toggle_schedule(sched_id: int):
    sched = database.get_schedule(sched_id)
    if not sched:
        raise HTTPException(404, "schedule not found")
    return database.update_schedule(sched_id, {"enabled": not sched["enabled"]})


@api.delete("/api/schedules/{sched_id}")
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
    if not (payload.days or payload.dates or payload.start_date or payload.end_date):
        raise HTTPException(
            400, "select at least one weekday, calendar date, or a date range"
        )
    if (
        payload.start_date
        and payload.end_date
        and payload.end_date < payload.start_date
    ):
        raise HTTPException(400, "end date must be on or after start date")


app.include_router(api)


# ---- frontend -------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/", StaticFiles(directory="static"), name="static")
