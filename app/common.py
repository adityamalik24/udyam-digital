"""Shared Streamlit helpers. Pages hold UI only; decisions live in core/."""
import os, sys
from uuid import uuid4
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import streamlit as st
from core.advisor import State

T = {
 "en": {"title": "Udyam Digital", "tag": "The right business plan, one clear monthly price, set up from your phone."},
 "hi": {"title": "उद्यम डिजिटल", "tag": "सही बिज़नेस प्लान, एक साफ़ मासिक कीमत, सब कुछ आपके फ़ोन से।"},
}
L = {
 "en": dict(advisor="Advisor", quote="Your quote", per_month="per month", setup="One-time setup", contract="Minimum contract", months="months", valid="Quote valid until", addons="Add-ons", no_plan="Chat with the advisor first to get a plan.", accept="Accept quote", accepted="Quote accepted. Next: consent.", needs="Added: {a}, because {b} needs it.", consent="Your consent", kyc="Verify your business", tracker="Track your order", no_order="No order yet. Accept a quote first.", first_consent="Please give consent first.", docs="Documents", specimen="Use a specimen applicant (K01 to K12)", upload="Upload my own", applicant="Applicant", verify="Verify", reading="Reading documents...", pay="Pay first month and setup (mock)", paid="Mock payment recorded. No money moved.", stored="Stored (masked)", kyc_note="Documents were read in memory and not stored. Checked as of 15 Jul 2026.", verdicts={"verified": "Verified", "needs_review": "Needs review", "rejected": "Rejected"}, doc_gst="GST certificate", doc_udyam="Udyam certificate", doc_id="Signatory ID", doc_bill="Address proof (under 90 days old)", next="Next expected (estimate)", tech="Technician", resched="Reschedule installation", new_date="New date", resched_btn="Reschedule", demo="Demo control", demo_note="Moves the order one stage forward, for demo only.", advance="Advance stage", your_consent="Your consent", withdraw="Withdraw", granted="granted", withdrawn="withdrawn", hold="On hold: this order moves forward once KYC is verified.", stages=None),
 "hi": dict(advisor="सलाहकार", quote="आपका कोटेशन", per_month="प्रति माह", setup="एकमुश्त सेटअप", contract="न्यूनतम अनुबंध", months="महीने", valid="कोटेशन मान्य है", addons="ऐड-ऑन", no_plan="प्लान के लिए पहले सलाहकार से बात करें।", accept="कोटेशन स्वीकार करें", accepted="कोटेशन स्वीकार। अगला चरण: सहमति।", needs="{a} जोड़ा गया, क्योंकि {b} के लिए ज़रूरी है।", consent="आपकी सहमति", kyc="बिज़नेस सत्यापन", tracker="ऑर्डर ट्रैक करें", no_order="अभी कोई ऑर्डर नहीं। पहले कोटेशन स्वीकार करें।", first_consent="कृपया पहले सहमति दें।", docs="दस्तावेज़", specimen="नमूना आवेदक चुनें (K01 से K12)", upload="अपने दस्तावेज़ अपलोड करें", applicant="आवेदक", verify="सत्यापित करें", reading="दस्तावेज़ पढ़े जा रहे हैं...", pay="पहले महीने और सेटअप का भुगतान (डेमो)", paid="डेमो भुगतान दर्ज हुआ। कोई पैसा नहीं कटा।", stored="सहेजा गया (छिपाकर)", kyc_note="दस्तावेज़ केवल मेमोरी में पढ़े गए, सहेजे नहीं गए। जाँच की तारीख 15 जुलाई 2026।", verdicts={"verified": "सत्यापित", "needs_review": "जाँच ज़रूरी", "rejected": "अस्वीकृत"}, doc_gst="GST प्रमाणपत्र", doc_udyam="Udyam प्रमाणपत्र", doc_id="हस्ताक्षरकर्ता की ID", doc_bill="पते का प्रमाण (90 दिन से कम पुराना)", next="अगली अनुमानित तारीख", tech="तकनीशियन", resched="इंस्टॉलेशन की तारीख बदलें", new_date="नई तारीख", resched_btn="तारीख बदलें", demo="डेमो कंट्रोल", demo_note="ऑर्डर को एक चरण आगे बढ़ाता है, केवल डेमो के लिए।", advance="अगला चरण", your_consent="आपकी सहमति", withdraw="वापस लें", granted="दी गई", withdrawn="वापस ली गई", hold="रुका हुआ: KYC सत्यापित होने पर ऑर्डर आगे बढ़ेगा।", stages=["कोटेशन स्वीकार", "KYC सत्यापित", "भुगतान पूरा", "इंस्टॉलेशन तय", "तकनीशियन तय", "इंस्टॉल पूरा", "सक्रिय"]),
}


def setup(title: str):
    st.set_page_config(page_title=f"{title} · Accel Business", page_icon="📶", layout="centered")
    st.markdown("<style>.block-container{padding:1.2rem 1rem 4rem;max-width:720px}.big-price{font-size:2.6rem;font-weight:700;line-height:1.1}</style>", unsafe_allow_html=True)
    st.session_state.setdefault("advisor", State())
    # A chat that began before a deploy can miss newer fields: start it fresh instead of crashing.
    if any(not hasattr(st.session_state.advisor, f) for f in State.__dataclass_fields__):
        st.session_state.advisor, st.session_state.chat = State(), []
    st.session_state.setdefault("ui_lang", "en")
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("synced_lang", "en")
    # Follow the language of the chat on every page; the sidebar can still override it afterwards.
    chat_lang = st.session_state.advisor.profile.language
    if chat_lang in L and chat_lang != st.session_state.synced_lang:
        st.session_state.synced_lang = st.session_state.ui_lang = chat_lang
    st.sidebar.radio("Language / भाषा", ["en", "hi"], key="ui_lang", format_func=lambda x: {"en": "English", "hi": "हिन्दी"}[x])
    st.sidebar.caption("Demo. All data is synthetic. Accel Telecom is fictional.")
    return L[st.session_state.ui_lang]


def user() -> str:
    """One demo identity per browser session, so judges testing at once never see each other's orders or consent."""
    return st.session_state.setdefault("user", f"demo-{uuid4().hex[:8]}")


def link(page: str, **kw):
    """st.page_link, tolerant of running a page as its own entrypoint (headless tests)."""
    from streamlit.errors import StreamlitPageNotFoundError
    try:
        st.page_link(page, **kw)
    except StreamlitPageNotFoundError:
        st.caption(kw.get("label", page))
