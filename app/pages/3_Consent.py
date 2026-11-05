import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent
t = c.setup("Consent")
c.journey("consent", t)
st.subheader(t["consent"])
lang = st.session_state.ui_lang
hi = lang == "hi"
W = (lambda en, h: h if hi else en)
st.markdown(consent.NOTICE_SHORT[lang])
with st.expander(t["read_notice"]): st.markdown(consent.NOTICE[lang])
st.markdown(f"**{t['keep_ready']}**")
st.markdown("\n".join(f"- **{name}:** {why}" for name, why in (d[lang] for d in consent.DOCS_NEEDED.values())))
st.caption(consent.DOCS_TIP[lang])
active = consent.active(c.user())
kyc_ok, updates_ok = consent.KYC in active, consent.UPDATES in active
a = b = False
if kyc_ok: st.success(W("KYC consent is given.", "KYC सहमति दी गई है।"))
else:
    a = st.checkbox(W("Use my documents for KYC verification (required)", "KYC सत्यापन के लिए मेरे दस्तावेज़ों का उपयोग करें (ज़रूरी)"), value=False, key="consent_kyc")
    st.caption(W("If you say no: we can't check your documents, so we can't activate your connection.", "अगर आप मना करते हैं: हम आपके दस्तावेज़ नहीं जाँच पाएँगे, इसलिए आपका कनेक्शन चालू नहीं हो पाएगा।"))
if updates_ok: st.success(W("Order updates consent is given.", "ऑर्डर अपडेट की सहमति दी गई है।"))
else:
    b = st.checkbox(W("Send order updates on WhatsApp/SMS (optional)", "WhatsApp/SMS पर ऑर्डर अपडेट भेजें (वैकल्पिक)"), value=False, key="consent_updates")
    st.caption(W("If you say no: nothing else changes, and you can still check your order in the tracker. In this demo no messages are sent.", "अगर आप मना करते हैं: और कुछ नहीं बदलेगा, आप ट्रैकर में अपना ऑर्डर देख सकते हैं। इस डेमो में कोई मैसेज नहीं भेजा जाता।"))
if not (kyc_ok and updates_ok):
    ready = (kyc_ok or a) and (a or b)
    if not kyc_ok and not a: st.caption(W("Tick KYC verification to continue.", "आगे बढ़ने के लिए KYC सत्यापन पर टिक करें।"))
    if (not kyc_ok or b) and st.button(W("Save consent", "सहमति सहेजें"), type="primary", disabled=not ready, use_container_width=True):  # no dead button once only the optional box is left
        if a: consent.grant(c.user(), consent.KYC, lang)
        if b: consent.grant(c.user(), consent.UPDATES, lang)
        st.rerun()
if consent.records(c.user()):
    with st.expander(t["your_consent"]): c.consent_panel(t)
if consent.KYC in consent.active(c.user()):
    c.link("pages/4_KYC.py", label=t["kyc"], icon="🪪")
