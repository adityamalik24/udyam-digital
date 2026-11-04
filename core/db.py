"""SQLite store for orders, consent, KYC results and handoff leads. Holds no raw documents or full identifiers."""
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
CREATE TABLE IF NOT EXISTS order_events(id INTEGER PRIMARY KEY, order_id INTEGER, stage TEXT, ts TEXT);
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
