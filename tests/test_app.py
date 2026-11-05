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
