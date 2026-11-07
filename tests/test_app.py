"""Headless smoke test of every page via Streamlit's AppTest."""
import os, sys, pathlib, tempfile
ROOT = pathlib.Path(__file__).parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import pytest
from streamlit.testing.v1 import AppTest
from core.advisor import State, turn

@pytest.mark.parametrize("page", ["Home.py", "pages/1_Advisor.py", "pages/2_Quote.py", "pages/3_Consent.py", "pages/4_KYC.py", "pages/5_Tracker.py", "pages/6_Partner_Queue.py", "pages/7_Your_Data.py"])
def test_pages_render(page):
    at = AppTest.from_file(str(ROOT / "app" / page), default_timeout=30).run()
    assert not at.exception

def test_chat_then_quote_then_accept():
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    at.chat_input[0].set_value("Clinic in Delhi, 6 staff, one location, have GSTIN, want email").run()
    assert not at.exception
    assert any("per month" in m.markdown[0].value for m in at.chat_message if m.markdown)
    state = at.session_state["advisor"]
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["advisor"] = state
    q.run(); assert not q.exception
    assert f"{state.rec.quote.monthly:,}" in " ".join(m.value for m in q.markdown)
    next(b for b in q.button if b.label == "Accept quote").click().run(); assert not q.exception and q.session_state["order_id"]


def test_rejected_kyc_cannot_be_advanced_verified_can():
    from core import consent, orders
    from core.pricing import price
    oid = orders.create("gate-user", {"P01": 1}, price({"P01": 1}))
    consent.grant("gate-user", consent.KYC, "en")
    k = AppTest.from_file(str(ROOT / "app/pages/4_KYC.py"), default_timeout=120)
    k.session_state["user"], k.session_state["order_id"] = "gate-user", oid
    k.run(); assert not k.exception
    k.selectbox[0].set_value("K01").run()
    next(b for b in k.button if b.label == "Verify").click().run(); assert not k.exception
    assert any("Rejected" in e.value for e in k.error) and orders.get(oid)["stage"] == "Quote accepted"
    t = AppTest.from_file(str(ROOT / "app/pages/5_Tracker.py"), default_timeout=30)
    t.session_state["user"], t.session_state["order_id"] = "gate-user", oid
    t.run(); assert not t.exception
    assert t.warning and not [b for b in t.button if b.label == "Advance stage"]
    k.selectbox[0].set_value("K03").run()
    next(b for b in k.button if b.label == "Verify").click().run(); assert not k.exception
    assert any("Verified" in e.value for e in k.success) and orders.get(oid)["stage"] == "KYC verified"
    t.run(); assert not [b for b in t.button if b.label == "Advance stage"] and [b for b in t.button if "Pay first" in b.label]


def test_two_sessions_do_not_share_an_identity():
    a = AppTest.from_file(str(ROOT / "app/pages/3_Consent.py"), default_timeout=30).run()
    b = AppTest.from_file(str(ROOT / "app/pages/3_Consent.py"), default_timeout=30).run()
    assert not a.exception and not b.exception


def test_hindi_chat_switches_quote_page_to_hindi():
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    s = State(); turn(s, "मेरा क्लिनिक है, दिल्ली में, 6 लोग, एक ही, GSTIN है, ईमेल चाहिए")
    q.session_state["advisor"] = s
    q.run(); assert not q.exception and q.session_state["ui_lang"] == "hi"
    assert any("प्रति माह" in m.value for m in q.markdown)


def test_start_over_clears_the_visible_chat():
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    at.chat_input[0].set_value("clinic in Delhi").run()
    at.chat_input[0].set_value("start over").run()
    assert not at.exception
    assert len(at.session_state["chat"]) == 1 and "start over" in at.session_state["chat"][0][1]
    assert at.session_state["advisor"].profile.business_type is None


def test_chat_from_before_a_deploy_does_not_crash():
    old = State(); turn(old, "clinic in Delhi")
    for field in ("restarted", "declined", "stuck"): delattr(old, field)
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30)
    at.session_state["advisor"] = old
    at.session_state["chat"] = [("assistant", "old message")]
    at.run(); assert not at.exception
    at.chat_input[0].set_value("kirana in Pune").run(); assert not at.exception
    assert at.session_state["advisor"].profile.business_type == "kirana"


def test_new_chat_button_resets_the_chat_and_keeps_the_language():
    new_chat = lambda p: next(b for b in p.button if b.label in ("New chat", "नई चैट"))
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    assert not [b for b in at.button if b.label == "New chat"]  # nothing to clear yet
    at.chat_input[0].set_value("Clinic in Delhi, 6 staff, one location, have GSTIN, want email").run()
    assert at.session_state["advisor"].rec.quote
    new_chat(at).click().run(); assert not at.exception
    s = at.session_state["advisor"]
    assert s.rec is None and s.profile.business_type is None and len(at.session_state["chat"]) == 1
    at.chat_input[0].set_value("मेरा क्लिनिक है").run()
    new_chat(at).click().run(); assert not at.exception
    assert at.session_state["ui_lang"] == "hi" and at.session_state["advisor"].profile.language == "hi"
    assert "नमस्ते" in at.session_state["chat"][0][1]


def test_quote_addon_can_answer_a_question_the_chat_skipped():
    s = State()
    for m in ("clinic", "internet", "Delhi", "6", "1"): turn(s, m)
    assert s.rec.quote and s.profile.has_gstin is None
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["advisor"] = s
    q.run(); assert not q.exception
    whatsapp = next(c for c in q.checkbox if c.key == "addon_P15")
    assert whatsapp.disabled and "GSTIN" in whatsapp.label
    next(c for c in q.checkbox if c.key == "quote_gstin").check().run()
    whatsapp = next(c for c in q.checkbox if c.key == "addon_P15")
    assert not whatsapp.disabled
    whatsapp.check().run(); assert not q.exception
    assert any("1,249" in m.value or "2,348" in m.value for m in q.markdown)


