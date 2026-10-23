#!/usr/bin/env python3
"""CareLoop: Medication reminder MCP server with FastMCP v1.30"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse, HTMLResponse

REMIND_MINUTES = 15
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
if not NTFY_TOPIC:
    print("Set NTFY_TOPIC to a private topic, see README")
    exit(1)

last_alerted = {}

mcp = FastMCP("CareLoop", host="0.0.0.0", port=8000)
DB_PATH = Path(__file__).parent / "doses.db"

def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            due_time TEXT NOT NULL,
            confirmed INTEGER DEFAULT 0,
            confirmed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ring_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            dose_id INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(dose_id) REFERENCES doses(id)
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_alert_level(dose: sqlite3.Row) -> str:
    if dose["confirmed"]:
        return "none"
    due = datetime.fromisoformat(dose["due_time"])
    now = datetime.now()
    minutes_late = (now - due).total_seconds() / 60
    if minutes_late >= 5:
        return "urgent"
    elif minutes_late >= 2:
        return "warning"
    return "none"

alert_running = False

def send_alert(dose_name: str, level: str, minutes_late: float):
    if not NTFY_TOPIC:
        return  # Alerts disabled
    try:
        title = f"{'URGENT' if level == 'urgent' else 'WARNING'}: {dose_name}"
        message = f"{dose_name} is {int(minutes_late)} minutes late"
        r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"),
                          headers={"Title": title, "Priority": "high"}, timeout=5)
        print("alert sent:", r.status_code)
    except Exception as e:
        print("alert failed:", e)

def alert_worker():
    global alert_running, last_alerted
    while alert_running:
        print("worker tick")
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM doses WHERE confirmed = 0")
            doses = cursor.fetchall()
            now = datetime.now()
            for dose in doses:
                due = datetime.fromisoformat(dose["due_time"])
                minutes_late = (now - due).total_seconds() / 60
                
                level = None
                if 2 <= minutes_late < 5:
                    level = "warning"
                elif minutes_late >= 5:
                    level = "urgent"
                
                if level:
                    key = (dose["id"], level)
                    should_alert = False
                    
                    if key not in last_alerted:
                        should_alert = True
                    else:
                        time_since_alert = (now - last_alerted[key]).total_seconds() / 60
                        if time_since_alert >= REMIND_MINUTES:
                            should_alert = True
                    
                    if should_alert:
                        send_alert(dose["name"], level, minutes_late)
                        last_alerted[key] = now
            
            conn.close()
        except Exception as e:
            print("worker error:", e)
        time.sleep(30)

init_db()
alert_running = True
threading.Thread(target=alert_worker, daemon=True).start()

def _create_dose_by_minutes(name: str, minutes_from_now: float) -> tuple:
    """Helper: Create a dose due in X minutes from now. Returns (dose_id, error or None)"""
    try:
        due_dt = datetime.now() + timedelta(minutes=minutes_from_now)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO doses (name, due_time) VALUES (?, ?)", (name, due_dt.isoformat()))
        dose_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return dose_id, None
    except Exception as e:
        return None, str(e)

@mcp.tool()
def add_dose(name: str, due_time: str) -> dict:
    """Add a dose. due_time in HH:MM format."""
    try:
        today = datetime.now().date()
        hour, minute = map(int, due_time.split(":"))
        due_dt = datetime.combine(today, __import__('datetime').time(hour, minute))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO doses (name, due_time) VALUES (?, ?)", (name, due_dt.isoformat()))
        dose_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"status": "success", "dose_id": dose_id, "message": f"Dose '{name}' scheduled for {due_time}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def confirm_dose(name: str) -> dict:
    """Mark a dose as confirmed."""
    global last_alerted
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE doses SET confirmed = 1, confirmed_at = CURRENT_TIMESTAMP WHERE name = ? AND confirmed = 0 ORDER BY due_time DESC LIMIT 1", (name,))
        if cursor.rowcount > 0:
            # Get the dose_id that was just confirmed
            cursor.execute("SELECT id FROM doses WHERE name = ? AND confirmed = 1 ORDER BY confirmed_at DESC LIMIT 1", (name,))
            dose_row = cursor.fetchone()
            if dose_row:
                dose_id = dose_row["id"]
                # Remove all alert entries for this dose from last_alerted
                keys_to_remove = [key for key in last_alerted if key[0] == dose_id]
                for key in keys_to_remove:
                    del last_alerted[key]
            conn.commit()
            conn.close()
            return {"status": "success", "message": f"Dose '{name}' confirmed"}
        else:
            conn.close()
            return {"status": "error", "message": f"No pending dose for '{name}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def whats_next() -> dict:
    """Get the next pending dose."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM doses WHERE confirmed = 0 ORDER BY due_time ASC LIMIT 1")
        dose = cursor.fetchone()
        conn.close()
        if dose:
            due = datetime.fromisoformat(dose["due_time"])
            now = datetime.now()
            minutes_until = (due - now).total_seconds() / 60
            return {
                "status": "found",
                "dose": {
                    "id": dose["id"],
                    "name": dose["name"],
                    "due_time": dose["due_time"],
                    "minutes_until": round(minutes_until, 1),
                    "alert_level": calculate_alert_level(dose)
                }
            }
        else:
            return {"status": "none", "message": "No pending doses"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def log_ring_event(kind: str) -> dict:
    """Log an event."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ring_events (kind) VALUES (?)", (kind,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Event '{kind}' logged"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.custom_route("/api/state", ["GET"])
async def get_state(request):
    """Get JSON state of all doses."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM doses ORDER BY due_time ASC")
        doses = cursor.fetchall()
        
        state = {
            "doses": [],
            "timestamp": datetime.now().isoformat(),
            "alerts": {"warning_count": 0, "urgent_count": 0}
        }
        
        for dose in doses:
            alert_level = calculate_alert_level(dose)
            # Only count alerts for unconfirmed doses
            if not dose["confirmed"]:
                if alert_level == "warning":
                    state["alerts"]["warning_count"] += 1
                elif alert_level == "urgent":
                    state["alerts"]["urgent_count"] += 1
            
            due = datetime.fromisoformat(dose["due_time"])
            now = datetime.now()
            minutes_late = (now - due).total_seconds() / 60
            
            cursor.execute("""
                SELECT COUNT(DISTINCT date(due_time)) as count FROM doses 
                WHERE name = ? AND confirmed = 0 
                AND due_time < datetime('now')
                AND due_time > datetime('now', '-3 days')
            """, (dose["name"],))
            missed_days = cursor.fetchone()["count"]
            
            state["doses"].append({
                "id": dose["id"],
                "name": dose["name"],
                "due_time": dose["due_time"],
                "confirmed": bool(dose["confirmed"]),
                "confirmed_at": dose["confirmed_at"],
                "minutes_late": round(max(0, minutes_late), 1),
                "alert_level": alert_level,
                "chronic_miss": missed_days >= 2
            })
        
        conn.close()
        return JSONResponse(state)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/api/doses", ["POST"])
