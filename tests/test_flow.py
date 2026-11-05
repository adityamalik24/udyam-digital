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
    good = f"Biz Fibre 100, Cloud Email & Office Suite and Endpoint Security: ₹{q.monthly:,} a month. Cheaper option at ₹{s0.rec.alt_quote.monthly:,}."
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


class _Fake:
    """Stands in for Gemini: replies with fixed text."""
    def __init__(self, text): self.text = text
    @property
    def models(self): return self
    def generate_content(self, **k): return NS(text=self.text)


def _chat(msgs, reply):
    llm._paused_until = 0.0
    s, out, fake = advisor.State(), "", _Fake(reply)
    for m in msgs: out = advisor.turn(s, m, fake)
    return s, out


def test_side_remark_gets_a_reply_then_the_question():
    s, out = _chat(["clinic in Delhi, need internet", "my cousin set this up for me"], "That's kind of your cousin.")
    assert out.startswith("That's kind of your cousin.") and "How many people" in out and s.stuck == 1


def test_first_message_side_remark_gets_a_reply():
    _, out = _chat(["my son usually handles all this"], "Happy to help you directly.")
    assert out.startswith("Happy to help") and "kind of business" in out


def test_side_remarks_still_end_with_a_person():
    s, out = _chat(["clinic in Delhi, need internet", "my cousin set this up", "he is very busy these days", "anyway he went to Dubai"], "I understand.")
    assert s.handoff == "repeated_confusion" and "specialist" in out


def test_remark_after_a_plan_keeps_the_plan():
    s, out = _chat(["Clinic in Delhi, 6 staff, one location, have GSTIN, want email"], "x")
    fake = _Fake("Biz Fibre 100 suits a clinic like yours, a specialist can confirm the details.")
    before = s.rec.items
    out = advisor.turn(s, "my brother thinks this looks okay", fake)
    assert out.startswith("Biz Fibre 100 suits") and s.rec.items == before


@pytest.mark.parametrize("bad", ["Sure, ₹500 works for you.", "Great, it will be ready tomorrow.", "We can give a discount.", "You should take Cloud CCTV.", "Try our fibre plan.",
                                 "P01 is good.", "I recommend upgrading.", "आपको मुफ़्त मिलेगा।", "Call 9876543210.", "word " * 50])
def test_unsafe_llm_small_talk_is_dropped(bad):
    _, out = _chat(["clinic in Delhi, need internet", "my cousin set this up for me"], bad)
    assert bad.strip() not in out and "How many people" in out


def test_small_talk_failure_falls_back_to_the_script():
    class Down:
        @property
        def models(self): return self
        def generate_content(self, **k): raise TimeoutError("down")
    llm._paused_until = 0.0
    s = advisor.State()
    advisor.turn(s, "clinic in Delhi, need internet")
    assert "How many people" in advisor.turn(s, "my cousin set this up for me", Down())
    llm._paused_until = 0.0; llm.last_error = None


def test_rewrite_must_keep_cheaper_option_and_exclusions():
    alt = price({"P04": 1})
    draft = "Biz Fibre 100. Cheaper option: Biz 5G AirFiber 100 at ₹999 per month. Not included: Static IP (reason)."
    assert G.dropped_facts("Biz Fibre 100 only.", draft, alt, ["Static IP"]) == ["cheaper option dropped", "exclusion Static IP dropped"]
    assert not G.dropped_facts("Fibre, or AirFiber at ₹999. Static IP isn't included.", draft, alt, ["Static IP"])
    assert G.check_reply("Biz Fibre 100 is a budget-friendly ₹1,099", price({"P01": 1}))


def test_plan_changes_update_the_order_until_it_is_paid():
    oid = orders.create("up", {"P01": 1}, price({"P01": 1}))
    assert orders.update_quote(oid, {"P04": 1}, price({"P04": 1})) and orders.get(oid)["monthly"] == price({"P04": 1}).monthly
    orders.advance(oid, "KYC verified")
    assert orders.update_quote(oid, {"P01": 1}, price({"P01": 1})) and orders.get(oid)["monthly"] == price({"P01": 1}).monthly
    orders.advance(oid, "Payment done")
    assert not orders.update_quote(oid, {"P04": 1}, price({"P04": 1})) and orders.get(oid)["monthly"] == price({"P01": 1}).monthly


