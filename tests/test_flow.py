import os, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import json, pytest
from types import SimpleNamespace as NS
from datetime import date
from core import orders, consent, db, llm, advisor, guardrails as G
from core.pricing import price, TODAY

def test_order_walk_and_no_skip():
    oid = orders.create("u", {"P01": 1}, price({"P01": 1}))
    with pytest.raises(ValueError): orders.advance(oid, "Installed")
    for s in orders.STAGES[1:]:
        orders.advance(oid, s)
    o = orders.get(oid)
    assert o["stage"] == "Activated" and o["technician"] and len(o["events"]) == 7
    with pytest.raises(ValueError): orders.advance(oid)

def test_consent_withdraw_erases_kyc():
    consent.grant("x", consent.KYC, "en"); consent.save_kyc("x", "verified", "r", "{}")
    assert consent.KYC in consent.active("x") and consent.latest_kyc("x")
    consent.withdraw("x", consent.KYC)
    assert not consent.active("x") and consent.latest_kyc("x") is None and consent.records("x")[0]["withdrawn_at"]

def test_guardrail_catches_bad_llm_output():
    q = price({"P01": 1})
    assert not G.check_reply("Biz Fibre 100 at ₹1,099 a month", q)
    assert G.check_reply("Biz Fibre 100 at ₹1,099, now only ₹799", q)
    assert G.check_reply("Biz Fibre 100 at ₹1,099 plus Cloud Backup 1 TB", q)
    assert G.check_reply("Biz Fibre 100 at ₹1,099 with a free upgrade", q)
    assert G.check_reply("P01 at ₹1,099 Biz Fibre 100", q)

class Fake:
    def __init__(self, texts): self.texts, self.calls = list(texts), []; self.models = self
    def generate_content(self, **k):
        self.calls.append(k)
        return NS(text=self.texts.pop(0))

MSG = "Clinic in Delhi, 6 staff, one location, have GSTIN, want email"

def test_bad_llm_regenerates_then_falls_back(monkeypatch):
    s = advisor.State(); f = Fake(["Biz Fibre 100 only ₹1!", "still ₹2 Biz Fibre 100"])
    r = advisor.turn(s, MSG, llm_client=f)
    assert len(f.calls) == 2 and "₹2,"[:1] in r and "only ₹1!" not in r and f"{s.rec.quote.monthly:,}" in r

def test_good_llm_used():
    s0 = advisor.State(); advisor.turn(s0, MSG); q = s0.rec.quote
    good = f"Biz Fibre 100, Cloud Email & Office Suite and Endpoint Security: ₹{q.monthly:,} a month."
    s = advisor.State(); assert advisor.turn(s, MSG, llm_client=Fake([good])) == good

def test_llm_never_receives_pii(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "client", lambda: object())
    monkeypatch.setattr(llm, "extract", lambda t, n, c=None: (seen.append(t), {})[1])
    s = advisor.State()
    advisor.turn(s, "I run a salon, gstin 27XUIXG0767D1ZP")
    assert seen and all("27XUIXG" not in x for x in seen)

def test_llm_cannot_inject_bad_fields(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: object())
    monkeypatch.setattr(llm, "extract", lambda t, n, c=None: {"needs": ["free_everything"], "employees": -5, "has_gstin": "yes"})
    s = advisor.State(); advisor.turn(s, "hello there")
    assert s.profile.needs == [] and s.profile.employees is None and s.profile.has_gstin is None

def test_busy_model_falls_through_then_pauses(monkeypatch):
    monkeypatch.setattr(llm, "_paused_until", 0.0)
    class Busy(Exception): code = 503
    class C:
        def __init__(self, fail): self.fail, self.n, self.models = fail, 0, self
        def generate_content(self, **k):
            self.n += 1
            if self.n <= self.fail: raise Busy()
            return NS(text="ok")
    c = C(1); assert llm._call("s", "u", c) == "ok" and c.n == 2
    c = C(9); assert llm._call("s", "u", c) is None and c.n == 2
    assert llm._call("s", "u", c) is None and c.n == 2  # paused, no further calls
    monkeypatch.setattr(llm, "_paused_until", 0.0)

def test_no_key_means_no_llm(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm.client() is None


def test_extra_scenario_sets_pass():
    import subprocess, sys, pathlib
    root = pathlib.Path(__file__).parent
    for f in ("advisor_dev.yaml", "advisor_unseen.yaml"):
        r = subprocess.run([sys.executable, str(root / "run_scenarios.py"), str(root / f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-800:]


def test_kyc_gate_on_order_stages():
    oid = orders.create("gate", {"P01": 1}, price({"P01": 1}))
    o = orders.get(oid)
    assert not orders.can_advance(o, None) and not orders.can_advance(o, "rejected") and not orders.can_advance(o, "needs_review")
    assert orders.can_advance(o, "verified")


def test_rewrite_may_not_add_a_date_or_number():
    q = price({"P01": 1})
    draft = "Biz Fibre 100: ₹1,099 per month"
    assert not G.check_reply("Biz Fibre 100 costs ₹1,099 per month", q, draft=draft)
    assert G.check_reply("Biz Fibre 100 costs ₹1,099 per month, live in 3 days", q, draft=draft)
    assert G.check_reply("Biz Fibre 100 at 1,099 per month or 799 per month", q)


def test_llm_failure_pauses_instead_of_stalling():
    class Boom:
        class models:
            @staticmethod
            def generate_content(**k): raise TimeoutError("hung")
    llm._paused_until = 0.0
    assert llm._call("s", "u", Boom()) is None and llm.last_error == "TimeoutError"
    assert llm._paused_until > 0
    llm._paused_until = 0.0; llm.last_error = None


def test_llm_cannot_add_a_declined_need_or_bad_type(monkeypatch):
    s = advisor.State(); s.declined = ["cctv"]
    monkeypatch.setattr(llm, "client", lambda: object())
    monkeypatch.setattr(llm, "extract", lambda t, n: {"needs": ["cctv", "storage"], "business_type": "<script>", "employees": True})
    advisor._merge_llm(s, "text", {})
    assert s.profile.needs == ["storage"] and s.profile.business_type is None and s.profile.employees is None


def test_callback_validation():
    from core.callback import clean
    assert clean("+91 98765-43210", "") == ("9876543210", None, None)
    assert clean("", "a@b.co") == (None, "a@b.co", None)
    assert clean("", "")[2] == "missing" and clean("12345", "")[2] == "bad_phone" and clean("", "nope")[2] == "bad_email"


def test_callback_consent_delete_purge_and_note_redaction():
    from datetime import datetime, timedelta, timezone
    from core import callback
    callback.save("cb", "Asha", "9876543210", None, "Morning", "my pan is ABCDE1234F", "{}", "frustration", "en")
    assert callback.has_request("cb") and consent.CALLBACK in consent.active("cb")
    row = next(r for r in callback.queue() if r["user"] == "cb")
    assert "ABCDE" not in row["note"]
    callback.save("cb", "Asha", "9876500000", None, "Morning", "", "{}", "frustration", "en")
    assert sum(r["user"] == "cb" for r in callback.queue()) == 1
    callback.delete("cb")
    assert not callback.has_request("cb") and consent.records("cb")[-1]["withdrawn_at"]
    callback.save("old", "", "9876543210", None, "Any time", "", "{}", "x", "en")
    callback.purge(datetime.now(timezone.utc) + timedelta(days=91))
    assert not callback.has_request("old")
