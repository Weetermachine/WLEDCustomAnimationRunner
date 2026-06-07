"""SQLite persistence for settings and schedules."""
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("DB_PATH", "/data/wled.db")

# Serialize all DB access; SQLite + threads from APScheduler/animator.
_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "wled_ip": "192.168.50.250",
    "latitude": 40.7608,
    "longitude": -111.8910,
    "speed": 1.0,            # animation speed multiplier (0.5 - 3.0)
    "master_brightness": 255,  # 0 - 255
}


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with _lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS schedules (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                start_type    TEXT NOT NULL DEFAULT 'clock',  -- 'clock' | 'sunset'
                start_time    TEXT,                            -- 'HH:MM' when clock
                sunset_offset INTEGER NOT NULL DEFAULT 0,      -- minutes, may be negative
                end_time      TEXT NOT NULL,                   -- 'HH:MM'
                days          TEXT NOT NULL DEFAULT '[]',      -- JSON list of weekday ints (Mon=0)
                dates         TEXT NOT NULL DEFAULT '[]',      -- JSON list of 'YYYY-MM-DD'
                enabled       INTEGER NOT NULL DEFAULT 1
            )"""
        )
        for k, v in DEFAULT_SETTINGS.items():
            c.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (k, json.dumps(v)),
            )
        conn.commit()
        conn.close()


# ---- settings -------------------------------------------------------------

def get_settings():
    with _lock:
        conn = get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
    s = dict(DEFAULT_SETTINGS)
    for r in rows:
        s[r["key"]] = json.loads(r["value"])
    return s


def update_settings(updates):
    with _lock:
        conn = get_conn()
        for k, v in updates.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, json.dumps(v)),
            )
        conn.commit()
        conn.close()


# ---- schedules ------------------------------------------------------------

def _row_to_schedule(r):
    return {
        "id": r["id"],
        "name": r["name"],
        "start_type": r["start_type"],
        "start_time": r["start_time"],
        "sunset_offset": r["sunset_offset"],
        "end_time": r["end_time"],
        "days": json.loads(r["days"]),
        "dates": json.loads(r["dates"]),
        "enabled": bool(r["enabled"]),
    }


def list_schedules():
    with _lock:
        conn = get_conn()
        rows = conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        conn.close()
    return [_row_to_schedule(r) for r in rows]


def get_schedule(sched_id):
    with _lock:
        conn = get_conn()
        r = conn.execute("SELECT * FROM schedules WHERE id = ?", (sched_id,)).fetchone()
        conn.close()
    return _row_to_schedule(r) if r else None


def create_schedule(data):
    with _lock:
        conn = get_conn()
        cur = conn.execute(
            """INSERT INTO schedules
               (name, start_type, start_time, sunset_offset, end_time, days, dates, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["name"],
                data["start_type"],
                data.get("start_time"),
                data.get("sunset_offset", 0),
                data["end_time"],
                json.dumps(data.get("days", [])),
                json.dumps(data.get("dates", [])),
                1 if data.get("enabled", True) else 0,
            ),
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
    return get_schedule(new_id)


def update_schedule(sched_id, data):
    existing = get_schedule(sched_id)
    if not existing:
        return None
    merged = {**existing, **data}
    with _lock:
        conn = get_conn()
        conn.execute(
            """UPDATE schedules SET
                 name = ?, start_type = ?, start_time = ?, sunset_offset = ?,
                 end_time = ?, days = ?, dates = ?, enabled = ?
               WHERE id = ?""",
            (
                merged["name"],
                merged["start_type"],
                merged.get("start_time"),
                merged.get("sunset_offset", 0),
                merged["end_time"],
                json.dumps(merged.get("days", [])),
                json.dumps(merged.get("dates", [])),
                1 if merged.get("enabled", True) else 0,
                sched_id,
            ),
        )
        conn.commit()
        conn.close()
    return get_schedule(sched_id)


def delete_schedule(sched_id):
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM schedules WHERE id = ?", (sched_id,))
        conn.commit()
        conn.close()