def test_journey_only_counts_what_really_happened():
    from core import journey as j
    fresh = j.progress(None, False, None)
    assert set(fresh) == set(j.STEPS) and set(fresh.values()) == {j.TODO}
    assert j.progress(None, True, "verified") == {**fresh, "consent": j.DONE, "kyc": j.DONE}  # KYC first: no order, so no quote or payment tick
    for verdict in ("needs_review", "rejected"):
        assert j.progress(None, True, verdict)["kyc"] == j.ATTENTION
    oid = orders.create("jr", {"P01": 1}, price({"P01": 1}))
    done_at = {}
    for i, stage in enumerate(orders.STAGES):
        if i: orders.advance(oid, stage)
        done_at[stage] = j.progress(orders.get(oid), True, "verified")
    assert done_at["KYC verified"]["payment"] == j.TODO and done_at["Payment done"]["payment"] == j.DONE
    assert done_at["Installed"]["tracker"] == j.TODO and done_at["Activated"]["tracker"] == j.DONE
    # Withdrawn after payment: the payment happened, but consent and KYC no longer stand.
    assert j.progress(orders.get(oid), False, None) == {"quote": j.DONE, "consent": j.TODO, "kyc": j.TODO, "payment": j.DONE, "tracker": j.DONE}


def test_journey_points_at_payment_only_when_it_can_be_paid():
    from core import journey as j
    ready = {"quote": j.DONE, "consent": j.DONE, "kyc": j.DONE, "payment": j.TODO, "tracker": j.TODO}
    assert j.current("kyc", ready) == "payment" and j.current("consent", ready) == "consent"
    assert j.current("kyc", {**ready, "quote": j.TODO}) == "kyc"  # nothing to pay for yet
    assert j.current("kyc", {**ready, "kyc": j.ATTENTION}) == "kyc" and j.current("kyc", {**ready, "payment": j.DONE}) == "kyc"


def test_receipt_records_each_purpose_and_holds_no_document_data():
    from core import consent
    consent.grant("rc", consent.KYC, "hi"); consent.grant("rc", consent.UPDATES, "en")
    consent.save_kyc("rc", "verified", "ok", '{"gstin_masked": "****1234"}')
    consent.withdraw("rc", consent.UPDATES)
    en, hi = consent.receipt_text("rc", "en"), consent.receipt_text("rc", "hi")
    recs = consent.records("rc")
    assert "KYC verification" in en and "Order updates" in en and consent.NOTICE_VERSION in en and "rc" in en
    assert en.count("Status: Active") == 1 and en.count("Status: Withdrawn") == 1
    assert recs[0]["granted_at"][:16].replace("T", " ") in en and recs[1]["withdrawn_at"][:16].replace("T", " ") in en
    assert "हिन्दी" in en and "English" in en  # the language each notice was actually shown in
    assert "KYC सत्यापन" in hi and "सक्रिय" in hi and "UTC" in hi
    for leak in ("1234", "verified", "gstin"): assert leak not in en.lower()


def test_documents_to_keep_ready_match_what_kyc_checks():
    from core import consent
    from core.kyc.checks import BILL_MAX_AGE_DAYS
    from core.kyc.pipeline import FILES
    assert set(consent.DOCS_NEEDED) == set(FILES)
    for lang in ("en", "hi"):
        assert f"{BILL_MAX_AGE_DAYS} " in consent.DOCS_NEEDED["bill"][lang][1]
        words = " ".join(" ".join(d[lang]) for d in consent.DOCS_NEEDED.values()) + consent.DOCS_TIP[lang] + consent.NOTICE_SHORT[lang]
        for banned in ("aadhaar", "आधार", "bank", "बैंक"): assert banned not in words.lower()  # never ask for these
        for banned in (" pan ", " पैन "): assert banned not in f" {words.lower()} "


@pytest.mark.parametrize("claim", ["the best plan", "सबसे बढ़िया प्लान", "sabse badhiya plan", "a perfect fit"])
def test_rewrite_cannot_claim_a_plan_is_the_best(claim):
    assert G.check_reply(f"Biz Fibre 100 is {claim} at ₹1,099", price({"P01": 1}))
