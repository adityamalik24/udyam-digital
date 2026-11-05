import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core.advisor import State, turn, TXT
from core.rules import Profile
t = c.setup("Advisor")
st.subheader(t["advisor"])
s = st.session_state.advisor
if len(st.session_state.chat) > 1 and st.button({"en": "New chat", "hi": "नई चैट"}[st.session_state.ui_lang], icon="🔄"):
    # Clears the answers and the quote, keeps the language. An accepted order stays in the tracker.
    st.session_state.advisor = State(profile=Profile(language=s.profile.language))
    st.session_state.chat = []
    st.session_state.pop("addons", None)
    st.rerun()
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
from core import callback, consent
if len(st.session_state.chat) > 1:
    hi = st.session_state.ui_lang == "hi"
    text = (lambda en, h: h if hi else en)
    with st.expander(text("Talk to a person", "किसी व्यक्ति से बात करें"), expanded=bool(s.handoff)):
        if callback.has_request(c.user()):
            st.success(text("Thanks, your request is saved and our team will use it to contact you.", "धन्यवाद, आपका अनुरोध सेव हो गया है। हमारी टीम इसी से संपर्क करेगी।"))
            if st.button(text("Delete my contact details", "मेरी संपर्क जानकारी हटाएँ")):
                callback.delete(c.user()); st.rerun()
        else:
            st.write(text("Leave your details and our team can contact you, now or when we can serve you.", "अपनी जानकारी दें, हमारी टीम अभी या सेवा उपलब्ध होने पर आपसे संपर्क कर सकती है।"))
            with st.form("callback"):
                name = st.text_input(text("Your name (optional)", "आपका नाम (वैकल्पिक)"))
                phone = st.text_input(text("Mobile number", "मोबाइल नंबर"))
                email = st.text_input(text("Email", "ईमेल"))
                times = {"Any time": "कभी भी", "Morning": "सुबह", "Afternoon": "दोपहर", "Evening": "शाम"}
                best = st.selectbox(text("Best time to call", "कॉल का सही समय"), list(times), format_func=lambda x: times[x] if hi else x)
                note = st.text_area(text("Anything we should know? (optional)", "कुछ और बताना चाहें? (वैकल्पिक)"), max_chars=200)
                ok = st.checkbox(text(f"Accel Business may use these details only to contact me about this request. They are deleted after {callback.RETENTION_DAYS} days or when I remove them.", f"Accel Business इस जानकारी का उपयोग केवल इस अनुरोध के लिए मुझसे संपर्क करने में करे। यह {callback.RETENTION_DAYS} दिन बाद या मेरे हटाने पर मिटा दी जाएगी।"), value=False)
                sent = st.form_submit_button(text("Request a call back", "कॉल बैक का अनुरोध करें"), use_container_width=True)
            if sent:
                ph, em, err = callback.clean(phone, email)
                if err:
                    st.error({"missing": text("Please add a mobile number or an email.", "कृपया मोबाइल नंबर या ईमेल दें।"), "bad_phone": text("Please enter a valid 10-digit mobile number.", "कृपया सही 10 अंकों का मोबाइल नंबर दें।"), "bad_email": text("Please enter a valid email.", "कृपया सही ईमेल दें।")}[err])
                elif not ok:
                    st.error(text("Please tick the box so we're allowed to contact you.", "संपर्क की अनुमति के लिए कृपया बॉक्स पर टिक करें।"))
                else:
                    callback.save(c.user(), name, ph, em, best, note, s.profile.model_dump_json(), s.handoff or "customer_request", st.session_state.ui_lang)
                    st.rerun()