async def create_dose_http(request):
    """HTTP endpoint to create a dose. JSON: {name, due_minutes_from_now}"""
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        due_minutes = float(body.get("due_minutes_from_now", 0))
        
        if not name:
            return JSONResponse({"status": "error", "message": "name is required"}, status_code=400)
        
        dose_id, error = _create_dose_by_minutes(name, due_minutes)
        if error:
            return JSONResponse({"status": "error", "message": error}, status_code=500)
        
        return JSONResponse({"status": "success", "dose_id": dose_id, "message": f"Dose '{name}' created"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/api/doses/{dose_id}/confirm", ["POST"])
async def confirm_dose_http(request):
    """HTTP endpoint to confirm a dose by ID. Clears last_alerted entries."""
    global last_alerted
    try:
        dose_id = int(request.path_params.get("dose_id", 0))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE doses SET confirmed = 1, confirmed_at = CURRENT_TIMESTAMP WHERE id = ?", (dose_id,))
        
        if cursor.rowcount > 0:
            # Remove all alert entries for this dose from last_alerted
            keys_to_remove = [key for key in last_alerted if key[0] == dose_id]
            for key in keys_to_remove:
                del last_alerted[key]
            conn.commit()
            conn.close()
            return JSONResponse({"status": "success", "message": f"Dose {dose_id} confirmed"})
        else:
            conn.close()
            return JSONResponse({"status": "error", "message": f"Dose {dose_id} not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/", ["GET"])
async def dashboard(request):
    """Dark theme dashboard with 3-second polling and add/confirm forms."""
    dashboard_html = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(dashboard_html, headers={"Cache-Control": "no-store"})

if __name__ == "__main__":
    print("🚀 CareLoop MCP Server (FastMCP v1.30)")
    print("🌐 Dashboard: http://localhost:8000/")
    print("📊 API: http://localhost:8000/api/state")
    print("📡 Transport: streamable-http")
    print(f"ntfy topic: {NTFY_TOPIC}\n")
    mcp.run(transport="streamable-http")
