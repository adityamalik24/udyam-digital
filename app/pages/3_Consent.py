import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent
t = c.setup("Consent")
st.subheader(t["consent"])
hi = st.session_state.ui_lang == "hi"
st.markdown("""
**हम क्या लेते हैं:** GST और Udyam प्रमाणपत्र, हस्ताक्षरकर्ता की ID, पते का प्रमाण।

**क्यों:** केवल आपके बिज़नेस के सत्यापन और कनेक्शन चालू करने के लिए।

**कितने समय तक:** मूल दस्तावेज़ सत्यापन के तुरंत बाद हटा दिए जाते हैं। निकाली गई जानकारी और परिणाम सेवा अवधि तक रखे जाते हैं।

**कौन देखता है:** केवल Accel Business की KYC टीम। ID नंबर छिपाकर (अंतिम 4 अंक) दिखते हैं। दस्तावेज़ किसी AI सेवा को नहीं भेजे जाते।
""" if hi else """
**What we collect:** GST and Udyam certificates, signatory ID, address proof.

**Why:** only to verify your business and activate your connection.

**How long:** original documents are deleted right after verification. Extracted details and the result are kept for the life of your service.

**Who sees it:** only the Accel Business KYC team. ID numbers show the last 4 digits only. Documents are never sent to an AI service.
""")
a = st.checkbox("KYC सत्यापन के लिए मेरे दस्तावेज़ों का उपयोग करें (ज़रूरी)" if hi else "Use my documents for KYC verification (required)", value=False)
b = st.checkbox("WhatsApp/SMS पर ऑर्डर अपडेट भेजें (वैकल्पिक)" if hi else "Send order updates on WhatsApp/SMS (optional)", value=False)
if st.button("सहमति सहेजें" if hi else "Save consent", type="primary", disabled=not a, use_container_width=True):
    lang = st.session_state.ui_lang
    have = consent.active(c.USER)
    if consent.KYC not in have: consent.grant(c.USER, consent.KYC, lang)
    if b and consent.UPDATES not in have: consent.grant(c.USER, consent.UPDATES, lang)
    st.success("Saved")
if consent.KYC in consent.active(c.USER):
    c.link("pages/4_KYC.py", label=t["kyc"], icon="🪪")
