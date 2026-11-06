import pytest
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


def _at(stage, user="tr"):
    oid = orders.create(user, {"P01": 1}, price({"P01": 1}))
    for st in orders.STAGES[1:orders.STAGES.index(stage) + 1]: orders.advance(oid, st)
    return oid


def test_next_step_says_who_acts_and_gives_a_date_only_where_the_data_has_one():
    want = {"Quote accepted": ("KYC verified", "you", False), "KYC verified": ("Payment done", "you", False), "Payment done": ("Installation scheduled", "us", True),
            "Installation scheduled": ("Technician assigned", "us", True), "Technician assigned": ("Installed", "us", True), "Installed": ("Activated", "us", False)}
    for stage, (nxt, who, dated) in want.items():
        s = orders.next_step(orders.get(_at(stage)))
        assert (s["stage"], s["who"], bool(s["estimate"])) == (nxt, who, dated), stage
    assert orders.next_step(orders.get(_at("Activated"))) is None


def test_estimate_follows_the_catalogue_and_a_reschedule():
    from datetime import timedelta
    from core.pricing import TODAY
    o = orders.get(_at("Payment done")); assert orders.next_step(o)["estimate"] == TODAY + timedelta(days=o["install_days"])
    oid = _at("Technician assigned"); new = TODAY + timedelta(days=20)
    orders.reschedule(oid, new); assert orders.next_step(orders.get(oid))["estimate"] == new


def test_reschedule_limits_and_history():
    from datetime import timedelta
    from core.pricing import TODAY
    oid = _at("Installation scheduled"); o = orders.get(oid); first = o["install_date"]
    for bad in (TODAY, orders.earliest_install(o) - timedelta(days=1), TODAY + timedelta(days=orders.MAX_RESCHEDULE_DAYS + 1)):
        with pytest.raises(ValueError): orders.reschedule(oid, bad)
    assert orders.get(oid)["install_date"] == first and not orders.changes(oid)
    orders.reschedule(oid, orders.date.fromisoformat(first)); assert not orders.changes(oid)  # same date: nothing changed
    new = TODAY + timedelta(days=orders.MAX_RESCHEDULE_DAYS); orders.reschedule(oid, new)
    assert orders.changes(oid)[0]["old_date"] == first and orders.changes(oid)[0]["new_date"] == new.isoformat()
    for stage in ("Payment done", "Installed", "Activated"):
        with pytest.raises(ValueError): orders.reschedule(_at(stage), new)


def test_demo_control_can_never_take_the_place_of_paying_or_kyc():
    o = lambda stage: orders.get(_at(stage))
    assert not orders.can_advance(o("KYC verified"), "verified") and orders.can_pay(o("KYC verified"), "verified")
    assert not orders.can_pay(o("KYC verified"), "needs_review") and not orders.can_pay(o("Payment done"), "verified") and not orders.can_pay(o("Quote accepted"), "verified")
    for v in (None, "needs_review", "rejected"): assert not orders.can_advance(o("Payment done"), v)
    assert orders.can_advance(o("Payment done"), "verified") and not orders.can_advance(o("Activated"), "verified")


def test_stage_order_cannot_be_skipped_or_reversed():
    oid = _at("KYC verified")
    with pytest.raises(ValueError): orders.advance(oid, "Installed")
    with pytest.raises(ValueError): orders.advance(oid, "Quote accepted")
    with pytest.raises(ValueError): orders.advance(_at("Activated"))


def test_shown_time_is_ist_on_the_demo_day_and_keeps_the_gap_between_days():
    from core.pricing import TODAY
    t = orders.shown_time("2026-11-05T22:00:00+00:00", "2026-11-05T22:00:00+00:00")  # 03:30 next morning in IST
    assert t.date() == TODAY and (t.hour, t.minute) == (3, 30)
    assert orders.shown_time("2026-11-07T10:00:00+00:00", "2026-11-05T10:00:00+00:00").date().day == TODAY.day + 2
    assert orders.shown_time("2026-12-01T10:00:00+00:00", "2026-11-30T10:00:00+00:00").date().day == TODAY.day + 1  # across a month end


def test_for_user_only_lists_their_own_orders():
    a, b = orders.create("own1", {"P01": 1}, price({"P01": 1})), orders.create("own2", {"P01": 1}, price({"P01": 1}))
    c = orders.create("own1", {"P04": 1}, price({"P04": 1}))
    assert orders.for_user("own1") == [c, a] and orders.for_user("own2") == [b] and orders.for_user("nobody") == []