def test_callback_form_needs_contact_and_consent_and_masks_in_queue():
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    at.chat_input[0].set_value("this is useless, let me talk to a human").run()
    submit = next(b for b in at.button if "call back" in b.label)
    submit.click().run()
    assert any("mobile number" in e.value for e in at.error)
    at.text_input[1].set_value("9876543210")
    next(b for b in at.button if "call back" in b.label).click().run()
    assert any("tick" in e.value for e in at.error)
    at.checkbox[0].check()
    next(b for b in at.button if "call back" in b.label).click().run()
    assert not at.exception and at.success
    q = AppTest.from_file(str(ROOT / "app/pages/6_Partner_Queue.py"), default_timeout=60).run()
    assert not q.exception
    shown = " ".join(d.value.astype(str).to_string() for d in q.dataframe)  # every table on the page, not just the first
    assert "9876543210" not in shown and "3210" in shown
    next(b for b in at.button if "Delete" in b.label).click().run()
    assert not at.exception and not at.success


def _quote(*msgs):
    s = State()
    for m in msgs: turn(s, m)
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["advisor"] = s
    return q.run()


def _big(q): return next(m.value for m in q.markdown if 'class="big-price"' in m.value)
CLINIC = "Clinic in Delhi, 6 staff, one location, have GSTIN, want email"


def test_price_comes_before_addons_and_shows_totals():
    q = _quote(CLINIC); assert not q.exception
    labels = {m.label: m.value for m in q.metric}
    assert labels["First payment"] == "₹2,671" and labels["Total over 12 months"] == f"₹{2671 * 12:,}"
    assert any("about 5 days" in x.value and "estimate" in x.value for x in q.caption)
    assert [b for b in q.button if "cheaper" in b.label]


def test_accept_greys_out_at_once_and_replan_updates_the_same_order():
    q = _quote(CLINIC)
    accept = next(b for b in q.button if b.label == "Accept quote")
    accept.click().run(); assert not q.exception
    assert next(b for b in q.button if b.label == "Accept quote").disabled and q.success
    oid = q.session_state["order_id"]
    next(c for c in q.checkbox if c.key == "addon_P23").check().run()
    accept = next(b for b in q.button if b.label == "Accept quote"); assert not accept.disabled
    accept.click().run()
    from core import orders
    assert q.session_state["order_id"] == oid and orders.get(oid)["monthly"] == 2671 + 249


def test_cheaper_option_switch_and_back():
    q = _quote(CLINIC); assert "2,671" in _big(q)
    assert any("Saves ₹100" in x.value for x in q.success)
    next(b for b in q.button if "cheaper" in b.label).click().run(); assert not q.exception and "2,571" in _big(q)
    next(b for b in q.button if "recommended" in b.label).click().run(); assert not q.exception and "2,671" in _big(q)


def test_quantity_changes_the_server_price():
    q = _quote(CLINIC)
    next(n for n in q.number_input if n.key == "qty_P16").set_value(10).run(); assert not q.exception
    assert f"{2671 + 4 * 138:,}" in _big(q)


def test_replacing_airfiber_is_explained():
    q = _quote("kirana in Pune, 3 people, one shop, no GST, need internet")
    next(c for c in q.checkbox if c.key == "addon_P09").check().run(); assert not q.exception
    notes = " ".join(i.value for i in q.info)
    assert "replaces Biz 5G AirFiber 100" in notes and "12 months (it was 6)" in notes


def test_current_bill_comparison_and_download():
    q = _quote(CLINIC)
    next(n for n in q.number_input if n.key == "current_bill").set_value(3000).run(); assert not q.exception
    assert any("₹329 a month less" in m.value for m in q.markdown)


def test_quote_page_says_why_and_what_the_cheaper_option_gives_up():
    q = _quote("clinic in Delhi 6 staff 1 location need internet")
    assert any("Why:" in x.value and "lowest-priced wired" in x.value for x in q.caption)
    assert any("you'd get wireless 5G" in x.value for x in q.success)
    next(b for b in q.button if "cheaper" in b.label).click().run(); assert not q.exception
    assert any("miss" in w.value for w in q.warning)


def _page(name, user, **state):
    a = AppTest.from_file(str(ROOT / "app/pages" / name), default_timeout=120)
    a.session_state["user"] = user
    for k, v in state.items(): a.session_state[k] = v
    return a.run()


def test_consent_needs_a_tick_stores_each_purpose_and_blocks_kyc():
    from core import consent
    k = _page("4_KYC.py", "c1"); assert k.warning and not [b for b in k.button if b.label == "Verify"]
    c = _page("3_Consent.py", "c1")
    assert [x.value for x in c.checkbox] == [False, False]
    save = next(b for b in c.button if b.label == "Save consent"); assert save.disabled
    next(x for x in c.checkbox if "optional" in x.label).check().run()
    assert next(b for b in c.button if b.label == "Save consent").disabled and not consent.active("c1")  # optional alone isn't enough
    next(x for x in c.checkbox if "required" in x.label).check().run()
    next(b for b in c.button if b.label == "Save consent").click().run(); assert not c.exception
    assert consent.active("c1") == {consent.KYC, consent.UPDATES}
    r = consent.records("c1")[0]
    assert r["notice_version"] == consent.NOTICE_VERSION and r["language"] == "en" and r["granted_at"] and not r["withdrawn_at"]
    k = _page("4_KYC.py", "c1"); assert not k.warning and [b for b in k.button if b.label == "Verify"]


def test_coming_back_shows_status_and_allows_withdrawal_without_an_order():
    from core import consent
    consent.grant("c2", consent.KYC, "en")
    c = _page("3_Consent.py", "c2")
    assert any("KYC consent is given" in s.value for s in c.success) and not [x for x in c.checkbox if "required" in x.label]
    t = _page("5_Tracker.py", "c2"); assert t.info
    next(b for b in t.button if b.label == "Withdraw: KYC verification").click().run(); assert not t.exception
    assert not consent.active("c2") and consent.records("c2")[0]["withdrawn_at"]


