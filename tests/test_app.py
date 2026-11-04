"""Headless smoke test of every page via Streamlit's AppTest."""
import os, sys, pathlib, tempfile
ROOT = pathlib.Path(__file__).parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import pytest
from streamlit.testing.v1 import AppTest
from core.advisor import State, turn

@pytest.mark.parametrize("page", ["Home.py", "pages/1_Advisor.py", "pages/2_Quote.py", "pages/3_Consent.py", "pages/4_KYC.py", "pages/5_Tracker.py"])
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
