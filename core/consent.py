"""Purpose-specific consent records (DPDP Act 2023). One row per purpose; withdrawal is a timestamp, not a delete."""
from . import db

NOTICE_VERSION = "v1.0-2026-07"
KYC, UPDATES = "kyc_verification", "order_updates"
REQUIRED = {KYC}


def grant(user: str, purpose: str, language: str) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO consent(user,purpose,notice_version,language,granted_at) VALUES(?,?,?,?,?)",
                  (user, purpose, NOTICE_VERSION, language, db.now()))


def active(user: str) -> set[str]:
    with db.conn() as c:
        return {r["purpose"] for r in c.execute("SELECT purpose FROM consent WHERE user=? AND withdrawn_at IS NULL", (user,))}


def withdraw(user: str, purpose: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE consent SET withdrawn_at=? WHERE user=? AND purpose=? AND withdrawn_at IS NULL", (db.now(), user, purpose))
        if purpose == KYC:  # stop processing and erase what that consent allowed us to keep
            c.execute("DELETE FROM kyc WHERE user=?", (user,))


def records(user: str) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT purpose,notice_version,language,granted_at,withdrawn_at FROM consent WHERE user=? ORDER BY id", (user,))]


def save_kyc(user: str, verdict: str, reason: str, fields_json: str) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO kyc(user,verdict,reason,fields,ts) VALUES(?,?,?,?,?)", (user, verdict, reason, fields_json, db.now()))


def latest_kyc(user: str) -> dict | None:
    with db.conn() as c:
        r = c.execute("SELECT verdict,reason,fields,ts FROM kyc WHERE user=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
    return dict(r) if r else None