def test_withdrawn_verdict_never_comes_back_on_screen():
    from core import consent, orders
    from core.pricing import price
    oid = orders.create("c3", {"P01": 1}, price({"P01": 1})); consent.grant("c3", consent.KYC, "en")
    k = _page("4_KYC.py", "c3", order_id=oid)
    k.selectbox[0].set_value("K03").run(); next(b for b in k.button if b.label == "Verify").click().run()
    assert any("Verified" in s.value for s in k.success)
    consent.withdraw("c3", consent.KYC); k.run(); assert k.warning
    consent.grant("c3", consent.KYC, "en"); k.run(); assert not k.exception
    assert not [s for s in k.success if "Verified" in s.value] and consent.latest_kyc("c3") is None
    t = _page("5_Tracker.py", "c3", order_id=oid); assert t.warning and not [b for b in t.button if b.label == "Advance stage"]
    assert not [b for b in k.button if "Pay first" in b.label]


def test_notice_covers_what_the_person_must_know_in_both_languages():
    from core.consent import NOTICE
    for words in (["collect", "Why", "How long", "Who sees", "withdraw", "Data Protection Board"], ):
        for w in words: assert w in NOTICE["en"], w
    for w in ["क्या लेते", "क्यों", "कितने समय", "कौन देखता", "वापस", "डेटा संरक्षण बोर्ड"]: assert w in NOTICE["hi"], w


def test_hindi_consent_page_stores_hindi_and_plain_labels():
    from core import consent
    c = _page("3_Consent.py", "c4", ui_lang="hi")
    assert not c.exception and any("KYC सत्यापन" in x.label for x in c.checkbox)
    next(x for x in c.checkbox if "ज़रूरी" in x.label).check().run()
    next(b for b in c.button if "सहमति" in b.label).click().run()
    assert consent.records("c4")[0]["language"] == "hi" and any("KYC सहमति" in s.value for s in c.success)
    assert [b for b in c.button if b.label == "वापस लें: KYC सत्यापन"]


def _bar(page):
    """Each step's state on the page's progress bar, and which step is marked as now."""
    import re
    html = next(m.value for m in page.markdown if 'class="steps"' in m.value)
    found = re.findall(r'<li class="(\w+)( now)?"[^>]*>.*?</span>(.+?)<span', html)
    return {label: cls for cls, _, label in found}, next(label for cls, now, label in found if now)


def test_progress_bar_follows_the_real_journey_on_every_page():
    from core import consent, orders
    from core.pricing import price
    u = "j1"
    assert _bar(_page("3_Consent.py", u)) == ({"Quote": "todo", "Consent": "todo", "KYC": "todo", "Payment": "todo", "Tracking": "todo"}, "Consent")
    oid = orders.create(u, {"P01": 1}, price({"P01": 1}))
    c = _page("3_Consent.py", u, order_id=oid); assert _bar(c)[0]["Quote"] == "done" and _bar(c)[0]["Consent"] == "todo"
    next(x for x in c.checkbox if "required" in x.label).check().run()
    next(b for b in c.button if b.label == "Save consent").click().run()
    assert _bar(c)[0]["Consent"] == "done"
    k = _page("4_KYC.py", u, order_id=oid); assert _bar(k)[1] == "KYC" and _bar(k)[0]["KYC"] == "todo"
    k.selectbox[0].set_value("K01").run(); next(b for b in k.button if b.label == "Verify").click().run()
    assert _bar(k)[0]["KYC"] == "attention" and _bar(k)[1] == "KYC"
    k.selectbox[0].set_value("K03").run(); next(b for b in k.button if b.label == "Verify").click().run()
    assert _bar(k)[0]["KYC"] == "done" and _bar(k)[1] == "Payment" and _bar(k)[0]["Payment"] == "todo"
    next(b for b in k.button if "Pay first" in b.label).click().run(); assert not k.exception
    assert _bar(k)[0]["Payment"] == "done" and any("No money moved" in x.value for x in k.success)
    assert not [b for b in k.button if "Pay first" in b.label] and orders.get(oid)["stage"] == "Payment done"
    k.run(); assert not [x for x in k.success if "No money moved" in x.value]  # the note shows once
    t = _page("5_Tracker.py", u, order_id=oid); assert _bar(t) == ({"Quote": "done", "Consent": "done", "KYC": "done", "Payment": "done", "Tracking": "todo"}, "Tracking")
    consent.withdraw(u, consent.KYC); t.run()
    assert _bar(t)[0] == {"Quote": "done", "Consent": "todo", "KYC": "todo", "Payment": "done", "Tracking": "todo"}
    assert _bar(_quote(CLINIC))[1] == "Quote"


def test_progress_bar_is_translated_and_says_its_state_in_words():
    c = _page("3_Consent.py", "j2", ui_lang="hi")
    html = next(m.value for m in c.markdown if 'class="steps"' in m.value)
    for w in ("कोटेशन", "सहमति", "भुगतान", "ट्रैकिंग", "बाकी"): assert w in html
    assert "Quote" not in html and 'aria-current="step"' in html


def test_kyc_done_before_the_quote_does_not_strand_the_order():
    from core import consent, orders
    consent.grant("j3", consent.KYC, "en")
    k = _page("4_KYC.py", "j3")
    k.selectbox[0].set_value("K03").run(); next(b for b in k.button if b.label == "Verify").click().run()
    assert not [b for b in k.button if "Pay first" in b.label]  # nothing to pay for yet
    q = _quote_for("j3"); next(b for b in q.button if b.label == "Accept quote").click().run(); assert not q.exception
    oid = q.session_state["order_id"]; assert orders.get(oid)["stage"] == "KYC verified"
    k.session_state["order_id"] = oid; k.run()
    assert [b for b in k.button if "Pay first" in b.label]


def test_unverified_kyc_does_not_move_an_accepted_order():
    from core import consent, orders
    consent.grant("j4", consent.KYC, "en")
    consent.save_kyc("j4", "needs_review", "old bill", "{}")
    q = _quote_for("j4"); next(b for b in q.button if b.label == "Accept quote").click().run()
    assert orders.get(q.session_state["order_id"])["stage"] == "Quote accepted"


