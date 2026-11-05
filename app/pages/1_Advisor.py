import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core.advisor import turn, TXT
t = c.setup("Advisor")
st.subheader(t["advisor"])
s = st.session_state.advisor
if not st.session_state.chat:
    welcome = {"en": TXT["welcome"]["en"] + " " + "What kind of business do you run?",
               "hi": "नमस्ते! मैं आपका Accel Business सलाहकार हूँ। आपका बिज़नेस किस तरह का है?"}[st.session_state.ui_lang]
    st.session_state.chat.append(("assistant", welcome))
    if st.session_state.ui_lang == "hi": s.profile.language = "hi"
for role, msg in st.session_state.chat:
    with st.chat_message(role): st.markdown(msg)
if prompt := st.chat_input("Type here / यहाँ लिखें"):
    with st.spinner("..."):
        reply = turn(s, prompt)
    # Only the redacted form of what the user typed is kept, so identifiers vanish from the transcript too.
    if getattr(s, "restarted", False):  # a session from before a deploy may not have this field
        st.session_state.chat = [("assistant", reply)]
        st.session_state.pop("addons", None)
    else:
        st.session_state.chat += [("user", s.history[-2][1]), ("assistant", reply)]
    st.rerun()
from core import llm
if llm.last_error: st.caption("AI wording is unavailable right now, so replies use standard text. Plans and prices are unaffected.")
if s.rec and s.rec.quote:
    c.link("pages/2_Quote.py", label=t["quote"], icon="🧾")
