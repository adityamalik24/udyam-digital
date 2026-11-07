"""How we reach the owner about their order: a name and a mobile number, kept under their own consent
(installation and order updates). Never sent to the LLM, never in the audit log, masked on staff screens."""
from __future__ import annotations
import re
from . import consent, db
from .callback import PHONE

MAX_NAME = 60


def _ensure() -> None:
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS contacts(user TEXT PRIMARY KEY, name TEXT, phone TEXT, ts TEXT)")


def clean(name: str, phone: str) -> tuple[str | None, str | None, str | None]:
    """Returns (name, 10-digit mobile, problem code)."""
    name = re.sub(r"\s+", " ", (name or "")).strip()[:MAX_NAME]
    if len(name) < 2 or not re.search(r"[^\W\d_]", name): return None, None, "bad_name"
    m = PHONE.match(re.sub(r"[\s-]", "", phone or ""))
    if not m: return None, None, "bad_phone"
    return name, m.group(1), None


def save(user: str, name: str, phone: str, language: str) -> str | None:
    """Records the consent (once) and the details. Returns a problem code, or None."""
    name, phone, problem = clean(name, phone)
    if problem: return problem
    _ensure()
    if consent.CONTACT not in consent.active(user): consent.grant(user, consent.CONTACT, language)
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO contacts(user,name,phone,ts) VALUES(?,?,?,?)", (user, name, phone, db.now()))
    db.audit(user, "contact_saved")
    return None


def get(user: str) -> dict | None:
    """Only while the consent for it is active."""
    _ensure()
    if consent.CONTACT not in consent.active(user): return None
    with db.conn() as c:
        r = c.execute("SELECT name, phone, ts FROM contacts WHERE user=?", (user,)).fetchone()
    return dict(r) if r else None


def delete(user: str) -> None:
    _ensure()
    with db.conn() as c:
        c.execute("DELETE FROM contacts WHERE user=?", (user,))


def masked(user: str) -> str:
    """For staff screens with no login: first letter of the name and the last 4 digits."""
    _ensure()
    with db.conn() as c:
        r = c.execute("SELECT name, phone FROM contacts WHERE user=?", (user,)).fetchone()
    return f"{r['name'][0]}… · ••••••{r['phone'][-4:]}" if r else ""
