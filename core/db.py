"""SQLite store for orders, consent, KYC results, handoff leads and call-back requests. Holds no raw documents or full ID numbers."""
import os, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("UDYAM_DB", Path(__file__).resolve().parent.parent / "udyam.db"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, profile TEXT, reason TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS consent(id INTEGER PRIMARY KEY, user TEXT, purpose TEXT, notice_version TEXT, language TEXT, granted_at TEXT, withdrawn_at TEXT);
CREATE TABLE IF NOT EXISTS kyc(id INTEGER PRIMARY KEY, user TEXT, verdict TEXT, reason TEXT, fields TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user TEXT, items TEXT, monthly INTEGER, setup INTEGER, contract INTEGER, install_days INTEGER, technician TEXT, install_date TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS callbacks(id INTEGER PRIMARY KEY, user TEXT, name TEXT, phone TEXT, email TEXT, best_time TEXT, note TEXT, profile TEXT, reason TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS order_events(id INTEGER PRIMARY KEY, order_id INTEGER, stage TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT, action TEXT, detail TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS order_delays(id INTEGER PRIMARY KEY, order_id INTEGER, reason TEXT, old_date TEXT, new_date TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS order_changes(id INTEGER PRIMARY KEY, order_id INTEGER, old_date TEXT, new_date TEXT, ts TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c; c.commit()
    finally:
        c.close()


def save_lead(profile_json: str, reason: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO leads(profile,reason,ts) VALUES(?,?,?)", (profile_json, reason, now()))


def list_leads() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT profile, reason, ts FROM leads ORDER BY id DESC").fetchall()
    return [{"profile": r[0], "reason": r[1], "ts": r[2]} for r in rows]


def audit(actor: str, action: str, detail: str = "") -> None:
    """Who did what to personal data, for proving it later. Holds a session reference and a code: never names, numbers or document details."""
    with conn() as c:
        c.execute("INSERT INTO audit(actor,action,detail,ts) VALUES(?,?,?,?)", (actor, action, detail, now()))


def audit_log(limit: int = 50) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT actor,action,detail,ts FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
