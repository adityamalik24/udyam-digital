import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core.advisor import State, TXT, from_form, quick_replies, turn
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
if len(st.session_state.chat) > 1 and st.session_state.chat[-1][0] == "assistant":
    c.read_aloud(st.session_state.chat[-1][1], "सुनें" if st.session_state.ui_lang == "hi" else "Read aloud")


def track() -> None:
    """Funnel steps for the dashboard: a random id and a step name, never what was typed."""
    c.event("chat_started")
    if s.rec and s.rec.quote: c.event("plan_shown")
    if s.handoff: c.event("handoff", code=s.handoff)
hi_ui = st.session_state.ui_lang == "hi"
chips = quick_replies(s)
tapped = st.pills("जल्दी जवाब" if hi_ui else "Quick answers", [label for label, _ in chips], key=f"chip_{len(st.session_state.chat)}", label_visibility="collapsed") if chips else None
with st.expander("AI और आपकी चैट" if hi_ui else "AI and your chat"):
    st.caption("चैट पढ़ने और जवाब के शब्द लिखने के लिए हम Google Gemini का उपयोग करते हैं। यह भारत के बाहर प्रोसेस हो सकता है, और Google इसे अपने उत्पाद सुधारने में उपयोग कर सकता है। भेजने से पहले हम ID नंबर और संपर्क जानकारी हटा देते हैं, फिर भी कृपया इन्हें न लिखें। प्रोडक्ट और कीमत हमेशा हमारा कोड तय करता है।" if hi_ui else
               "We use Google Gemini to read the chat and word replies. It may process text outside India, and Google may use it to improve its products. We remove ID numbers and contact details before sending, but please don't type them. Our code always decides products and prices.")
    s.no_ai = not st.toggle("AI को मेरी चैट पढ़ने दें" if hi_ui else "Let AI read my chat", value=not getattr(s, "no_ai", False), key="ai_toggle", help="बंद करने पर भी सलाहकार काम करता रहेगा।" if hi_ui else "The advisor still works with this off.")
if not (s.rec and s.rec.quote) and not s.handoff:  # for owners who'd rather not chat, and it needs no AI
    say = (lambda en, h: h if hi_ui else en)
    with st.expander(say("Prefer a short form?", "छोटा फ़ॉर्म भरना चाहेंगे?")):
        with st.form("short_form"):
            KINDS = {"kirana": say("Kirana store", "किराना"), "retailer": say("Other shop", "अन्य दुकान"), "salon": say("Salon", "सैलून"), "pharmacy": say("Pharmacy", "फ़ार्मेसी"), "clinic": say("Clinic", "क्लिनिक"), "ca_firm": say("CA firm", "सीए फर्म"), "office": say("Other office", "अन्य ऑफिस"), "coaching": say("Coaching centre", "कोचिंग"), "restaurant": say("Restaurant or cafe", "रेस्टोरेंट"), "manufacturer": say("Factory or workshop", "फैक्ट्री या वर्कशॉप"), "other": say("Something else", "कुछ और")}
            NEED_LABELS = {"internet": say("Internet", "इंटरनेट"), "internet_for_upi_pos": say("Internet for UPI or card payments", "UPI या कार्ड के लिए इंटरनेट"), "uptime": say("Backup if the internet drops", "इंटरनेट बंद होने पर बैकअप"), "pos_billing": say("Billing", "बिलिंग"), "cloud_email": say("Business email", "बिज़नेस ईमेल"), "security": say("Device security", "डिवाइस सुरक्षा"), "cctv": say("CCTV", "सीसीटीवी"), "wifi": say("Wi-Fi for customers", "ग्राहकों के लिए वाई-फ़ाई"), "customer_messaging": say("WhatsApp for customers", "ग्राहकों के लिए WhatsApp"), "website": say("Website", "वेबसाइट"), "mobile_line": say("Mobile lines", "मोबाइल लाइन"), "dedicated_bandwidth": say("Leased line", "लीज़्ड लाइन")}
            f_kind = st.selectbox(say("Your business", "आपका बिज़नेस"), list(KINDS), format_func=KINDS.get)
            f_city = st.text_input(say("City", "शहर"))
            f_tier = st.selectbox(say("If your city isn't a big one, what size is it?", "शहर छोटा हो तो उसका आकार?"), [0, 1, 2, 3], format_func=lambda x: {0: say("Not needed", "ज़रूरत नहीं"), 1: say("Metro", "मेट्रो"), 2: say("Large city", "बड़ा शहर"), 3: say("Smaller town", "छोटा शहर")}[x])
            f_staff = st.number_input(say("People working there", "काम करने वाले लोग"), 1, 100000, 1)
            f_sites = st.number_input(say("Locations", "लोकेशन"), 1, 10000, 1)
            f_gst = st.selectbox(say("GSTIN", "GSTIN"), ["unsure", "yes", "no"], format_func=lambda x: {"unsure": say("Not sure", "पता नहीं"), "yes": say("Yes, active", "हाँ, सक्रिय"), "no": say("No", "नहीं")}[x])
            f_needs = st.multiselect(say("What do you need?", "आपको क्या चाहिए?"), list(NEED_LABELS), format_func=NEED_LABELS.get)
            f_fibre = st.checkbox(say("Fibre doesn't reach my site", "मेरी जगह फाइबर नहीं पहुँचता"))
            if st.form_submit_button(say("Show my plan", "मेरा प्लान दिखाएँ"), use_container_width=True):
                if not f_city.strip(): st.error(say("Please add your city.", "कृपया अपना शहर लिखें।"))
                else:
                    reply = from_form(s, f_kind, f_city, f_tier or None, int(f_staff), int(f_sites), {"unsure": None, "yes": True, "no": False}[f_gst], f_needs, f_fibre)
                    st.session_state.chat += [("user", say("Filled in the short form", "छोटा फ़ॉर्म भरा")), ("assistant", reply)]
                    track(); st.rerun()
typed = st.chat_input("Type here / यहाँ लिखें")
if prompt := typed or dict(chips).get(tapped):
    with st.spinner("..."):
        reply = turn(s, prompt)
    # Only the redacted form of what the user typed is kept, so identifiers vanish from the transcript too.
    if getattr(s, "restarted", False):  # a session from before a deploy may not have this field
        st.session_state.chat = [("assistant", reply)]
        st.session_state.pop("addons", None)
    else:
        st.session_state.chat += [("user", s.history[-2][1]), ("assistant", reply)]
    track(); st.rerun()
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