def test_plan_change_after_kyc_keeps_one_order_and_after_payment_says_it_is_separate():
    from core import consent, orders
    consent.grant("j5", consent.KYC, "en"); consent.save_kyc("j5", "verified", "ok", "{}")
    q = _quote_for("j5"); next(b for b in q.button if b.label == "Accept quote").click().run()
    oid = q.session_state["order_id"]; assert orders.get(oid)["stage"] == "KYC verified"
    next(x for x in q.checkbox if x.key == "addon_P23").check().run()
    next(b for b in q.button if b.label == "Accept quote").click().run(); assert not q.exception
    assert q.session_state["order_id"] == oid and orders.get(oid)["monthly"] == 2671 + 249 and orders.get(oid)["stage"] == "KYC verified"
    orders.advance(oid, "Payment done"); q.run()
    assert next(b for b in q.button if b.label == "Accept quote").disabled  # same plan: nothing to accept
    next(x for x in q.checkbox if x.key == "addon_P23").uncheck().run()
    assert any("separate order" in x.value for x in q.caption)
    next(b for b in q.button if b.label == "Accept as a new order").click().run(); assert not q.exception
    new = q.session_state["order_id"]
    assert new != oid and orders.get(oid)["monthly"] == 2671 + 249 and orders.get(oid)["stage"] == "Payment done"
    assert orders.get(new)["monthly"] == 2671 and orders.get(new)["stage"] == "KYC verified"


def _quote_for(user):
    s = State(); turn(s, CLINIC)
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["user"], q.session_state["advisor"] = user, s
    return q.run()


def test_consent_page_leads_with_the_summary_and_keeps_the_full_notice_one_tap_away():
    from core.consent import NOTICE, NOTICE_SHORT, DOCS_NEEDED
    for lang, label in (("en", "Read full notice"), ("hi", "पूरी सूचना पढ़ें")):
        c = _page("3_Consent.py", f"n-{lang}", ui_lang=lang); assert not c.exception
        tops = [m.value for m in c.main.children.values() if getattr(m, "type", "") == "markdown"]
        assert any(NOTICE_SHORT[lang].strip() in v for v in tops) and not any(NOTICE[lang].strip() in v for v in tops)
        box = next(e for e in c.expander if e.label == label)
        assert not box.proto.expanded and NOTICE[lang].strip() in [m.value.strip() for m in box.markdown]
        for name, why in (DOCS_NEEDED[k][lang] for k in DOCS_NEEDED):
            assert any(name in v and why in v for v in tops)


def test_summary_states_the_data_purpose_rights_and_complaint_route():
    from core.consent import NOTICE_SHORT
    for w in ("GST", "Udyam", "signatory ID", "address proof", "only to verify", "deleted", "withdraw", "tracker", "Talk to a person", "Data Protection Board"): assert w in NOTICE_SHORT["en"], w
    for w in ("GST", "Udyam", "हस्ताक्षरकर्ता की ID", "पते का प्रमाण", "केवल", "हटा दिए", "वापस", "ट्रैकर", "किसी व्यक्ति से बात करें", "डेटा संरक्षण बोर्ड"): assert w in NOTICE_SHORT["hi"], w


def test_each_box_says_what_happens_on_no_and_only_while_it_is_a_choice():
    from core import consent
    c = _page("3_Consent.py", "n1")
    said = [x.value for x in c.caption if x.value.startswith("If you say no")]
    assert len(said) == 2 and "can't activate" in said[0] and "still check your order" in said[1]
    assert sum("अगर आप मना करते हैं" in x.value for x in _page("3_Consent.py", "n1h", ui_lang="hi").caption) == 2
    consent.grant("n2", consent.KYC, "en")
    assert [x.value for x in _page("3_Consent.py", "n2").caption if x.value.startswith("If you say no")] == [said[1]]


def test_boxes_are_unticked_again_after_withdrawal():
    from core import consent
    c = _page("3_Consent.py", "n3")
    next(x for x in c.checkbox if "required" in x.label).check().run()
    next(b for b in c.button if b.label == "Save consent").click().run()
    next(b for b in c.button if b.label == "Withdraw: KYC verification").click().run(); assert not c.exception
    assert [x.value for x in c.checkbox] == [False, False] and not consent.active("n3")
    assert next(b for b in c.button if b.label == "Save consent").disabled


def test_receipt_button_appears_once_there_is_something_to_prove():
    from core import consent
    def buttons(p): return p.get("download_button")
    assert not buttons(_page("3_Consent.py", "n4"))
    consent.grant("n4", consent.KYC, "en")
    for page in ("3_Consent.py", "5_Tracker.py"):
        got = buttons(_page(page, "n4")); assert [b.proto.label for b in got] == ["Download consent receipt", "Consent receipt for software (JSON)"]
    assert "सहमति रसीद" in buttons(_page("3_Consent.py", "n4", ui_lang="hi"))[0].proto.label


def test_save_button_is_not_left_dead_when_only_the_optional_box_remains():
    from core import consent
    consent.grant("n5", consent.KYC, "en")
    c = _page("3_Consent.py", "n5"); assert not [b for b in c.button if b.label == "Save consent"]
    next(x for x in c.checkbox if "optional" in x.label).check().run()
    next(b for b in c.button if b.label == "Save consent").click().run(); assert not c.exception
    assert consent.active("n5") == {consent.KYC, consent.UPDATES} and not c.checkbox


def test_demo_control_stays_open_between_taps():
    oid = _ready_order("n6", "Payment done")
    t = _page("5_Tracker.py", "n6", order_id=oid)
    assert not next(e for e in t.expander if e.label == "Demo control").proto.expanded
    next(b for b in t.button if b.label == "Advance stage").click().run(); assert not t.exception
    assert next(e for e in t.expander if e.label == "Demo control").proto.expanded and orders_stage(oid) == "Installation scheduled"


def orders_stage(oid):
    from core import orders
    return orders.get(oid)["stage"]


def _ready_order(user, stage, items=None):
    from core import consent, orders
    from core.pricing import price
    items = items or {"P01": 1}
    oid = orders.create(user, items, price(items))
    consent.grant(user, consent.KYC, "en"); consent.save_kyc(user, "verified", "ok", "{}")
    for s in orders.STAGES[1:orders.STAGES.index(stage) + 1]: orders.advance(oid, s)
    return oid


