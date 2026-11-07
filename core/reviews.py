"""A person's decision on a KYC result the automatic check couldn't settle. Maker-checker: one reviewer proposes, a
different one confirms, and only then does the result change. Notes are redacted like chat text."""
from __future__ import annotations
import json
from . import consent, db, orders
from . import guardrails as G

DECISIONS = {"verified": "Approve (verified)", "rejected": "Reject"}


def _ensure() -> None:
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS kyc_reviews(id INTEGER PRIMARY KEY, kyc_id INTEGER, user TEXT, was TEXT, decision TEXT, note TEXT, maker TEXT, checker TEXT, made_at TEXT, checked_at TEXT, outcome TEXT)")


def _latest(user: str) -> dict | None:
    with db.conn() as c:
        r = c.execute("SELECT id,user,verdict,reason,fields,ts FROM kyc WHERE user=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
    return dict(r) if r else None


def propose(kyc_id: int, decision: str, note: str, maker: str) -> str | None:
    """Returns a problem code, or None when the proposal is recorded."""
    _ensure()
    maker, note = maker.strip()[:40], G.redact(note.strip()[:300])[0]
    if decision not in DECISIONS: return "bad_decision"
    if not maker: return "no_name"
    if not note: return "no_note"
    with db.conn() as c:
        row = c.execute("SELECT id,user,verdict FROM kyc WHERE id=?", (kyc_id,)).fetchone()
        if not row or row["verdict"] == "verified": return "not_waiting"
        latest = c.execute("SELECT MAX(id) FROM kyc WHERE user=?", (row["user"],)).fetchone()[0]
        if latest != kyc_id: return "not_waiting"  # the owner has verified again since
        if c.execute("SELECT 1 FROM kyc_reviews WHERE kyc_id=? AND outcome IS NULL", (kyc_id,)).fetchone(): return "already_proposed"
        c.execute("INSERT INTO kyc_reviews(kyc_id,user,was,decision,note,maker,made_at) VALUES(?,?,?,?,?,?,?)", (kyc_id, row["user"], row["verdict"], decision, note, maker, db.now()))
    db.audit(row["user"], "kyc_review_proposed", decision)
    return None


def confirm(review_id: int, checker: str, accept: bool) -> str | None:
    """The second person. Confirming writes a new KYC result; sending back closes the proposal with no change."""
    _ensure()
    checker = checker.strip()[:40]
    if not checker: return "no_name"
    with db.conn() as c:
        rv = c.execute("SELECT * FROM kyc_reviews WHERE id=? AND outcome IS NULL", (review_id,)).fetchone()
        if not rv: return "not_open"
        if checker.casefold() == rv["maker"].casefold(): return "same_person"
    if not accept:
        with db.conn() as c:
            c.execute("UPDATE kyc_reviews SET checker=?, checked_at=?, outcome='sent_back' WHERE id=?", (checker, db.now(), review_id))
        db.audit(rv["user"], "kyc_review_sent_back", rv["decision"])
        return None
    latest = _latest(rv["user"])
    if consent.KYC not in consent.active(rv["user"]) or not latest or latest["id"] != rv["kyc_id"]:
        with db.conn() as c:
            c.execute("UPDATE kyc_reviews SET checker=?, checked_at=?, outcome='stale' WHERE id=?", (checker, db.now(), review_id))
        return "stale"  # consent withdrawn, or a newer result exists: nothing may change
    fields = json.loads(latest["fields"] or "{}")
    fields.update(reviewed=True, review_note=rv["note"], was=rv["was"])
    reason = ("Checked by a person: " if rv["decision"] == "verified" else "Rejected after a person's check: ") + rv["note"]
    consent.save_kyc(rv["user"], rv["decision"], reason, json.dumps(fields))
    with db.conn() as c:
        c.execute("UPDATE kyc_reviews SET checker=?, checked_at=?, outcome='confirmed' WHERE id=?", (checker, db.now(), review_id))
    if rv["decision"] == "verified":
        for oid in orders.for_user(rv["user"]):
            if orders.get(oid)["stage"] == "Quote accepted": orders.advance(oid, "KYC verified")
    db.audit(rv["user"], "kyc_review_confirmed", f"{rv['was']}->{rv['decision']}")
    return None


def pending() -> list[dict]:
    _ensure()
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT id,kyc_id,user,was,decision,note,maker,made_at FROM kyc_reviews WHERE outcome IS NULL ORDER BY id")]


def overturned_rejections() -> int:
    """Automatic rejections a person reversed: the closest live measure of false rejections."""
    _ensure()
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM kyc_reviews WHERE outcome='confirmed' AND was='rejected' AND decision='verified'").fetchone()[0]


PROBLEM = {"bad_decision": "Choose a decision.", "no_name": "Add your reviewer name.", "no_note": "Add a note saying what you checked.", "not_waiting": "This result isn't waiting any more.",
           "already_proposed": "A decision is already waiting for a second person.", "not_open": "This proposal is already closed.", "same_person": "A different person must confirm.",
           "stale": "Nothing changed: the owner withdrew consent or verified again since."}
