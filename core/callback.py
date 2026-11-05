"""Call-back requests for people the advisor couldn't help. Contact details come only from the form, never go to the LLM,
and are kept for a limited time."""
from __future__ import annotations
import json, re
from datetime import datetime, timedelta, timezone
from . import consent, db, guardrails as G

RETENTION_DAYS = 90
PHONE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def clean(phone: str, email: str) -> tuple[str | None, str | None, str | None]:
    """Returns (phone, email, error code). At least one valid contact is needed."""
    raw = re.sub(r"[\s-]", "", phone or "")
    mail = (email or "").strip()
    m = PHONE.match(raw)
    if raw and not m: return None, None, "bad_phone"
    if mail and not EMAIL.match(mail): return None, None, "bad_email"
    if not raw and not mail: return None, None, "missing"
    return (m.group(1) if m else None), (mail or None), None


def save(user: str, name: str, phone: str | None, email: str | None, best_time: str, note: str, profile_json: str, reason: str, language: str) -> None:
    """One active request per user: a new one replaces the old. The note is redacted like chat text."""
    with db.conn() as c:
        c.execute("DELETE FROM callbacks WHERE user=?", (user,))
        c.execute("INSERT INTO callbacks(user,name,phone,email,best_time,note,profile,reason,ts) VALUES(?,?,?,?,?,?,?,?,?)",
                  (user, name.strip()[:60], phone, email, best_time, G.redact(note or "")[0][:200], profile_json, reason, db.now()))
    if consent.CALLBACK not in consent.active(user):
        consent.grant(user, consent.CALLBACK, language)


def purge(now: datetime | None = None) -> None:
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    with db.conn() as c:
        c.execute("DELETE FROM callbacks WHERE ts < ?", (cutoff,))


def has_request(user: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM callbacks WHERE user=?", (user,)).fetchone() is not None


def delete(user: str) -> None:
    """Withdrawing consent erases the request; the consent record stays as proof."""
    consent.withdraw(user, consent.CALLBACK)


def queue() -> list[dict]:
    purge()
    with db.conn() as c:
        rows = c.execute("SELECT * FROM callbacks ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r); d["profile"] = json.loads(d["profile"] or "{}")
        out.append(d)
    return out