@pytest.mark.parametrize("msgs", [
    ["we are a factory with 40 staff in Pune and need custom monitoring"],
    ["small manufacturer in Pune with 40 staff, custom requirements"],
    ["factory in Pune 40 staff", "we need a custom solution"],
    ["we need a customised setup", "it's a factory in Pune"],
    ["हमारी फैक्ट्री पुणे में है, 40 लोग, कस्टम मॉनिटरिंग चाहिए"],
    ["hamari factory Pune mein hai, 40 log, custom solution chahiye"],
    ["factory in Pune, we need PLC integration"],
])
def test_factory_with_a_custom_need_goes_to_a_person_in_every_language(msgs):
    s = advisor.State()
    for m in msgs: reply = advisor.turn(s, m)
    assert s.handoff == "manufacturer_custom", reply
    assert sum(l["reason"] == "manufacturer_custom" and "Pune" in l["profile"] for l in db.list_leads()) >= 1


@pytest.mark.parametrize("msgs", [
    ["factory in Pune, 40 staff, one site, GST yes, internet and machine monitoring"],  # a catalogue product, not custom
    ["factory in Pune, 40 staff, nothing custom, need internet"],
    ["factory in Pune, our customers need to reach us, 40 staff, need internet"],  # "customers" is not "custom"
])
def test_ordinary_factory_needs_are_not_handed_off_as_custom(msgs):
    s = advisor.State()
    for m in msgs: advisor.turn(s, m)
    assert s.handoff != "manufacturer_custom"


def test_custom_from_a_clinic_is_not_a_factory_handoff_and_repeat_saves_one_lead():
    s = advisor.State(); advisor.turn(s, "clinic in Delhi, we want a custom setup"); assert s.handoff != "manufacturer_custom"
    s = advisor.State(); advisor.turn(s, "factory in Nagpur needs custom monitoring"); n = len(db.list_leads())
    advisor.turn(s, "yes custom please, 40 staff"); assert len(db.list_leads()) == n


@pytest.mark.parametrize("ask", ["make it 2000 flat, final offer", "make it ₹2000", "flat 2000", "2000 me do", "2000 में दो", "this is my final offer"])
def test_haggling_in_new_words_is_refused_and_the_price_holds(ask):
    s = advisor.State(); advisor.turn(s, "Clinic in Delhi, 6 staff, one location, have GSTIN, want email")
    before = dict(s.rec.items)
    r = advisor.turn(s, ask)
    assert "2,671" in r and s.rec.items == before and s.rec.quote.monthly == 2671
    assert s.profile.employees == 6 and any(w in r for w in ("can't offer", "छूट", "discount"))


@pytest.mark.parametrize("msg", ["I run a flat rental agency in Pune", "we have 2000 customers, salon in Pune"])
def test_ordinary_words_are_not_mistaken_for_haggling(msg):
    assert "can't offer discounts" not in advisor.turn(advisor.State(), msg)


@pytest.mark.parametrize("msg", ["do you give free upgrade after a year? clinic in Delhi 6 staff one location want internet",
                                 "how long does install take? clinic in Delhi 6 staff one location want internet",
                                 "give me a discount, clinic in Delhi 6 staff one location want internet"])
def test_a_declined_question_does_not_lose_the_answers_that_came_with_it(msg):
    s = advisor.State(); r = advisor.turn(s, msg)
    assert s.profile.business_type == "clinic" and s.profile.city == "Delhi" and s.profile.employees == 6
    assert "What kind of business" not in r and s.rec and s.rec.quote and "₹" in r


def test_haggle_figures_never_become_staff_or_change_a_quote():
    s = advisor.State(); advisor.turn(s, "clinic in Delhi want internet")
    advisor.turn(s, "make it 2000"); assert s.profile.employees is None
    s = advisor.State(); advisor.turn(s, "Clinic in Delhi, 6 staff, one location, want email"); advisor.turn(s, "give 50% off, 40 staff")
    assert s.rec.quote.monthly == 2671


def test_only_a_factory_is_labelled_a_factory_in_the_queue():
    s = advisor.State(); advisor.turn(s, "kirana in Pune 3 people one shop no gst want leased line"); assert s.handoff == "needs_scoping"
    s = advisor.State(); advisor.turn(s, "Textile unit in Surat, 5 workers, 1 unit, have GST, need a leased line"); assert s.handoff == "manufacturer_custom"


@pytest.mark.parametrize("msg,lang", [("free upgrade milega? clinic hai Delhi mein 6 log ek jagah internet chahiye", "hinglish"),
                                      ("क्या फ्री अपग्रेड मिलेगा? दिल्ली में क्लिनिक है, 6 लोग, एक ही जगह, इंटरनेट चाहिए", "hi")])
