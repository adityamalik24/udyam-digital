import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent, rights
t = c.setup("Your data")
lang = st.session_state.ui_lang
W = (lambda en, h: h if lang == "hi" else en)
st.subheader(W("Your data", "आपका डेटा"))
st.caption(W("Your rights under the Digital Personal Data Protection Act, 2023: see what we hold, ask us to correct it, or erase it.", "डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023 के तहत आपके अधिकार: देखें हमारे पास क्या है, उसे ठीक करवाएँ, या मिटवाएँ।"))
if st.session_state.pop("erased", None):
    st.success(W("Done. We've erased what we held, and this browser now starts fresh.", "हो गया। हमारे पास जो था वह मिटा दिया गया, और यह ब्राउज़र अब नए सिरे से शुरू होगा।"))

st.markdown(W("**Download everything we hold**", "**हमारे पास जो कुछ है, सब डाउनलोड करें**"))
st.download_button(W("Download my data (JSON)", "मेरा डेटा डाउनलोड करें (JSON)"), json.dumps(rights.export(c.user()), ensure_ascii=False, indent=2).encode("utf-8"), "accel_business_my_data.json", "application/json", use_container_width=True)
with st.expander(t["your_consent"], expanded=bool(consent.records(c.user()))): c.consent_panel(t)

st.markdown(W("**Ask us to correct something**", "**कुछ ठीक करवाना है?**"))
with st.form("correction", clear_on_submit=True):
    detail = st.text_area(W("What's wrong, and what should it say? Please don't type ID numbers.", "क्या ग़लत है, और सही क्या होना चाहिए? कृपया ID नंबर न लिखें।"), max_chars=500)
    if st.form_submit_button(W("Send request", "अनुरोध भेजें"), use_container_width=True):
        if rights.request_correction(c.user(), detail): st.error(W("Please say what to correct.", "कृपया बताएँ क्या ठीक करना है।"))
        else: st.success(W(f"Sent. We aim to reply within {rights.REPLY_DAYS} days.", f"भेज दिया। हम {rights.REPLY_DAYS} दिनों में जवाब देने की कोशिश करेंगे।"))

st.markdown(W("**Erase my data**", "**मेरा डेटा मिटाएँ**"))
st.caption(W("This deletes your KYC result, call-back details, requests and any unpaid order, and withdraws every consent. A paid order is kept while your service runs, because billing and the contract need it. Consent records stay, marked withdrawn, as proof of what you agreed.",
             "इससे आपका KYC परिणाम, कॉल-बैक जानकारी, अनुरोध और बिना भुगतान वाला ऑर्डर हट जाएगा, और हर सहमति वापस हो जाएगी। भुगतान किया गया ऑर्डर सेवा चलने तक रहेगा, क्योंकि बिलिंग और अनुबंध के लिए ज़रूरी है। सहमति रिकॉर्ड प्रमाण के तौर पर 'वापस ली गई' लिखकर रहेंगे।"))
sure = st.checkbox(W("I understand this can't be undone", "मैं समझता/समझती हूँ कि यह वापस नहीं हो सकता"), key="erase_sure")
if st.button(W("Erase my data", "मेरा डेटा मिटाएँ"), type="primary", disabled=not sure, use_container_width=True):
    rights.erase(c.user())
    keep = {"ui_lang": st.session_state.ui_lang}
    for k in list(st.session_state.keys()): del st.session_state[k]  # nothing of the old session may stay on screen
    st.session_state.update(keep, erased=True)
    st.rerun()