def _words(p): return " ".join(m.value for m in p.markdown) + " ".join(x.value for x in p.caption)


def test_tracker_walks_the_whole_order_with_times_next_steps_and_technician():
    from core import orders
    oid = _ready_order("t1", "KYC verified")
    t = _page("5_Tracker.py", "t1", order_id=oid); assert "**Next:** Payment done · You" in _words(t)
    pay = next(b for b in t.button if "Pay first" in b.label); assert "₹" in pay.label
    pay.click().run(); assert not t.exception and any("No money moved" in x.value for x in t.success) and orders_stage(oid) == "Payment done"
    assert "Installation scheduled · Accel Business" in _words(t) and "Estimated installation" in _words(t) and "not a promise" in _words(t)
    for want in orders.STAGES[3:]:
        next(b for b in t.button if b.label == "Advance stage").click().run(); assert not t.exception and orders_stage(oid) == want
        assert not [e for e in t.expander if e.label == "Demo control" and want == "Activated"]
    words = " ".join(m.value for m in t.markdown); o = orders.get(oid)  # consent records keep their real time on purpose: they're the legal proof
    assert "Your connection is active" in " ".join(x.value for x in t.success) and o["technician"] in words
    assert words.count("✅") == 7 and "⬜" not in words and "15 Jul" in words and "IST" in words and "2026-11" not in words


def test_tracker_shows_what_was_ordered_from_the_stored_order():
    from core.catalogue import catalogue
    oid = _ready_order("t2", "Payment done", {"P01": 1, "P16": 4})
    t = _page("5_Tracker.py", "t2", order_id=oid)
    box = next(e for e in t.expander if e.label == "What you ordered"); text = " ".join(m.value for m in box.markdown)
    cat = catalogue(); from core import orders; o = orders.get(oid)
    assert cat["P01"].name in text and f"{cat['P16'].name} × 4" in text and f"₹{o['monthly']:,}" in text and "P01" not in text


def test_tracker_reschedule_shows_limits_saves_and_records_it():
    from datetime import timedelta
    from core import orders
    oid = _ready_order("t3", "Installation scheduled")
    t = _page("5_Tracker.py", "t3", order_id=oid); o = orders.get(oid)
    btn = next(b for b in t.button if b.label == "Reschedule"); assert btn.disabled  # nothing changed yet
    new = orders.earliest_install(o) + timedelta(days=3)
    t.date_input[0].set_value(new).run()
    next(b for b in t.button if b.label == "Reschedule").click().run(); assert not t.exception
    assert orders.get(oid)["install_date"] == new.isoformat() and "Installation moved from" in _words(t) and new.strftime("%d %b %Y") in _words(t)


def test_tracker_never_offers_reschedule_outside_its_window_or_on_hold():
    from core import consent
    for stage in ("Payment done", "Installed", "Activated"):
        t = _page("5_Tracker.py", f"t4{stage}", order_id=_ready_order(f"t4{stage}", stage)); assert not [b for b in t.button if b.label == "Reschedule"]
    oid = _ready_order("t5", "Technician assigned"); consent.withdraw("t5", consent.KYC)
    t = _page("5_Tracker.py", "t5", order_id=oid); assert not [b for b in t.button if b.label in ("Reschedule", "Advance stage")]


def test_withdrawing_after_payment_holds_the_order_says_why_and_promises_no_refund():
    from core import consent
    oid = _ready_order("t6", "Payment done"); consent.withdraw("t6", consent.KYC)
    t = _page("5_Tracker.py", "t6", order_id=oid); words = _words(t)
    assert t.warning and "consent isn't active" in words and "payment is recorded" in words and "refund" not in words.lower()
    assert "Estimated installation" not in words and not [b for b in t.button if b.label == "Advance stage"]
    consent.grant("t6", consent.KYC, "en"); consent.save_kyc("t6", "verified", "ok", "{}"); t.run()
    assert not t.warning and "Estimated installation" in _words(t) and orders_stage(oid) == "Payment done"


def test_needs_review_holds_a_paid_order_and_points_to_kyc():
    from core import consent
    oid = _ready_order("t7", "Payment done"); consent.save_kyc("t7", "needs_review", "old bill", "{}")
    t = _page("5_Tracker.py", "t7", order_id=oid); assert t.warning and "consent isn't active" not in _words(t)


def test_second_order_does_not_hide_the_paid_one_and_others_never_appear():
    from core import orders
    from core.pricing import price
    paid = _ready_order("t8", "Payment done"); new = orders.create("t8", {"P04": 1}, price({"P04": 1}))
    other = _ready_order("t9", "Payment done")
    t = _page("5_Tracker.py", "t8", order_id=new); box = t.selectbox[0]
    assert box.options and len(box.options) == 2 and not any(f"#{other} " in x for x in box.options)
    assert t.markdown and "Quote accepted" in " ".join(m.value for m in t.markdown)
    t.selectbox[0].select_index(1).run(); assert not t.exception and "### Payment done" in [m.value for m in t.markdown]
    assert t.session_state["order_id"] == new  # looking at an old order doesn't change which one is being worked on
    t2 = _page("5_Tracker.py", "t8", order_id=other); assert not t2.exception and "### Quote accepted" in [m.value for m in t2.markdown]  # someone else's id is ignored


def test_a_missing_order_never_crashes_any_page():
    for page in ("2_Quote.py", "3_Consent.py", "4_KYC.py", "5_Tracker.py"):
        p = _page(page, "t10", order_id=99999); assert not p.exception, page
        assert "order_id" not in p.session_state or not p.session_state["order_id"]


def test_tracker_with_no_order_points_to_the_quote():
    t = _page("5_Tracker.py", "t11"); assert t.info and not t.exception


def test_tracker_in_hindi():
    oid = _ready_order("t12", "Technician assigned")
    t = _page("5_Tracker.py", "t12", order_id=oid, ui_lang="hi"); assert not t.exception; words = _words(t)
    for w in ("अगला चरण", "अनुमानित इंस्टॉलेशन", "वादा नहीं", "आज की तारीख", "तकनीशियन"): assert w in words, w
    for w in ("Next:", "Estimated", "demo treats"): assert w not in words, w
    assert next(e for e in t.expander if e.label == "आपने क्या ऑर्डर किया")


