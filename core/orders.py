"""Order state machine for the tracker. Dates derive from catalogue install days and are shown as estimates."""
from __future__ import annotations
import json
from datetime import date, timedelta
from . import db
from .pricing import Quote, TODAY

STAGES = ["Quote accepted", "KYC verified", "Payment done", "Installation scheduled", "Technician assigned", "Installed", "Activated"]
TECHS = ["Ravi Menon", "Sana Qureshi", "Arjun Nair"]  # demo data


def create(user: str, items: dict[str, int], q: Quote) -> int:
    with db.conn() as c:
        cur = c.execute("INSERT INTO orders(user,items,monthly,setup,contract,install_days,created) VALUES(?,?,?,?,?,?,?)",
                        (user, json.dumps(items), q.monthly, q.setup, q.contract, q.install_days, db.now()))
        oid = cur.lastrowid
        c.execute("INSERT INTO order_events(order_id,stage,ts) VALUES(?,?,?)", (oid, STAGES[0], db.now()))
    return oid


def get(oid: int) -> dict | None:
    with db.conn() as c:
        o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o: return None
        ev = [dict(r) for r in c.execute("SELECT stage,ts FROM order_events WHERE order_id=? ORDER BY id", (oid,))]
    return {**dict(o), "events": ev, "stage": ev[-1]["stage"], "stage_index": STAGES.index(ev[-1]["stage"])}


def latest(user: str) -> int | None:
    with db.conn() as c:
        r = c.execute("SELECT id FROM orders WHERE user=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
    return r["id"] if r else None


def advance(oid: int, to: str | None = None) -> str:
    """Move forward exactly one stage; `to` asserts the expected next stage. Skips and reversals raise."""
    o = get(oid)
    i = o["stage_index"]
    if i == len(STAGES) - 1:
        raise ValueError("order already activated")
    nxt = STAGES[i + 1]
    if to and to != nxt:
        raise ValueError(f"cannot move from {o['stage']} to {to}")
    with db.conn() as c:
        c.execute("INSERT INTO order_events(order_id,stage,ts) VALUES(?,?,?)", (oid, nxt, db.now()))
        if nxt == "Installation scheduled":
            c.execute("UPDATE orders SET install_date=? WHERE id=?", ((TODAY + timedelta(days=o["install_days"])).isoformat(), oid))
        if nxt == "Technician assigned":
            c.execute("UPDATE orders SET technician=? WHERE id=?", (TECHS[oid % len(TECHS)], oid))
    return nxt


def can_advance(o: dict, kyc_verdict: str | None) -> bool:
    """Nothing moves past "Quote accepted" without a verified KYC, including the demo control."""
    return kyc_verdict == "verified" and o["stage_index"] < len(STAGES) - 1


def reschedule(oid: int, new: date) -> None:
    o = get(oid)
    if o["stage_index"] < 3 or o["stage_index"] >= 5:
        raise ValueError("can only reschedule between scheduling and installation")
    if new < TODAY:
        raise ValueError("date is in the past")
    with db.conn() as c:
        c.execute("UPDATE orders SET install_date=? WHERE id=?", (new.isoformat(), oid))


def next_expected(o: dict) -> str | None:
    """Estimated date for the next step, or None when nothing is pending."""
    i = o["stage_index"]
    if i >= len(STAGES) - 1: return None
    if o.get("install_date"): return o["install_date"]
    return (TODAY + timedelta(days=o["install_days"])).isoformat()
