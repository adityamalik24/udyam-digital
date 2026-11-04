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
    def __init__(self, texts): self.texts, self.calls = list(texts), []; self.messages = self
    def create(self, **k):
        self.calls.append(k)
        return NS(stop_reason="end_turn", content=[NS(type="text", text=self.texts.pop(0))])

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

def test_no_key_means_no_llm(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm.client() is None