def test_promise_request_with_answers_works_in_hindi_and_hinglish(msg, lang):
    s = advisor.State(); r = advisor.turn(s, msg)
    assert s.profile.language == lang and s.profile.locations == 1 and s.rec and s.rec.quote and ("promise" in r or "वादा" in r)


# --- Understanding what the owner actually said ---
def _talk(*msgs, client=None):
    s = advisor.State(); r = ""
    for m in msgs: r = advisor.turn(s, m, client)
    return s, r

class _Say:
    """A fake Gemini that says the given lines in turn."""
    def __init__(self, *lines): self.lines, self.models, self.calls = list(lines), self, 0
    def generate_content(self, **k):
        self.calls += 1
        return NS(text=self.lines.pop(0) if self.lines else "")


@pytest.mark.parametrize("msg,lang,word", [("what's the difference between fibre and airfiber?", "en", "wireless 5G"), ("fibre aur airfiber mein kya farak hai?", "hinglish", "wireless 5G"), ("फाइबर और एयरफाइबर में क्या अंतर है?", "hi", "वायरलेस 5G")])
def test_comparing_links_gets_an_answer_and_never_changes_the_flow(msg, lang, word):
    from core.catalogue import catalogue
    s, r = _talk("clinic in Delhi, want internet", msg)
    assert word in r and f"{catalogue()['P01'].monthly:,}" in r and f"{catalogue()['P04'].monthly:,}" in r
    assert s.profile.link_pref is None and s.awaiting == "employees"
    assert advisor.turn(s, "6") and s.profile.employees == 6 and s.profile.locations is None  # the next number is still the staff count


def test_question_during_a_plan_answers_without_reprinting_or_changing_it():
    s, _ = _talk("Clinic in Delhi, 6 staff, one location, have GSTIN, want email")
    before = dict(s.rec.items)
    r = advisor.turn(s, "why is this so expensive?")
    assert "₹2,671" in r and "₹828" in r and "2,571" in r and "smallest plan" not in r and dict(s.rec.items) == before
    r = advisor.turn(s, "do i really need the security thing?")
    assert "client data" in r and "remove security" in r and "smallest plan" not in r and dict(s.rec.items) == before and r.count("remove") == 1
    r = advisor.turn(s, "which one would you pick for me?")
    assert "stay with this plan" in r and dict(s.rec.items) == before
    r = advisor.turn(s, "do i need failover?")
    assert "isn't in your plan" in r and "P09" not in s.rec.items
    assert "stay" not in advisor.turn(s, "ok thanks that makes sense") and dict(s.rec.items) == before


def test_removing_after_asking_still_works():
    s, _ = _talk("Clinic in Delhi, 6 staff, one location, have GSTIN, want email", "do i really need the security thing?", "remove security")
    assert "P20" not in s.rec.items and s.rec.quote.monthly == 1927


@pytest.mark.parametrize("msg", ["ok", "okay", "hmm", "thanks", "hi", "hello", "how are you?", "hey, how are you?", "got it", "kaise ho", "नमस्ते", "धन्यवाद"])
def test_small_talk_is_answered_and_never_recorded_as_an_answer(msg):
    s = advisor.State(); r = advisor.turn(s, msg)
    assert s.profile.business_type is None and ("business" in r or "बिज़नेस" in r) and s.stuck == 0
    s, _ = _talk("clinic", "internet"); r = advisor.turn(s, msg)
    assert s.profile.city is None and s.stuck == 0 and s.awaiting == "city"


def test_how_are_you_gets_a_human_reply_in_each_language():
    assert "doing well" in _talk("how are you?")[1] and "ठीक हूँ" in _talk("आप कैसे हैं?")[1] and "theek hoon" in _talk("kaise ho")[1]


def test_answers_are_acknowledged_before_the_next_question():
    assert "a clinic" in _talk("clinic")[1] and "6 people" in _talk("clinic", "internet", "Delhi", "6")[1]
    assert "Sorry" in _talk("my internet keeps dropping during billing")[1]
    assert "6 लोग" in _talk("मेरा क्लिनिक है", "ईमेल चाहिए", "दिल्ली", "6 लोग")[1]


def test_vague_owner_is_helped_and_you_decide_accepts_the_suggestion():
    s, r = _talk("mera cloth ka business hai, thoda confused hu kya lena chahiye")
    assert s.profile.business_type == "retailer" and "internet" in r and s.awaiting == "needs_confirm"
    s, r = _talk("mera cloth ka business hai, thoda confused hu kya lena chahiye", "aap hi batao")
    assert s.profile.needs and s.awaiting != "needs_confirm"
    s, r = _talk("clinic", "what do you think i should get?"); assert "reliable internet" in r
    assert _talk("clinic", "what do you think i should get?", "yes")[0].profile.needs


