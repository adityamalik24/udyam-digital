"""The owner's rights under the DPDP Act, 2023: see everything we hold, ask for a correction, and erase it."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from . import consent, db, orders
from . import guardrails as G

REPLY_DAYS = 7  # our own target for a correction request, not a legal deadline


def _ensure() -> None:
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS rights_requests(id INTEGER PRIMARY KEY, user TEXT, kind TEXT, detail TEXT, ts TEXT, due TEXT, status TEXT)")


def export(user: str) -> dict:
    """Everything stored for this person, in one file. Masked values stay masked: we don't hold the full ones."""
    _ensure()
    with db.conn() as c:
        kyc = [dict(r) for r in c.execute("SELECT verdict,reason,fields,ts FROM kyc WHERE user=? ORDER BY id", (user,))]
        cb = [dict(r) for r in c.execute("SELECT name,phone,email,best_time,note,reason,ts FROM callbacks WHERE user=?", (user,))]
        req = [dict(r) for r in c.execute("SELECT kind,detail,ts,due,status FROM rights_requests WHERE user=?", (user,))]
    for k in kyc: k["fields"] = json.loads(k["fields"] or "{}")
    order_list = []
    for oid in orders.for_user(user):
        o = orders.get(oid)
        order_list.append({"order": oid, "items": json.loads(o["items"]), "monthly_inr": o["monthly"], "setup_inr": o["setup"], "contract_months": o["contract"], "stage": o["stage"],
                           "history": [{"stage": e["stage"], "at": e["ts"]} for e in o["events"]]})
    from . import contacts
    return {"generated_at": db.now(), "reference": user, "contact_details": contacts.get(user), "consents": consent.records(user), "orders": order_list, "kyc_results": kyc, "call_back_requests": cb, "rights_requests": req,
            "not_held": ["document images", "voice recordings", "full ID or GSTIN numbers", "the chat transcript (it lives only in your browser session)"]}


def request_correction(user: str, detail: str) -> str | None:
    _ensure()
    detail = G.redact(detail.strip()[:500])[0]
    if not detail: return "empty"
    now = datetime.now(timezone.utc)
    with db.conn() as c:
        c.execute("INSERT INTO rights_requests(user,kind,detail,ts,due,status) VALUES(?,?,?,?,?,?)", (user, "correction", detail, now.isoformat(timespec="seconds"), (now + timedelta(days=REPLY_DAYS)).date().isoformat(), "open"))
    db.audit(user, "rights_correction_requested")
    return None


def requests() -> list[dict]:
    _ensure()
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT id,user,kind,detail,ts,due,status FROM rights_requests ORDER BY id DESC")]


def erase(user: str) -> dict:
    """Deletes what we hold, except a paid order, which billing and the contract still need. Consent records stay,
    marked withdrawn, as proof of what was agreed; the audit log keeps only codes."""
    _ensure()
    kept = [oid for oid in orders.for_user(user) if orders.get(oid)["stage_index"] >= 2]
    for p in consent.active(user): consent.withdraw(user, p)
    with db.conn() as c:
        gone_orders = [r[0] for r in c.execute("SELECT id FROM orders WHERE user=?", (user,)) if r[0] not in kept]
        for oid in gone_orders:
            for table in ("order_events", "order_changes", "order_delays"): c.execute(f"DELETE FROM {table} WHERE order_id=?", (oid,))
            c.execute("DELETE FROM orders WHERE id=?", (oid,))
        c.execute("CREATE TABLE IF NOT EXISTS order_meta(order_id INTEGER PRIMARY KEY, segment TEXT, has_gstin INTEGER)")
        for oid in gone_orders: c.execute("DELETE FROM order_meta WHERE order_id=?", (oid,))
        c.execute("DELETE FROM kyc WHERE user=?", (user,))
        c.execute("DELETE FROM callbacks WHERE user=?", (user,))
        c.execute("CREATE TABLE IF NOT EXISTS contacts(user TEXT PRIMARY KEY, name TEXT, phone TEXT, ts TEXT)")
        c.execute("DELETE FROM contacts WHERE user=?", (user,))
        c.execute("DELETE FROM rights_requests WHERE user=?", (user,))
        c.execute("CREATE TABLE IF NOT EXISTS kyc_reviews(id INTEGER PRIMARY KEY, kyc_id INTEGER, user TEXT, was TEXT, decision TEXT, note TEXT, maker TEXT, checker TEXT, made_at TEXT, checked_at TEXT, outcome TEXT)")
        c.execute("DELETE FROM kyc_reviews WHERE user=? AND outcome IS NULL", (user,))
    db.audit(user, "erasure", f"orders_deleted={len(gone_orders)} orders_kept={len(kept)}")
    return {"orders_deleted": len(gone_orders), "orders_kept": len(kept)}
