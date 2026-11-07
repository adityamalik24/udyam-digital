"""Funnel events for the live dashboard. Each row is a random funnel id (not the user id), a step, and an optional
code such as a verdict or a hand-off reason. No names, numbers or text from the owner."""
from __future__ import annotations
import math, random
from datetime import datetime
from statistics import median
from . import db

STEPS = ["chat_started", "plan_shown", "quote_viewed", "quote_accepted", "consent_given", "kyc_done", "paid", "activated"]
STEP_LABEL = {"chat_started": "Chat started", "plan_shown": "Plan shown", "quote_viewed": "Quote viewed", "quote_accepted": "Quote accepted", "consent_given": "KYC consent given",
              "kyc_done": "KYC result", "paid": "Paid", "activated": "Activated"}
VARIANTS = ("A", "B")  # A: monthly price alone. B: also "about ₹N a day"


def _ensure() -> None:
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, fid TEXT, kind TEXT, variant TEXT, code TEXT, ts TEXT)")


def variant() -> str:
    return random.choice(VARIANTS)


def log(fid: str, kind: str, variant: str | None = None, code: str | None = None, once: bool = True) -> None:
    """Records a step once per funnel id (and code), so a page that redraws doesn't count twice."""
    _ensure()
    with db.conn() as c:
        if once and c.execute("SELECT 1 FROM events WHERE fid=? AND kind=? AND IFNULL(code,'')=IFNULL(?, '')", (fid, kind, code)).fetchone(): return
        c.execute("INSERT INTO events(fid,kind,variant,code,ts) VALUES(?,?,?,?,?)", (fid, kind, variant, code, db.now()))


def _rows() -> list[dict]:
    _ensure()
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT fid,kind,variant,code,ts FROM events ORDER BY id")]


def funnel() -> list[dict]:
    """Funnels that reached each step, the share of all started, and the median minutes from the step before."""
    first: dict[tuple[str, str], datetime] = {}
    for r in _rows():
        first.setdefault((r["fid"], r["kind"]), datetime.fromisoformat(r["ts"]))
    started = {f for (f, k) in first if k == "chat_started"}
    out, prev = [], None
    for step in STEPS:
        fids = {f for (f, k) in first if k == step}
        gaps = [(first[(f, step)] - first[(f, prev)]).total_seconds() / 60 for f in fids if prev and (f, prev) in first] if prev else []
        out.append({"step": STEP_LABEL[step], "count": len(fids), "share": len(fids) / len(started) if started else None, "minutes": round(median(gaps), 1) if gaps else None})
        prev = step
    return out


def counts(kind: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in _rows():
        if r["kind"] == kind: out[r["code"] or ""] = out.get(r["code"] or "", 0) + 1
    return out


def ab_test() -> dict:
    """Quote views and acceptances per variant, with a two-sided two-proportion z-test."""
    seen: dict[str, set] = {v: set() for v in VARIANTS}
    took: dict[str, set] = {v: set() for v in VARIANTS}
    for r in _rows():
        if r["variant"] in seen and r["kind"] == "quote_viewed": seen[r["variant"]].add(r["fid"])
        if r["variant"] in took and r["kind"] == "quote_accepted": took[r["variant"]].add(r["fid"])
    arms = {v: {"viewed": len(seen[v]), "accepted": len(took[v] & seen[v]), "rate": len(took[v] & seen[v]) / len(seen[v]) if seen[v] else None} for v in VARIANTS}
    a, b = arms["A"], arms["B"]
    p = None
    if a["viewed"] and b["viewed"]:
        pooled = (a["accepted"] + b["accepted"]) / (a["viewed"] + b["viewed"])
        se = math.sqrt(pooled * (1 - pooled) * (1 / a["viewed"] + 1 / b["viewed"]))
        p = 1.0 if se == 0 else math.erfc(abs(a["rate"] - b["rate"]) / se / math.sqrt(2))
    return {"arms": arms, "p": p, "enough": min(a["viewed"], b["viewed"]) >= 100}