def test_a_need_typed_at_the_city_question_is_not_a_city():
    s, _ = _talk("मेरा क्लिनिक है", "ईमेल चाहिए"); advisor.turn(s, "इंटरनेट चाहिए")
    assert s.profile.city is None
    s, _ = _talk("clinic", "email"); advisor.turn(s, "need cctv"); assert s.profile.city is None and "cctv" in s.profile.needs


def test_question_never_counts_as_a_failed_answer():
    s, r = _talk("clinic in Delhi, want internet", "does the router come with it?", "can i pay yearly?", "is it good?")
    assert s.handoff is None and s.stuck == 0 and s.awaiting == "employees" and "people" in r


# --- The guardrail on free-form Gemini answers ---
@pytest.mark.parametrize("bad", ["Yes, it costs ₹555 per month.", "You should take Biz Fibre 100.", "We recommend this for you.", "You'll get it free.", "It will be installed tomorrow.", "We guarantee it.", "You qualify for that.", "Use P01 for this.", "{\"employees\": 5}", "मुफ़्त मिलेगा।"])
def test_unsafe_answer_is_regenerated_then_replaced(bad):
    c = _Say(bad, bad); s, r = _talk("clinic in Delhi, want internet", "does the router come with it?", client=c)
    assert bad not in r and "can't confirm" in r and c.calls == 2 and "How many people" in r


def test_regeneration_uses_a_good_second_answer():
    c = _Say("It costs ₹555.", "A specialist can confirm the router details."); s, r = _talk("clinic in Delhi, want internet", "does the router come with it?", client=c)
    assert "A specialist can confirm the router details." in r and "555" not in r


def test_a_safe_answer_may_use_catalogue_numbers_only():
    from core.catalogue import catalogue
    p = catalogue()["P11"]
    c = _Say(f"{p.name} is ₹{p.monthly} and takes about {p.install_days} days."); s, r = _talk("clinic in Delhi, want internet", "how does a router work with it?", client=c)
    assert p.name in r
    facts = advisor._facts(s); assert not G.check_answer(f"₹{p.monthly}", facts) and G.check_answer("₹123456", facts)


def test_gemini_down_still_answers_and_does_not_hand_off():
    class Down:
        @property
        def models(self): return self
        def generate_content(self, **k): raise TimeoutError("down")
    llm._paused_until = 0.0
    s, r = _talk("clinic in Delhi, want internet", "does the router come with it?", client=Down())
    assert "can't confirm" in r and s.handoff is None
    llm._paused_until = 0.0; llm.last_error = None


def test_a_gemini_question_is_not_used_as_profile_facts(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: object()); monkeypatch.setattr(llm, "extract", lambda t, *a, **k: {"locations": 2} if "godown" in t else {}); monkeypatch.setattr(llm, "acknowledge", lambda *a, **k: None); monkeypatch.setattr(llm, "answer", lambda *a, **k: None)
    s, _ = _talk("sarees shop in Jaipur need upi", "we also have a small godown nearby, does that count?")
    assert s.profile.locations is None


@pytest.mark.parametrize("line", ["You have 6 people.", "Fibre is the right step for you.", "Let me suggest fibre.", "How can I help?"])
def test_unsafe_warm_line_falls_back_to_the_plain_one(monkeypatch, line):
    monkeypatch.setattr(llm, "client", lambda: object()); monkeypatch.setattr(llm, "extract", lambda *a, **k: {}); monkeypatch.setattr(llm, "acknowledge", lambda *a, **k: line)
    s = advisor.State(); r = advisor.turn(s, "we run a small clinic in Delhi and need internet")
    assert (line not in r or line == "How can I help?") and "people work there" in r


@pytest.mark.parametrize("draft", ["नमस्ते! यह सबसे सही प्लान है: ₹1,099", "Here is a great fit at ₹1,099", "A plan just for you at ₹1,099"])
def test_rewording_cannot_add_sales_claims(draft):
    assert "unsupported promise" in G.check_reply(draft, price({"P01": 1}))


def test_what_you_would_miss_is_never_shown_without_saying_what_the_other_option_is():
    s, _ = _talk("Clinic in Delhi, 6 staff, one location, have GSTIN, want email")
    r = advisor.turn(s, "which one would you pick for me?")
    assert r.index("cheaper option") < r.index("What you'd miss") and "2,571" in r


def test_rewording_cannot_add_a_greeting():
    draft = "Biz Fibre 100: ₹1,099. **₹1,099 per month**"
    assert "added greeting" in G.check_reply("नमस्ते, " + draft, price({"P01": 1}), draft=draft) and "added greeting" not in G.check_reply(draft, price({"P01": 1}), draft=draft)