def _verified(k, who):
    from core import consent
    consent.grant(who, consent.KYC, "en")
    p = _page("4_KYC.py", who)
    if k != "K01": p.selectbox[0].set_value(k).run()
    next(b for b in p.button if b.label == "Verify").click().run(); assert not p.exception
    return p


def test_kyc_result_is_labelled_explained_and_broken_down_by_document():
    p = _verified("K07", "kp1")
    assert any("Result for" in m.value and "K07" in m.value for m in p.markdown)
    assert any("Needs review" in w.value and "legal name" in w.value for w in p.warning)
    assert any("What happens next" in m.value for m in p.markdown)
    labels = [e.label for e in p.expander]
    assert "⚠️ GST certificate" in labels and "✅ Udyam certificate" in labels and "✅ Signatory ID" in labels and "✅ Address proof" in labels
    gst = next(e for e in p.expander if e.label == "⚠️ GST certificate"); assert gst.proto.expanded
    shown = " ".join(m.value for m in gst.markdown)
    assert "Shri Physio" in shown and "Neelgiri Physio Clinic" in shown  # what was read, trade name included, so the owner can spot it
    p.selectbox[0].set_value("K03").run()
    assert any("K07" in m.value for m in p.markdown)  # the old result stays labelled with who it belongs to


def test_kyc_page_in_hindi_has_no_english_reason_and_masks_ids():
    from core import consent
    consent.grant("kp2", consent.KYC, "hi")
    p = _page("4_KYC.py", "kp2", ui_lang="hi")
    p.selectbox[0].set_value("K11").run()
    next(b for b in p.button if b.label == "सत्यापित करें").click().run(); assert not p.exception
    assert any("जाँच ज़रूरी" in w.value and "257 दिन" in w.value for w in p.warning)
    assert any("✓ " in m.value and "रजिस्ट्री" in m.value for m in p.markdown)
    assert not [w for w in p.warning if "address proof" in w.value.lower()]
    blob = " ".join(m.value for m in p.markdown) + " ".join(x.value for x in p.caption)
    assert "SYN-ID" not in blob and "03KGZXT1320R1ZZ" not in blob and "••" in blob


def test_kyc_language_can_change_after_the_result():
    p = _verified("K11", "kp3"); assert any("days old" in w.value for w in p.warning)
    p.sidebar.radio[0].set_value("hi").run(); assert not p.exception
    assert any("दिन पुराना" in w.value for w in p.warning)


def test_nothing_identifying_reaches_the_database():
    import sqlite3
    from core import db
    _verified("K03", "kp4"); _verified("K07", "kp5"); _verified("K06", "kp6")
    with sqlite3.connect(db.DB_PATH) as conn:
        rows = conn.execute("SELECT verdict,reason,fields FROM kyc WHERE user IN ('kp4','kp5','kp6')").fetchall()
    blob = str(rows); assert len(rows) == 3
    for secret in ("447889", "SYN-ID", "27XUIXG0767D1ZP", "UDYAM-", "Joseph Singh", "Neha Banerjee", "Shri Physio"): assert secret not in blob, secret


def test_unverified_kyc_reaches_the_partner_queue_without_names_and_leaves_on_withdrawal():
    from core import consent
    _verified("K07", "queue1"); _verified("K03", "queue2")
    q = AppTest.from_file(str(ROOT / "app/pages/6_Partner_Queue.py"), default_timeout=60).run(); assert not q.exception
    table = next(d.value for d in q.dataframe if "Check" in d.value.columns)
    assert (table["Ref"] == "…eue1").any() and not (table["Ref"] == "…eue2").any()
    row = table[table["Ref"] == "…eue1"].iloc[0]
    assert row["Check"] == "GST certificate" and "Needs review" == row["Result"] and "Neha" not in row["Why"]
    consent.withdraw("queue1", consent.KYC); q.run()
    assert not any("Check" in d.value.columns and (d.value["Ref"] == "…eue1").any() for d in q.dataframe)


def test_fixing_a_result_clears_it_from_the_queue():
    from core import consent
    p = _verified("K11", "queue3")
    assert any(r["user"] == "queue3" for r in consent.kyc_queue())
    p.selectbox[0].set_value("K03").run(); next(b for b in p.button if b.label == "Verify").click().run()
    assert not any(r["user"] == "queue3" for r in consent.kyc_queue())


def test_partner_queue_self_check_matches_our_review():
    q = AppTest.from_file(str(ROOT / "app/pages/6_Partner_Queue.py"), default_timeout=180).run()
    next(b for b in q.button if b.label == "Run the self-check").click().run(); assert not q.exception
    assert any("12 of 12" in s.value for s in q.success)


def test_verified_without_a_quote_points_to_the_quote_and_can_not_pay():
    p = _verified("K03", "kp7")
    assert any("Accept a quote" in i.value for i in p.info) and not [b for b in p.button if "Pay first" in b.label]


def test_result_from_before_a_deploy_does_not_crash():
    from core import consent
    consent.grant("kp8", consent.KYC, "en"); consent.save_kyc("kp8", "verified", "ok", "{}")
    p = _page("4_KYC.py", "kp8", kyc_result={"verdict": "verified", "reason": "old", "passed": [], "fields": {}})
    assert not p.exception and not p.expander


def _kyc_page(user, **state):
    from core import consent
    consent.grant(user, consent.KYC, "en"); return _page("4_KYC.py", user, **state)


def _look(p, gstin="", udyam=""):
    p.text_input[0].set_value(gstin); p.text_input[1].set_value(udyam)
    next(b for b in p.button if b.label == "Check").click().run(); assert not p.exception


def test_lookup_catches_a_cancelled_gstin_before_any_upload_and_saves_nothing():
    from core import consent
    p = _kyc_page("lk1"); _look(p, "37IHKXV5167L1ZS")
    msg = " ".join(e.value for e in p.error); assert "cancelled" in msg and "37IHKXV5167L1ZS" not in msg and "1ZS" in msg and "Vindhya" not in msg
    assert consent.latest_kyc("lk1") is None


