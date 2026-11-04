"""Shared Streamlit helpers. Pages hold UI only; decisions live in core/."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import streamlit as st
from core.advisor import State

USER = "demo-user"
T = {
 "en": {"title": "Udyam Digital", "tag": "The right business plan, one clear monthly price, set up from your phone."},
 "hi": {"title": "उद्यम डिजिटल", "tag": "सही बिज़नेस प्लान, एक साफ़ मासिक कीमत, सब कुछ आपके फ़ोन से।"},
}
L = {
 "en": dict(advisor="Advisor", quote="Your quote", per_month="per month", setup="One-time setup", contract="Minimum contract", months="months", valid="Quote valid until", addons="Add-ons", no_plan="Chat with the advisor first to get a plan.", accept="Accept quote", accepted="Quote accepted. Next: consent.", needs="Added: {a}, because {b} needs it.", consent="Your consent", kyc="Verify your business", tracker="Track your order", no_order="No order yet. Accept a quote first."),
 "hi": dict(advisor="सलाहकार", quote="आपका कोटेशन", per_month="प्रति माह", setup="एकमुश्त सेटअप", contract="न्यूनतम अनुबंध", months="महीने", valid="कोटेशन मान्य है", addons="ऐड-ऑन", no_plan="प्लान के लिए पहले सलाहकार से बात करें।", accept="कोटेशन स्वीकार करें", accepted="कोटेशन स्वीकार। अगला चरण: सहमति।", needs="{a} जोड़ा गया, क्योंकि {b} के लिए ज़रूरी है।", consent="आपकी सहमति", kyc="बिज़नेस सत्यापन", tracker="ऑर्डर ट्रैक करें", no_order="अभी कोई ऑर्डर नहीं। पहले कोटेशन स्वीकार करें।"),
}


def setup(title: str):
    st.set_page_config(page_title=f"{title} · Accel Business", page_icon="📶", layout="centered")
    st.markdown("<style>.block-container{padding:1.2rem 1rem 4rem;max-width:720px}.big-price{font-size:2.6rem;font-weight:700;line-height:1.1}</style>", unsafe_allow_html=True)
    st.session_state.setdefault("advisor", State())
    st.session_state.setdefault("ui_lang", "en")
    st.session_state.setdefault("chat", [])
    st.sidebar.radio("Language / भाषा", ["en", "hi"], key="ui_lang", format_func=lambda x: {"en": "English", "hi": "हिन्दी"}[x])
    st.sidebar.caption("Demo. All data is synthetic. Accel Telecom is fictional.")
    return L[st.session_state.ui_lang]


def link(page: str, **kw):
    """st.page_link, tolerant of running a page as its own entrypoint (headless tests)."""
    from streamlit.errors import StreamlitPageNotFoundError
    try:
        st.page_link(page, **kw)
    except StreamlitPageNotFoundError:
        st.caption(kw.get("label", page))
