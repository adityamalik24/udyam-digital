"""Order state machine for the tracker. Dates derive from catalogue install days and are shown as estimates."""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from . import db
from .pricing import Quote, TODAY

STAGES = ["Quote accepted", "KYC verified", "Payment done", "Installation scheduled", "Technician assigned", "Installed", "Activated"]
TECHS = ["Ravi Menon", "Sana Qureshi", "Arjun Nair"]  # demo data
MAX_RESCHEDULE_DAYS = 60  # how far ahead an installation can be moved
IST = timezone(timedelta(hours=5, minutes=30))


def create(user: str, items: dict[str, int], q: Quote) -> int:
    with db.conn() as c:
        cur = c.execute("INSERT INTO orders(user,items,monthly,setup,contract,install_days,created) VALUES(?,?,?,?,?,?,?)",
                        (user, json.dumps(items), q.monthly, q.setup, q.contract, q.install_days, db.now()))
        oid = cur.lastrowid
        c.execute("INSERT INTO order_events(order_id,stage,ts) VALUES(?,?,?)", (oid, STAGES[0], db.now()))
    return oid


def update_quote(oid: int, items: dict[str, int], q: Quote) -> bool:
    """Replace the plan on an unpaid order. KYC checks the business, not the plan, so it stays valid. False once paid."""
    if get(oid)["stage_index"] >= 2: return False
    with db.conn() as c:
        c.execute("UPDATE orders SET items=?,monthly=?,setup=?,contract=?,install_days=? WHERE id=?", (json.dumps(items), q.monthly, q.setup, q.contract, q.install_days, oid))
    return True


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
    """What the demo control may do. Nothing moves without a verified KYC, and payment only happens through paying."""
    return kyc_verdict == "verified" and o["stage_index"] != STAGES.index("KYC verified") and o["stage_index"] < len(STAGES) - 1


def can_pay(o: dict, kyc_verdict: str | None) -> bool:
    return kyc_verdict == "verified" and o["stage"] == "KYC verified"


def first_due(o: dict) -> int:
    return o["monthly"] + o["setup"]


def earliest_install(o: dict) -> date:
    """The catalogue's typical install time is the soonest we can honestly offer, counted from the demo's today."""
    return TODAY + timedelta(days=o["install_days"])


def reschedule(oid: int, new: date) -> None:
    o = get(oid)
    if o["stage_index"] < 3 or o["stage_index"] >= 5:
        raise ValueError("can only reschedule between scheduling and installation")
    if new < earliest_install(o):
        raise ValueError("date is earlier than we can install")
    if new > TODAY + timedelta(days=MAX_RESCHEDULE_DAYS):
        raise ValueError("date is too far ahead")
    if new.isoformat() == o["install_date"]: return
    with db.conn() as c:
        c.execute("INSERT INTO order_changes(order_id,old_date,new_date,ts) VALUES(?,?,?,?)", (oid, o["install_date"], new.isoformat(), db.now()))
        c.execute("UPDATE orders SET install_date=? WHERE id=?", (new.isoformat(), oid))


def changes(oid: int) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT old_date,new_date,ts FROM order_changes WHERE order_id=? ORDER BY id", (oid,))]


def for_user(user: str) -> list[int]:
    """This person's orders, newest first."""
    with db.conn() as c:
        return [r["id"] for r in c.execute("SELECT id FROM orders WHERE user=? ORDER BY id DESC", (user,))]


def next_step(o: dict) -> dict | None:
    """What comes next, who does it, and an estimate only where the catalogue gives one. None once activated.
    Activation has no date in the data, so we promise none."""
    i = o["stage_index"]
    if i >= len(STAGES) - 1: return None
    planned = date.fromisoformat(o["install_date"]) if o.get("install_date") else earliest_install(o)
    return {"stage": STAGES[i + 1], "who": "you" if i < 2 else "us", "estimate": planned if 2 <= i <= 4 else None}


def shown_time(ts: str, created: str) -> datetime:
    """A stored time as the demo should show it: in IST, with the order's first day placed on the demo's today.
    Eligibility dates and estimates all use that today, so a real clock next to them would read as months apart.
    The stored record keeps the real time."""
    t, start = datetime.fromisoformat(ts).astimezone(IST), datetime.fromisoformat(created).astimezone(IST)
    return t.replace(year=TODAY.year, month=TODAY.month, day=TODAY.day) + timedelta(days=(t.date() - start.date()).days)
