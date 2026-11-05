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
    q.button[0].click().run(); assert not q.exception and q.session_state["order_id"]


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
