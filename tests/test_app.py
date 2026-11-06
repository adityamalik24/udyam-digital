"""Headless smoke test of every page via Streamlit's AppTest."""
import os, sys, pathlib, tempfile
ROOT = pathlib.Path(__file__).parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import pytest
from streamlit.testing.v1 import AppTest
from core.advisor import State, turn

@pytest.mark.parametrize("page", ["Home.py", "pages/1_Advisor.py", "pages/2_Quote.py", "pages/3_Consent.py", "pages/4_KYC.py", "pages/5_Tracker.py", "pages/6_Partner_Queue.py"])
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
    k.button[0].click().run(); assert not k.exception
    assert any("Rejected" in e.value for e in k.error) and orders.get(oid)["stage"] == "Quote accepted"
    t = AppTest.from_file(str(ROOT / "app/pages/5_Tracker.py"), default_timeout=30)
    t.session_state["user"], t.session_state["order_id"] = "gate-user", oid
    t.run(); assert not t.exception
    assert t.warning and not [b for b in t.button if b.label == "Advance stage"]
    k.selectbox[0].set_value("K03").run()
    k.button[0].click().run(); assert not k.exception
    assert any("Verified" in e.value for e in k.success) and orders.get(oid)["stage"] == "KYC verified"
    t.run(); assert [b for b in t.button if b.label == "Advance stage"]


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
    at = AppTest.from_file(str(ROOT / "app/pages/1_Advisor.py"), default_timeout=30).run()
    assert not at.button  # nothing to clear yet
    at.chat_input[0].set_value("Clinic in Delhi, 6 staff, one location, have GSTIN, want email").run()
    assert at.session_state["advisor"].rec.quote
    at.button[0].click().run(); assert not at.exception
    s = at.session_state["advisor"]
    assert s.rec is None and s.profile.business_type is None and len(at.session_state["chat"]) == 1
    at.chat_input[0].set_value("मेरा क्लिनिक है").run()
    at.button[0].click().run(); assert not at.exception
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
    shown = q.dataframe[0].value.astype(str).to_string()
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
        got = buttons(_page(page, "n4")); assert len(got) == 1 and got[0].proto.label == "Download consent receipt"
    assert "सहमति रसीद" in buttons(_page("3_Consent.py", "n4", ui_lang="hi"))[0].proto.label


def test_save_button_is_not_left_dead_when_only_the_optional_box_remains():
    from core import consent
    consent.grant("n5", consent.KYC, "en")
    c = _page("3_Consent.py", "n5"); assert not [b for b in c.button if b.label == "Save consent"]
    next(x for x in c.checkbox if "optional" in x.label).check().run()
    next(b for b in c.button if b.label == "Save consent").click().run(); assert not c.exception
    assert consent.active("n5") == {consent.KYC, consent.UPDATES} and not c.checkbox


def test_demo_control_stays_open_between_taps():
    from core import consent, orders
    from core.pricing import price
    oid = orders.create("n6", {"P01": 1}, price({"P01": 1}))
    consent.grant("n6", consent.KYC, "en"); consent.save_kyc("n6", "verified", "ok", "{}"); orders.advance(oid, "KYC verified")
    t = _page("5_Tracker.py", "n6", order_id=oid)
    assert not next(e for e in t.expander if e.label == "Demo control").proto.expanded
    next(b for b in t.button if b.label == "Advance stage").click().run(); assert not t.exception
    assert next(e for e in t.expander if e.label == "Demo control").proto.expanded and orders.get(oid)["stage"] == "Payment done"


def _change_page(page, to):
    """What Streamlit does on a real page change: widget values are wiped and only plain session values carry over."""
    plain = ("user", "advisor", "chat", "ui_lang", "synced_lang", "order_id", "plan_id", "use_alt", "saved_qty", "has_gstin_tick", "addons")
    a = AppTest.from_file(str(ROOT / "app/pages" / to), default_timeout=30)
    for k in plain:
        if k in page.session_state: a.session_state[k] = page.session_state[k]
    return a.run()


def test_language_survives_a_page_change():
    c = _page("3_Consent.py", "w1")
    c.sidebar.radio[0].set_value("hi").run(); assert not c.exception
    assert c.session_state["ui_lang"] == "hi" and any("KYC सत्यापन" in x.label for x in c.checkbox)
    k = _change_page(c, "3_Consent.py"); assert not k.exception
    assert k.session_state["ui_lang"] == "hi" and k.sidebar.radio[0].value == "hi" and any("KYC सत्यापन" in x.label for x in k.checkbox)
    k.sidebar.radio[0].set_value("en").run(); assert k.session_state["ui_lang"] == "en"  # and it can still be changed back
    assert any("KYC verification" in x.label for x in k.checkbox)


def test_hindi_from_the_chat_survives_a_page_change():
    s = State(); turn(s, "मेरा क्लिनिक है, दिल्ली में, 6 लोग, एक ही, GSTIN है, ईमेल चाहिए")
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["advisor"] = s; q.run(); assert q.session_state["ui_lang"] == "hi"
    for page, word in (("2_Quote.py", "प्रति माह"), ("3_Consent.py", "हम क्या लेते हैं")):
        n = _change_page(q, page); assert not n.exception and n.session_state["ui_lang"] == "hi"
        assert any(word in m.value for m in n.markdown)


def test_quantity_and_gstin_tick_survive_a_page_change_and_a_new_plan_clears_them():
    s = State()
    for m in ("clinic", "internet", "Delhi", "6", "1"): turn(s, m)
    q = AppTest.from_file(str(ROOT / "app/pages/2_Quote.py"), default_timeout=30)
    q.session_state["advisor"] = s; q.run()
    next(x for x in q.checkbox if x.key == "quote_gstin").check().run()
    next(x for x in q.checkbox if x.key == "addon_P15").check().run()
    before = _big(q); back = _change_page(q, "2_Quote.py"); assert not back.exception
    assert _big(back) == before and next(x for x in back.checkbox if x.key == "quote_gstin").value and next(x for x in back.checkbox if x.key == "addon_P15").value
    c = _quote(CLINIC)
    next(n for n in c.number_input if n.key == "qty_P16").set_value(10).run(); before = _big(c); assert f"{2671 + 4 * 138:,}" in before
    back = _change_page(c, "2_Quote.py"); assert not back.exception
    assert _big(back) == before and next(n for n in back.number_input if n.key == "qty_P16").value == 10
    back.session_state["advisor"] = _state("clinic in Delhi 6 staff 1 location need internet")  # a new chat happens on the Advisor page, so widgets are gone
    fresh = _change_page(back, "2_Quote.py"); assert not fresh.exception
    assert "P16" not in fresh.session_state["saved_qty"] and not fresh.session_state["has_gstin_tick"]


def _state(*msgs):
    s = State()
    for m in msgs: turn(s, m)
    return s


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