def test_lookup_active_unknown_and_malformed_say_so_in_plain_words():
    p = _kyc_page("lk2"); _look(p, "27XUIXG0767D1ZP", "UDYAM-MH-00-9516696")
    words = " ".join(x.value for x in p.success); assert "is active" in words and "is in the registry" in words and "Ganesh" not in words
    from core.kyc.validators import gstin_checksum
    _look(p, "27XUIXG0768D1Z" + gstin_checksum("27XUIXG0768D1Z")); assert any("couldn't find" in w.value for w in p.warning)  # valid shape, not registered
    _look(p, "27XUIXG0767D1ZQ"); assert any("check for a typo" in w.value for w in p.warning)  # one wrong character fails the checksum
    _look(p, "my aadhaar 1234"); assert any("valid GSTIN" in w.value for w in p.warning)
    assert not p.session_state["lookup"]["gst"].get("masked") and "1234" not in " ".join(w.value for w in p.warning).replace("27ABCDE1234F1Z5", "")
    _look(p); assert not p.exception and not p.warning and not p.success


def test_lookup_in_hindi_has_no_english():
    p = _kyc_page("lk3", ui_lang="hi")
    p.text_input[0].set_value("37IHKXV5167L1ZS"); next(b for b in p.button if b.label == "जाँचें").click().run(); assert not p.exception
    assert any("रद्द" in e.value for e in p.error) and not any("cancelled" in e.value for e in p.error)


def test_typed_number_is_never_stored_and_goes_with_withdrawal():
    import sqlite3
    from core import consent, db
    p = _kyc_page("lk4"); _look(p, "27XUIXG0767D1ZP")
    assert p.session_state["typed_gstin"] == "27XUIXG0767D1ZP"
    next(b for b in p.button if b.label == "Verify").click().run()
    with sqlite3.connect(db.DB_PATH) as conn: assert "27XUIXG0767D1ZP" not in str(conn.execute("SELECT * FROM kyc WHERE user='lk4'").fetchall())
    consent.withdraw("lk4", consent.KYC)
    c = _page("3_Consent.py", "lk5"); consent.grant("lk5", consent.KYC, "en"); c.run()
    c.session_state["typed_gstin"], c.session_state["lookup"] = "x", {"gst": {"state": "active"}}
    next(b for b in c.button if b.label == "Withdraw: KYC verification").click().run()
    assert "typed_gstin" not in c.session_state and "lookup" not in c.session_state


def test_upload_mode_offers_one_box_for_everything():
    p = _kyc_page("up1"); p.radio[0].set_value("upload").run(); assert not p.exception
    assert any("in any order" in x.value and "PDF" in x.value for x in p.caption)
    assert next(b for b in p.button if b.label == "Verify").disabled
    assert len(p.get("file_uploader")) == 1
    from core.kyc.pipeline import MAX_PAGES; assert MAX_PAGES >= 4


def test_time_taken_is_shown_and_measured():
    p = _verified("K03", "up2"); assert any("Checked in" in x.value and "seconds" in x.value for x in p.caption)
    assert 0 < p.session_state["kyc_result"]["seconds"] < 120


def test_old_lookup_message_does_not_sit_above_the_result():
    p = _kyc_page("up3"); _look(p, "27XUIXG0767D1ZP"); assert any("is active" in x.value for x in p.success)
    p.selectbox[0].set_value("K01").run(); next(b for b in p.button if b.label == "Verify").click().run(); assert not p.exception
    assert not any("is active" in x.value for x in p.success) and any("Rejected" in e.value for e in p.error)


def test_advisor_page_shows_the_ai_notice_tappable_answers_and_a_working_toggle():
    a = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run(); assert not a.exception
    assert any("Google Gemini" in x.value for x in a.caption) and a.toggle[0].value
    a.chat_input[0].set_value("clinic").run(); assert not a.exception
    pills = a.get("button_group"); assert pills and "Internet" in str(pills[0].proto)
    a.toggle[0].set_value(False).run(); assert a.session_state["advisor"].no_ai is True


def test_tracker_shows_a_delay_with_its_reason_and_the_airfiber_option():
    from core import orders
    oid = _ready_order("d1", "Installation scheduled")
    t = _page("5_Tracker.py", "d1", order_id=oid); assert not t.warning
    next(b for b in t.button if b.label == "Simulate a fibre delay").click().run(); assert not t.exception
    msg = " ".join(w.value for w in t.warning); assert "delayed" in msg and "Fibre can't reach" in msg
    assert "AirFiber" in _words(t) and not [b for b in t.button if b.label == "Simulate a fibre delay"]
    next(b for b in t.button if b.label == "Advance stage").click().run(); next(b for b in t.button if b.label == "Advance stage").click().run()
    assert orders.get(oid)["stage"] == "Installed" and not [w for w in t.warning if "delayed" in w.value]


def test_a_failed_payment_says_so_charges_nothing_and_can_be_retried():
    from core import orders
    oid = _ready_order("d2", "KYC verified")
    t = _page("5_Tracker.py", "d2", order_id=oid)
    next(b for b in t.button if b.label == "Simulate a failed payment").click().run(); assert not t.exception
    assert any("Nothing was charged" in e.value for e in t.error) and orders.get(oid)["stage"] == "KYC verified"
    next(b for b in t.button if "Pay first" in b.label).click().run(); assert orders.get(oid)["stage"] == "Payment done"


def test_consent_panel_shows_what_we_hold():
    from core import consent
    consent.grant("d3", consent.KYC, "en"); consent.save_kyc("d3", "verified", "ok", '{"gstin_masked": "•••1ZP"}')
    c = _page("3_Consent.py", "d3")
    assert any("What we hold" in m.value and "•••1ZP" in m.value and "No document images" in m.value for m in c.markdown)


def test_quote_page_is_open_about_gst():
    assert any("GST is included" in x.value for x in _quote(CLINIC).caption)


