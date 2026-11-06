"""Deletes what's no longer needed, on real time because real data ages in real time. Runs when the app starts.
Consent records stay: they're the proof of what was agreed. Figures are our proposal, to be confirmed with legal."""
from datetime import datetime, timedelta, timezone
from . import db

POLICY = {"kyc_without_order_days": 90, "unpaid_order_days": 180, "handoff_summary_days": 180, "callback_days": 90, "audit_days": 365}
_ran = False


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ago = lambda key: (now - timedelta(days=POLICY[key])).isoformat(timespec="seconds")
    out = {}
    with db.conn() as c:
        out["kyc"] = c.execute("DELETE FROM kyc WHERE ts<? AND user NOT IN (SELECT user FROM orders)", (ago("kyc_without_order_days"),)).rowcount
        stale = [r["id"] for r in c.execute("SELECT id FROM orders WHERE created<? AND id NOT IN (SELECT order_id FROM order_events WHERE stage='Payment done')", (ago("unpaid_order_days"),))]
        for oid in stale:
            for table in ("order_events", "order_changes", "order_delays"): c.execute(f"DELETE FROM {table} WHERE order_id=?", (oid,))
            c.execute("DELETE FROM orders WHERE id=?", (oid,))
        out["orders"] = len(stale)
        out["handoffs"] = c.execute("DELETE FROM leads WHERE ts<?", (ago("handoff_summary_days"),)).rowcount
        out["callbacks"] = c.execute("DELETE FROM callbacks WHERE ts<?", (ago("callback_days"),)).rowcount
        out["audit"] = c.execute("DELETE FROM audit WHERE ts<?", (ago("audit_days"),)).rowcount
    if any(out.values()): db.audit("system", "retention_run", ",".join(f"{k}={v}" for k, v in out.items() if v))
    return out


def run_once() -> None:
    global _ran
    if not _ran:
        _ran = True
        run()
