import common as c
import streamlit as st
t = c.setup("Home")
lang = st.session_state.ui_lang
st.title(c.T[lang]["title"])
st.write(c.T[lang]["tag"])
steps = {"en": ["Tell the advisor about your business", "Review one clear monthly price", "Give consent and verify documents", "Track installation without calling support"],
         "hi": ["सलाहकार को अपने बिज़नेस के बारे में बताएँ", "एक साफ़ मासिक कीमत देखें", "सहमति दें और दस्तावेज़ सत्यापित करें", "बिना कॉल किए इंस्टॉलेशन ट्रैक करें"]}[lang]
for i, s in enumerate(steps, 1): st.markdown(f"**{i}.** {s}")
st.page_link("pages/1_Advisor.py", label=t["advisor"], icon="💬")