def test_kyc_page_explains_an_ocr_outage_and_saves_nothing(monkeypatch):
    import pytesseract
    from core import consent
    def gone(*a, **k): raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "image_to_string", gone)
    p = _kyc_page("o1"); next(b for b in p.button if b.label == "Verify").click().run(); assert not p.exception
    assert any("can't read documents right now" in e.value for e in p.error) and consent.latest_kyc("o1") is None


def test_kyc_page_tells_a_no_gstin_plan_what_it_needs():
    from core import orders
    from core.pricing import price
    oid = orders.create("o2", {"P04": 1}, price({"P04": 1})); p = _kyc_page("o2", order_id=oid); p.radio[0].set_value("upload").run()
    assert any("doesn't need a GSTIN" in i.value for i in p.info)
    oid = orders.create("o3", {"P15": 1}, price({"P15": 1})); p = _kyc_page("o3", order_id=oid); p.radio[0].set_value("upload").run()
    assert not p.info


def test_quote_line_can_be_removed_with_what_depends_on_it_and_put_back():
    q = _quote("Clinic in Delhi, 6 staff, one location, have GSTIN, want internet that stays up and email"); before = _big(q)
    assert "1,099" in " ".join(m.value for m in q.markdown) or "Fibre" in " ".join(m.value for m in q.markdown)
    fibre = next(b for b in q.button if b.label.startswith("Remove Biz Fibre")); fibre.click().run(); assert not q.exception
    assert any("also came out" in i.value and "Failover" in i.value for i in q.info) and _big(q) != before
    assert any("less than the plan I recommended" in x.value for x in q.caption) and not [b for b in q.button if "cheaper" in b.label]
    next(b for b in q.button if b.label == "Put back what I removed").click().run(); assert _big(q) == before


def test_short_form_on_the_page_gives_a_plan_and_needs_a_city():
    a = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    next(b for b in a.button if b.label == "Show my plan").click().run(); assert any("add your city" in e.value for e in a.error) and not a.session_state["advisor"].rec
    next(t for t in a.text_input if t.label == "City").set_value("Delhi")
    next(s for s in a.selectbox if s.label == "Your business").set_value("clinic")
    next(n for n in a.number_input if n.label == "People working there").set_value(6)
    next(m for m in a.multiselect if m.label == "What do you need?").set_value(["cloud_email"])
    next(b for b in a.button if b.label == "Show my plan").click().run(); assert not a.exception
    assert a.session_state["advisor"].rec.quote and "smallest plan" in a.session_state["chat"][-1][1] and not [e for e in a.expander if e.label == "Prefer a short form?"]


def test_tracker_shows_product_dates_and_an_updates_log_only_with_consent():
    from core import consent
    oid = _ready_order("o4", "Installation scheduled")
    t = _page("5_Tracker.py", "o4", order_id=oid); assert "expected about" in _words(t) and "haven't turned on" in _words(t) and "about " in _words(t)
    consent.grant("o4", consent.UPDATES, "en"); t.run()
    assert "Your order moved on" in _words(t) and "No SMS or WhatsApp is sent" in _words(t)


def test_withdrawing_shows_its_effect_and_partner_queue_shows_the_audit_log():
    from core import consent
    consent.grant("o5", consent.KYC, "en"); c = _page("3_Consent.py", "o5")
    assert any("deletes your saved KYC result" in x.value for x in c.caption)
    q = AppTest.from_file(str(ROOT / "app/pages/6_Partner_Queue.py"), default_timeout=60).run(); assert not q.exception
    assert any("consent_granted" in d.value.astype(str).to_string() for d in q.dataframe)


def test_every_label_exists_in_both_languages():
    import common
    from core import understand as U
    assert set(common.L["en"]) == set(common.L["hi"])
    for key, text in U.TALK.items(): assert {"en", "hi", "hinglish"} <= set(text), key
    from core.advisor import TXT, Q
    for key, text in list(TXT.items()) + list(Q.items()): assert "en" in text, key


def test_new_features_on_the_pages():
    """Quote shows the daily figure only in variant B, peer shares for lines in the plan, and the Your data page erases."""
    from core import consent, events
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    at.chat_input[0].set_value("Clinic in Delhi, 6 staff, one location, have GSTIN, want email").run()
    state = at.session_state["advisor"]
    for variant, shown in (("A", False), ("B", True)):
        q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
        q.session_state["advisor"] = state; q.session_state["ab_variant"] = variant
        q.run(); assert not q.exception
        captions = " ".join(x.value for x in q.caption)
        assert ("a day" in captions) == shown and "past professional offices customers had this" in captions
    assert sum(s["count"] for s in events.funnel() if s["step"] == "Quote viewed") >= 1
    d = AppTest.from_file(str(ROOT / "app/pages/7_Your_Data.py"), default_timeout=30)
    d.session_state["user"] = "demo-erase-ui"
    consent.grant("demo-erase-ui", consent.KYC, "en")
    d.run(); assert not d.exception
    d.checkbox(key="erase_sure").check().run()
    next(b for b in d.button if b.label == "Erase my data").click().run()
    assert not d.exception and consent.active("demo-erase-ui") == set() and d.session_state["user"] != "demo-erase-ui"


def test_partner_queue_dashboard_renders_with_data():
    from core import consent, events, orders
    from core.pricing import price
    events.log("pq1", "chat_started"); events.log("pq1", "quote_viewed", variant="B")
    oid = orders.create("demo-pq", {"P04": 1}, price({"P04": 1})); orders.advance(oid, "KYC verified"); orders.advance(oid, "Payment done")
    consent.grant("demo-pq2", consent.KYC, "en"); consent.save_kyc("demo-pq2", "needs_review", "Blurry", '{"issues": ["blurry_id"], "signals": [{"code": "pdf_resaved", "n": 2}]}')
    at = AppTest.from_file(str(ROOT / "app/pages/6_Partner_Queue.py"), default_timeout=120).run()
    assert not at.exception
    text = " ".join(str(x.value) for x in at.markdown) + " ".join(str(getattr(x, "value", "")) for x in at.caption)
    assert "Funnel" in text and "Against the deck's targets" in text and "Propose a decision" in text
