"""What each screen shows, already worked out and worded. The page only draws it, so every rule stays in core/."""
from __future__ import annotations
import json
from core import asr, callback, consent, contacts, db, events, insights, journey as J, llm, orders, reviews, rights
from core.advisor import TXT, quick_replies, trade_text, why_text
from core.catalogue import catalogue
from core.kyc import forensics, messages as KM
from core.kyc.pipeline import DATA as KYC_DATA, FILES, MAX_PAGES, MAX_UPLOAD_MB, SPECIMEN_REVIEW
from core.kyc.validators import mask
from core.labels import L, T
from core.pricing import TODAY, contract_total, first_payment, price
from core.rules import ADJUSTABLE_UNITS, MAX_QTY, apply_addons, eligible, reason_text, remove_with_dependents
from .session import Session

ADDONS = ["P09", "P22", "P23", "P20", "P16", "P17", "P15", "P14", "P19", "P18", "P07", "P11"]
day = lambda d: d.strftime("%d %b %Y")


def event(s: Session, kind: str, code: str | None = None, variant: str | None = None) -> None:
    """A funnel step for the dashboard. Never breaks a request."""
    try:
        events.log(s.fid, kind, variant=variant, code=code)
    except Exception:
        pass


def track_chat(s: Session) -> None:
    event(s, "chat_started")
    if s.advisor.rec and s.advisor.rec.quote: event(s, "plan_shown")
    if s.advisor.handoff: event(s, "handoff", code=s.advisor.handoff)


def segment(s: Session) -> str | None:
    return insights.segment_of(s.advisor.profile.business_type, s.advisor.profile.locations)


def say(s: Session):
    return (lambda en, hi: hi if s.ui_lang == "hi" else en)


def link_label(s: Session) -> dict:
    t = L[s.ui_lang]
    return dict(advisor=t["advisor"], quote=t["quote"], consent=t["consent"], kyc=t["kyc"], tracker=t["tracker"])


def sync_language(s: Session) -> None:
    """Pages follow the chat's language, until the header switch overrides it."""
    chat = s.advisor.profile.language
    if chat in L and chat != s.synced_lang:
        s.synced_lang = s.ui_lang = chat


def verdict_of(s: Session) -> str | None:
    last = consent.latest_kyc(s.user)
    return last["verdict"] if last else None


def known_order(s: Session) -> None:
    if s.order_id and not orders.get(s.order_id):  # the database restarted under this session
        s.order_id, s.accepted_items = None, None


def chrome(s: Session, page: str | None = None) -> dict:
    """The header and the Quote-to-tracking progress, from stored records so it can't overstate where the owner is."""
    sync_language(s); known_order(s)
    W, t = say(s), L[s.ui_lang]
    oid = s.order_id or orders.latest(s.user)
    state = J.progress(orders.get(oid) if oid else None, consent.KYC in consent.active(s.user), verdict_of(s))
    now = J.current(page, state) if page else None
    steps = [{"key": k, "label": t["steps"][k], "state": state[k], "state_label": t["step_state"][state[k]], "now": k == now, "n": i} for i, k in enumerate(J.STEPS, 1)]
    return {"lang": s.ui_lang, "journey": steps if page in J.STEPS or page == "tracker" else None,
            "nav": {"title": W("Accel Business", "Accel Business"), "data": W("Your data", "आपका डेटा"), "skip": W("Skip to content", "मुख्य भाग पर जाएँ"),
                    "banner": W("Demo. All data is synthetic. Accel Telecom is fictional.", "डेमो। सारा डेटा काल्पनिक है। Accel Telecom काल्पनिक है।"), "language": W("Language", "भाषा"), "error": W("Something went wrong. Please try again.", "कुछ गड़बड़ हुई। कृपया दोबारा कोशिश करें।"),
                    "offline": W("We can't reach the server. Check your connection and try again.", "सर्वर से संपर्क नहीं हो पाया। अपना कनेक्शन जाँचकर दोबारा कोशिश करें।"),
                    "slow": W("This is taking too long. Please try again.", "इसमें बहुत समय लग रहा है। कृपया दोबारा कोशिश करें।"), "new_chat": W("New chat", "नई चैट"), "switch": W("Staff view", "स्टाफ़ व्यू"), "switch_to": "/partner",
                    "new_confirm": W("Start a new chat? Your answers and current quote will be cleared. Orders you've accepted stay in your tracker.", "नई चैट शुरू करें? आपके जवाब और मौजूदा कोटेशन हट जाएँगे। स्वीकार किए गए ऑर्डर ट्रैकर में रहेंगे।"), **link_label(s)}}


def home(s: Session) -> dict:
    W = say(s)
    known_order(s)
    oid = s.order_id or orders.latest(s.user)
    resume = None
    if oid: resume = {"to": "/tracker", "label": L[s.ui_lang]["tracker"]}
    elif s.advisor.rec and s.advisor.rec.quote: resume = {"to": "/quote", "label": W("Back to your quote", "अपने कोटेशन पर वापस जाएँ")}
    return {**chrome(s), "title": T[s.ui_lang]["title"], "tag": T[s.ui_lang]["tag"], "resume": resume, "start": W("Start with the advisor", "सलाहकार से शुरू करें"), "form": W("Use the short form", "छोटा फ़ॉर्म भरें"),
            "voice": W("Type or speak, in your language.", "अपनी भाषा में लिखें या बोलें।"),
            "points": [{"icon": "chat", "text": W("Tell the advisor about your business", "सलाहकार को अपने बिज़नेस के बारे में बताएँ")}, {"icon": "price", "text": W("Review one clear monthly price", "एक साफ़ मासिक कीमत देखें")},
                       {"icon": "shield", "text": W("Give consent and verify documents", "सहमति दें और दस्तावेज़ सत्यापित करें")}, {"icon": "pin", "text": W("Track installation without calling support", "बिना कॉल किए इंस्टॉलेशन ट्रैक करें")}]}


def voice(s: Session) -> dict:
    W = say(s)
    return {"available": asr.available(bool(s.advisor.no_ai)), "consented": consent.VOICE in consent.active(s.user), "notice": consent.VOICE_NOTICE[s.ui_lang],
            "agree": W("Let Google Gemini write down what I say", "Google Gemini को मेरी बात लिखने दें"), "turn_on": W("Turn on voice", "आवाज़ चालू करें"), "cancel": W("Not now", "अभी नहीं"), "title": W("Speak instead of typing?", "लिखने की जगह बोलना चाहेंगे?"),
            "mic": W("Speak", "बोलें"), "stop": W("Stop recording", "रिकॉर्डिंग रोकें"), "listening": W("Listening… speak in any language", "सुन रहे हैं… किसी भी भाषा में बोलें"), "working": W("Writing down what you said…", "आपकी बात लिखी जा रही है…"),
            "check": W("Please check the words, fix anything wrong, then send.", "कृपया शब्द जाँच लें, ग़लती ठीक करें, फिर भेजें।"), "removed": W("We removed an ID or contact number from what you said.", "आपकी बात से ID या संपर्क नंबर हटा दिया गया।"),
            "denied": W("Microphone access is blocked. Please allow it in your browser, or type instead.", "माइक्रोफ़ोन की अनुमति नहीं है। कृपया ब्राउज़र में अनुमति दें, या लिखकर बताएँ।"),
            "unsupported": W("This browser can't record here. Please type instead.", "यह ब्राउज़र यहाँ रिकॉर्ड नहीं कर सकता। कृपया लिखकर बताएँ।"),
            "problems": {"nothing_heard": W("We couldn't hear any words. Please try again, or type.", "कोई शब्द सुनाई नहीं दिया। कृपया दोबारा कोशिश करें, या लिखें।"), "too_short": W("That was too short. Please hold on and speak a little longer.", "यह बहुत छोटा था। कृपया थोड़ा और बोलें।"),
                         "too_long": W("Please keep it under a minute.", "कृपया एक मिनट से कम बोलें।"), "bad_audio": W("We couldn't read that recording. Please try again, or type.", "यह रिकॉर्डिंग पढ़ी नहीं जा सकी। कृपया दोबारा कोशिश करें, या लिखें।"),
                         "unavailable": W("Voice isn't available right now. Please type instead.", "आवाज़ अभी उपलब्ध नहीं है। कृपया लिखकर बताएँ।"), "busy": W("Too many recordings just now. Please wait a minute, or type.", "अभी बहुत रिकॉर्डिंग हो गईं। कृपया एक मिनट रुकें, या लिखें।")},
            "off_note": W("Voice needs AI, which is off for this chat.", "आवाज़ के लिए AI चाहिए, जो इस चैट में बंद है।"), "ai_off": bool(s.advisor.no_ai)}


KIND_KEYS = ("kirana", "retailer", "salon", "pharmacy", "clinic", "ca_firm", "office", "coaching", "restaurant", "manufacturer", "other")
NEED_KEYS = ("internet", "internet_for_upi_pos", "uptime", "pos_billing", "cloud_email", "security", "cctv", "wifi", "customer_messaging", "website", "mobile_line", "dedicated_bandwidth")


def short_form(s: Session) -> dict:
    W = say(s)
    kinds = dict(zip(KIND_KEYS, [W("Kirana store", "किराना"), W("Other shop", "अन्य दुकान"), W("Salon", "सैलून"), W("Pharmacy", "फ़ार्मेसी"), W("Clinic", "क्लिनिक"), W("CA firm", "सीए फर्म"), W("Other office", "अन्य ऑफिस"), W("Coaching centre", "कोचिंग"), W("Restaurant or cafe", "रेस्टोरेंट"), W("Factory or workshop", "फैक्ट्री या वर्कशॉप"), W("Something else", "कुछ और")]))
    needs = dict(zip(NEED_KEYS, [W("Internet", "इंटरनेट"), W("Internet for UPI or card payments", "UPI या कार्ड के लिए इंटरनेट"), W("Backup if the internet drops", "इंटरनेट बंद होने पर बैकअप"), W("Billing", "बिलिंग"), W("Business email", "बिज़नेस ईमेल"), W("Device security", "डिवाइस सुरक्षा"), W("CCTV", "सीसीटीवी"), W("Wi-Fi for customers", "ग्राहकों के लिए वाई-फ़ाई"), W("WhatsApp for customers", "ग्राहकों के लिए WhatsApp"), W("Website", "वेबसाइट"), W("Mobile lines", "मोबाइल लाइन"), W("Leased line", "लीज़्ड लाइन")]))
    return {"title": W("Prefer a short form?", "छोटा फ़ॉर्म भरना चाहेंगे?"), "kinds": kinds, "needs": needs, "kind": W("Your business", "आपका बिज़नेस"), "city": W("City", "शहर"), "tier": W("If your city isn't a big one, what size is it?", "शहर छोटा हो तो उसका आकार?"),
            "tiers": {"0": W("Not needed", "ज़रूरत नहीं"), "1": W("Metro", "मेट्रो"), "2": W("Large city", "बड़ा शहर"), "3": W("Smaller town", "छोटा शहर")}, "staff": W("People working there", "काम करने वाले लोग"), "sites": W("Locations", "लोकेशन"), "gst": "GSTIN",
            "gsts": {"unsure": W("Not sure", "पता नहीं"), "yes": W("Yes, active", "हाँ, सक्रिय"), "no": W("No", "नहीं")}, "need": W("What do you need?", "आपको क्या चाहिए?"), "fibre": W("Fibre doesn't reach my site", "मेरी जगह फाइबर नहीं पहुँचता"), "submit": W("Show my plan", "मेरा प्लान दिखाएँ"), "city_missing": W("Please add your city.", "कृपया अपना शहर लिखें।")}


def callback_view(s: Session) -> dict:
    W = say(s)
    saved = contacts.get(s.user)
    return {"prefill": {"name": saved["name"], "phone": saved["phone"]} if saved else None, "title": W("Talk to a person", "किसी व्यक्ति से बात करें"), "alert": bool(s.advisor.handoff), "close": W("Close", "बंद करें"), "sent": callback.has_request(s.user), "saved": W("Thanks, your request is saved and our team will use it to contact you.", "धन्यवाद, आपका अनुरोध सेव हो गया है। हमारी टीम इसी से संपर्क करेगी।"), "delete": W("Delete my contact details", "मेरी संपर्क जानकारी हटाएँ"),
            "intro": W("Leave your details and our team can contact you, now or when we can serve you.", "अपनी जानकारी दें, हमारी टीम अभी या सेवा उपलब्ध होने पर आपसे संपर्क कर सकती है।"), "name": W("Your name (optional)", "आपका नाम (वैकल्पिक)"), "phone": W("Mobile number", "मोबाइल नंबर"), "email": W("Email", "ईमेल"),
            "best": W("Best time to call", "कॉल का सही समय"), "times": {"Any time": W("Any time", "कभी भी"), "Morning": W("Morning", "सुबह"), "Afternoon": W("Afternoon", "दोपहर"), "Evening": W("Evening", "शाम")}, "note": W("Anything we should know? (optional)", "कुछ और बताना चाहें? (वैकल्पिक)"),
            "agree": W(f"Accel Business may use these details only to contact me about this request. They are deleted after {callback.RETENTION_DAYS} days or when I remove them.", f"Accel Business इस जानकारी का उपयोग केवल इस अनुरोध के लिए मुझसे संपर्क करने में करे। यह {callback.RETENTION_DAYS} दिन बाद या मेरे हटाने पर मिटा दी जाएगी।"), "submit": W("Request a call back", "कॉल बैक का अनुरोध करें")}


CALLBACK_ERRORS = {"missing": ("Please add a mobile number or an email.", "कृपया मोबाइल नंबर या ईमेल दें।"), "bad_phone": ("Please enter a valid 10-digit mobile number.", "कृपया सही 10 अंकों का मोबाइल नंबर दें।"), "bad_email": ("Please enter a valid email.", "कृपया सही ईमेल दें।"), "no_agree": ("Please tick the box so we're allowed to contact you.", "संपर्क की अनुमति के लिए कृपया बॉक्स पर टिक करें।")}


WELCOME = {"en": TXT["welcome"]["en"] + " What kind of business do you run?", "hi": "नमस्ते! मैं आपका Accel Business सलाहकार हूँ। आपका बिज़नेस किस तरह का है?"}
TRANSLATE_LATEST = 8  # older replies keep their language: translation spends free AI quota
RETRY_TRANSLATION_SECONDS = 60  # when the model was busy, not when a translation failed the check


def ensure_welcome(s: Session) -> None:
    if not s.chat:
        s.chat.append({"role": "assistant", "welcome": True})
        if s.ui_lang == "hi": s.advisor.profile.language = "hi"


def add_turn(s: Session, user_text: str, reply: str) -> None:
    """Keeps the language each reply was written in, so a language switch knows what to translate."""
    a = s.advisor
    s.chat += [{"role": "user", "text": user_text}, {"role": "assistant", "text": reply, "lang": a.reply_lang or a.profile.language}]


def _can_translate(s: Session) -> bool:
    return asr.available(bool(s.advisor.no_ai))


def _to_translate(s: Session) -> list[int]:
    """Replies not in the page's language and not tried yet, newest first, at most TRANSLATE_LATEST."""
    target = s.ui_lang
    # Only what was on screen at the switch: replies after it are in the language the owner chose to write in.
    import time
    def open_(i):
        got = s.tr.get((i, target), "missing")
        return got == "missing" or (isinstance(got, tuple) and got[0] == "busy" and time.time() - got[1] > RETRY_TRANSLATION_SECONDS)
    todo = [i for i, m in enumerate(s.chat[:s.switched_before]) if m["role"] == "assistant" and not m.get("welcome") and m.get("lang") != target and open_(i)]
    return todo[::-1][:TRANSLATE_LATEST]


def translate_chat(s: Session) -> None:
    """Translates earlier replies into the page's language. Numbers and product names are swapped for slots first and put back
    after, so a translation can't change a price; anything that fails the check keeps its original words."""
    from core.advisor import translate_reply
    llm.ai_off.set(bool(s.advisor.no_ai))
    import time
    for i in _to_translate(s):
        text, how = translate_reply(s.chat[i]["text"], s.ui_lang)
        s.tr[(i, s.ui_lang)] = text if how == "ok" else ("busy", time.time()) if how == "unavailable" else None
        if how == "unavailable": break  # the model is busy or out of quota: the rest can wait too


def chat_view(s: Session) -> dict:
    ensure_welcome(s)
    W, target, msgs, kept = say(s), s.ui_lang, [], False
    can = _can_translate(s)
    waiting = set(_to_translate(s)) if can else set()
    for i, m in enumerate(s.chat):
        if m.get("welcome"): msgs.append({"role": "assistant", "text": WELCOME[target]}); continue
        text = m["text"]
        if m["role"] == "assistant" and m.get("lang") != target and i < s.switched_before:
            done = s.tr.get((i, target))
            if isinstance(done, str): text = done
            elif i not in waiting: kept = True
        msgs.append({"role": m["role"], "text": text, "translating": i in waiting})
    return {"messages": msgs, "translate": bool(waiting), "translating": W("Translating…", "अनुवाद हो रहा है…"),
            "kept": W("Some earlier replies stay in the language they were written in.", "कुछ पुराने जवाब उसी भाषा में हैं जिसमें वे लिखे गए थे।") if kept else None}


def advisor(s: Session) -> dict:
    W = say(s)
    chat = chat_view(s)
    a = s.advisor
    has_plan = bool(a.rec and a.rec.quote)
    return {**chrome(s), "title": L[s.ui_lang]["advisor"], "chat": chat["messages"], "translate": chat["translate"], "translating": chat["translating"], "kept": chat["kept"], "chips": [label for label, _ in quick_replies(a)],
            "placeholder": W("Type or tap the mic", "लिखें या माइक दबाएँ"), "listen": W("Read aloud", "सुनें"), "stop_listen": W("Stop reading", "पढ़ना रोकें"), "send": W("Send", "भेजें"), "typing": W("Thinking…", "सोच रहे हैं…"),
            "has_plan": has_plan, "see_quote": W("See my quote", "मेरा कोटेशन देखें"), "fallback": W("AI wording is unavailable right now, so replies use standard text. Plans and prices are unaffected.", "AI अभी उपलब्ध नहीं है, इसलिए जवाब सामान्य शब्दों में हैं। प्लान और कीमतों पर कोई असर नहीं।") if llm.last_error else None,
            "ai_line": ai_line(s),
            "form": short_form(s) if not has_plan and not a.handoff else None, "callback": callback_view(s), "voice": voice(s)}


def ai_line(s: Session) -> str:
    """The one line under the chat. It says what really happens: no key on the server, or AI switched off, means no AI."""
    W = say(s)
    if llm.client() is None: return W("Replies on this server come from our rules, without AI. More in", "इस सर्वर पर जवाब हमारे नियमों से बनते हैं, AI के बिना। ज़्यादा जानकारी:")
    if s.advisor.no_ai: return W("You turned AI off, so replies come from our rules. Change this in", "आपने AI बंद किया है, इसलिए जवाब हमारे नियमों से बनते हैं। इसे यहाँ बदलें:")
    return W("Replies are written with AI. Manage this in", "जवाब AI की मदद से लिखे जाते हैं। इसे यहाँ बदलें:")


def ai_settings(s: Session) -> dict:
    """The notice that Gemini reads the chat, and the switch to turn that off. Lives with the other privacy controls."""
    W = say(s)
    off = None if llm.client() is not None else W("This server has no AI key right now, so replies come from our rules and nothing is sent to Gemini. When a key is set:", "इस सर्वर पर अभी AI कुंजी नहीं है, इसलिए जवाब हमारे नियमों से बनते हैं और Gemini को कुछ नहीं भेजा जाता। कुंजी होने पर:")
    return {"off_note": off, "title": W("AI and your chat", "AI और आपकी चैट"), "body": W("We use Google Gemini to read the chat and word replies. It may process text outside India, and Google may use it to improve its products. We remove ID numbers and contact details before sending, but please don't type them. Our code always decides products and prices.", "चैट पढ़ने और जवाब के शब्द लिखने के लिए हम Google Gemini का उपयोग करते हैं। यह भारत के बाहर प्रोसेस हो सकता है, और Google इसे अपने उत्पाद सुधारने में उपयोग कर सकता है। भेजने से पहले हम ID नंबर और संपर्क जानकारी हटा देते हैं, फिर भी कृपया इन्हें न लिखें। प्रोडक्ट और कीमत हमेशा हमारा कोड तय करता है।"),
            "toggle": W("Let AI read my chat", "AI को मेरी चैट पढ़ने दें"), "help": W("The advisor still works with this off.", "बंद करने पर भी सलाहकार काम करता रहेगा।"), "on": not s.advisor.no_ai}


def quote_chat(s: Session) -> dict:
    """The same conversation, on the Quote page, so the owner can change the plan by chatting."""
    W = say(s)
    chat = chat_view(s)
    return {"title": W("Change your plan by chatting", "चैट करके अपना प्लान बदलें"), "hint": W("For example: \"add CCTV for 2 cameras\" or \"remove security\". The quote updates when the plan changes.", "जैसे: \"2 कैमरों के लिए CCTV जोड़ें\" या \"सिक्योरिटी हटाएँ\"। प्लान बदलते ही कोटेशन अपडेट होगा।"),
            "placeholder": W("Ask for a change", "बदलाव के लिए लिखें"), "send": W("Send", "भेजें"), "typing": W("Thinking…", "सोच रहे हैं…"), "listen": W("Read aloud", "सुनें"), **chat}


def _quote_state(s: Session) -> dict:
    """The one place the current plan is worked out, for showing it and for accepting it. Always from product ids, never from the browser."""
    rec = s.advisor.rec
    plan_id = tuple(sorted(rec.items.items()))
    if s.plan_id != plan_id:  # a new chat plan resets the choices
        s.plan_id, s.use_alt, s.qty, s.gstin_tick, s.removed = plan_id, False, {}, False, []
    use_alt = bool(s.use_alt and rec.alternative)
    base = rec.alternative if use_alt else rec.items
    also_gone = {}
    for pid in s.removed:
        if pid in base:
            base, gone = remove_with_dependents(base, pid)
            for g in gone: also_gone[g] = pid
    prof = s.advisor.profile
    if prof.has_gstin is None and s.gstin_tick: prof = prof.model_copy(update={"has_gstin": True})
    s.addons = {a for a in s.addons if a in ADDONS and a not in base and eligible(a, prof)[0]}
    res = apply_addons(prof, base, s.addons, s.qty)
    return dict(rec=rec, use_alt=use_alt, base=base, also_gone=also_gone, prof=prof, res=res, q=price(res["items"]))


def quote(s: Session) -> dict:
    W, t, lang = say(s), L[s.ui_lang], s.ui_lang
    head = chrome(s, "quote")
    if not (s.advisor.rec and s.advisor.rec.quote):
        return {**head, "title": t["quote"], "empty": t["no_plan"], "advisor": t["advisor"], "chat": quote_chat(s)}
    cat, st = catalogue(), _quote_state(s)
    rec, use_alt, base, also_gone, prof, res, q = (st[k] for k in ("rec", "use_alt", "base", "also_gone", "prof", "res", "q"))
    unit = {"per camera": W("Cameras", "कैमरे"), "per line": W("Mobile lines", "मोबाइल लाइन"), "per user": W("Users", "यूज़र"), "per device": W("Devices", "डिवाइस"), "per vehicle": W("Vehicles", "गाड़ियाँ"), "per counter": W("Billing counters", "बिलिंग काउंटर"), "per channel": W("Phone channels", "फ़ोन चैनल"), "per number": W("Numbers", "नंबर"), "per IP": W("IP addresses", "IP पते"), "per pack": W("Packs", "पैक")}
    notes = [t["needs"].format(a=cat[a].name, b=cat[b].name) for a, b in res["added"].items()]
    notes += [W(f"{cat[lost].name} also came out, because it needs {cat[why].name}.", f"{cat[lost].name} भी हट गया, क्योंकि इसके लिए {cat[why].name} चाहिए।") for lost, why in also_gone.items()]
    notes += [W(f"{cat[l].name} replaces {cat[g].name}, so you don't pay for two connections.", f"{cat[l].name} ने {cat[g].name} की जगह ली है, ताकि आपको दो कनेक्शन का भुगतान न करना पड़े।") for g, l in res["removed"].items()]
    base_contract = price(base).contract
    if q.contract != base_contract: notes.append(W(f"These changes make the minimum contract {q.contract} months (it was {base_contract}).", f"इन बदलावों से न्यूनतम अनुबंध {q.contract} महीने हो गया है (पहले {base_contract} था)।"))
    gap = q.monthly - (rec.alt_quote.monthly if use_alt else rec.quote.monthly) if s.removed else 0
    alt = None
    if rec.alternative and not s.removed:
        if use_alt: alt = {"on": True, "title": W("You're on the cheaper option.", "आप सस्ते विकल्प पर हैं।"), "body": trade_text(rec, lang), "button": W("Back to the recommended plan", "सुझाए गए प्लान पर वापस जाएँ")}
        else:
            names, saving = ", ".join(cat[k].name for k in rec.alternative), rec.quote.monthly - rec.alt_quote.monthly
            alt = {"on": False, "title": W(f"Cheaper option: {names}. Saves ₹{saving:,} a month.", f"सस्ता विकल्प: {names}। हर महीने ₹{saving:,} की बचत।"), "body": trade_text(rec, lang), "button": W("Switch to the cheaper option", "सस्ते विकल्प पर जाएँ")}
    seg = segment(s)
    def peers(pid):
        p = insights.peer_share(seg, pid)  # only for what's already in the plan: social proof, never an upsell
        return W(f"{p['share']:.0%} of {p['n']} past {seg.lower()} customers had this.", f"{seg} के {p['n']} पुराने ग्राहकों में से {p['share']:.0%} के पास यह था।") if p and p["share"] >= 0.05 else None
    event(s, "quote_viewed", variant=s.ab)
    lines = [{"peers": peers(l.product_id), "id": l.product_id, "name": l.name, "qty": l.qty, "monthly": l.monthly, "description": cat[l.product_id].description, "why": (W("Why: ", "क्यों: ") + w) if (w := why_text(rec, l.product_id, lang) if not use_alt and l.product_id in rec.items else "") else "",
              "qty_label": unit.get(l.unit) if l.unit in ADJUSTABLE_UNITS else None, "max": MAX_QTY, "remove": W(f"Remove {l.name}", f"{l.name} हटाएँ") if len(q.lines) > 1 and l.product_id in base else None} for l in q.lines]
    addons = []
    for pid in (a for a in ADDONS if a not in base):
        ok, reason = eligible(pid, prof)
        addons.append({"id": pid, "label": f"{cat[pid].name} · ₹{cat[pid].monthly:,}/{cat[pid].unit.replace('per ', '')}", "on": pid in s.addons, "ok": ok, "reason": None if ok else reason_text(reason, lang)})
    known_order(s)
    already = s.accepted_items == res["items"]
    paid = bool(s.order_id) and orders.get(s.order_id)["stage_index"] >= 2
    return {**head, "chat": quote_chat(s), "title": t["quote"], "monthly": q.monthly, "per_month": t["per_month"], "per_day": W(f"That's about ₹{round(q.monthly / 30):,} a day.", f"यानी लगभग ₹{round(q.monthly / 30):,} प्रति दिन।") if s.ab == "B" else None, "facts": [{"label": t["setup"], "value": f"₹{q.setup:,}"}, {"label": t["contract"], "value": f"{q.contract} {t['months']}"}, {"label": t["valid"], "value": day(q.valid_until)}, {"label": W("First payment", "पहला भुगतान"), "value": f"₹{first_payment(q):,}", "hint": W("First month plus setup, due after KYC.", "पहला महीना और सेटअप, KYC के बाद।")}, {"label": W(f"Total over {q.contract} months", f"{q.contract} महीनों में कुल"), "value": f"₹{contract_total(q):,}"}],
            "gst_note": W("Catalogue prices. Our data doesn't say whether GST is included, so a real bill should confirm this.", "ये कैटलॉग की कीमतें हैं। हमारे डेटा में यह नहीं बताया गया कि GST शामिल है या नहीं, इसलिए असली बिल में इसकी पुष्टि होनी चाहिए।"), "install_note": W(f"Usually installed in about {q.install_days} {'day' if q.install_days == 1 else 'days'}. This is an estimate; the real date appears in your tracker.", f"इंस्टॉलेशन में आमतौर पर लगभग {q.install_days} दिन लगते हैं। यह अनुमान है; असली तारीख ट्रैकर में दिखेगी।"),
            "notes": notes, "gap": W(f"₹{abs(gap):,} a month {'more' if gap > 0 else 'less'} than the plan I recommended.", f"सुझाए गए प्लान से हर महीने ₹{abs(gap):,} {'ज़्यादा' if gap > 0 else 'कम'}।") if gap else None, "put_back": W("Put back what I removed", "हटाई गई चीज़ें वापस लाएँ") if s.removed else None, "alt": alt, "lines": lines, "bundle": W("What's in your plan", "आपके प्लान में क्या है"),
            "addons_title": t["addons"], "addons": addons, "gstin_box": {"label": W("My business has a GSTIN", "मेरे बिज़नेस का GSTIN है"), "on": s.gstin_tick} if s.advisor.profile.has_gstin is None else None,
            "compare": {"title": W("Compare with your current bill", "अपने मौजूदा बिल से तुलना करें"), "label": W("What do you pay per month now for phone and internet? (₹)", "अभी फ़ोन और इंटरनेट पर हर महीने कितना देते हैं? (₹)"),
                        "snap": W("Snap your current phone or internet bill (optional)", "अपने मौजूदा फ़ोन या इंटरनेट बिल की फ़ोटो लें (वैकल्पिक)"), "snap_note": W("Read on our server and thrown away. Only the amount is used, and you can change it.", "हमारे सर्वर पर पढ़कर हटा दी जाती है। केवल राशि का उपयोग होता है, और आप उसे बदल सकते हैं।"),
                        "reading": W("Reading your bill…", "आपका बिल पढ़ा जा रहा है…"), "found": W("We read ₹{n} as the amount due. Please check it below.", "हमने देय राशि ₹{n} पढ़ी। कृपया नीचे जाँच लें।"), "not_found": W("We couldn't find the amount due on that photo. Please type it below.", "इस फ़ोटो पर देय राशि नहीं मिली। कृपया नीचे लिखें।")}, "download": W("Download this quote", "यह कोटेशन डाउनलोड करें"),
            "accept": W("Accept as a new order", "नए ऑर्डर के रूप में स्वीकार करें") if paid and not already else t["accept"], "already": already, "accepted": t["accepted"] if already else None, "paid_note": W("Your paid order stays as it is. Accepting this plan starts a separate order.", "आपका भुगतान किया गया ऑर्डर वैसा ही रहेगा। यह प्लान स्वीकार करने पर एक अलग ऑर्डर शुरू होगा।") if paid and not already else None, "has_order": bool(s.order_id), "next": t["consent"]}


def accept_quote(s: Session) -> None:
    st = _quote_state(s)
    res, q = st["res"], st["q"]
    if s.accepted_items == res["items"]: return  # a second tap must not create or change an order
    if not (s.order_id and orders.update_quote(s.order_id, res["items"], q)):  # changed the plan before payment: same order, not a second one
        s.order_id = orders.create(s.user, res["items"], q)
    from core import insights
    orders.set_meta(s.order_id, insights.segment_of(s.advisor.profile.business_type, s.advisor.profile.locations), st["prof"].has_gstin)
    if verdict_of(s) == "verified" and orders.get(s.order_id)["stage"] == "Quote accepted":  # KYC done first must not strand the order
        orders.advance(s.order_id, "KYC verified")
    s.accepted_items = dict(res["items"])
    event(s, "quote_accepted", variant=s.ab)


def compare_bill(s: Session, now: int) -> dict:
    W, q = say(s), _quote_state(s)["q"]
    gap = q.monthly - now
    return {"text": W(f"This plan is ₹{abs(gap):,} a month {'more' if gap > 0 else 'less'} than what you pay now." if gap else "This plan costs the same as what you pay now.", f"यह प्लान आपके मौजूदा बिल से हर महीने ₹{abs(gap):,} {'ज़्यादा' if gap > 0 else 'कम'} है।" if gap else "यह प्लान आपके मौजूदा बिल के बराबर है।"), "note": W("Your current services may differ, so compare what's included too.", "आपकी मौजूदा सेवाएँ अलग हो सकती हैं, इसलिए क्या-क्या शामिल है यह भी देखें।")}


def consent_panel(s: Session) -> dict:
    W, t, lang = say(s), L[s.ui_lang], s.ui_lang
    label = lambda p: consent.PURPOSE_LABEL.get(p, {}).get(lang, p)
    held = consent.what_we_hold(s.user)
    lines = [W(f"Consent records: {held['consents']}", f"सहमति रिकॉर्ड: {held['consents']}"), W(f"Orders: {held['orders']}", f"ऑर्डर: {held['orders']}")]
    if held["kyc"]: lines.append(W(f"KYC result: {t['verdicts'][held['kyc']]}", f"KYC परिणाम: {t['verdicts'][held['kyc']]}"))
    if held["gstin"]: lines.append(f"GSTIN: {held['gstin']}")
    if held["id"]: lines.append(f"ID: {held['id']}")
    if held["callback"]: lines.append(W("Your call-back details", "आपकी कॉल-बैक जानकारी"))
    if held.get("contact"): lines.append(W("Your name and mobile number, for installation and updates", "इंस्टॉलेशन और अपडेट के लिए आपका नाम और मोबाइल नंबर"))
    when = lambda ts: ts[:16].replace("T", " ")
    records = [f"{label(r['purpose'])} · {r['notice_version']} · {t['granted']} {when(r['granted_at'])} UTC" + (f" · {t['withdrawn']} {when(r['withdrawn_at'])} UTC" if r["withdrawn_at"] else "") for r in consent.records(s.user)]
    return {"receipt_json": W("Consent receipt for software (JSON)", "सॉफ़्टवेयर के लिए सहमति रसीद (JSON)") if records else None, "rights": W("Download, correct or delete your data", "अपना डेटा डाउनलोड करें, ठीक करवाएँ या मिटाएँ"), "title": t["your_consent"], "records": records, "held_title": W("What we hold about you", "आपके बारे में हमारे पास क्या है"), "held": lines + [W("No document images are kept.", "दस्तावेज़ों की तस्वीरें नहीं रखी जातीं।"), W("No voice recordings are kept.", "आवाज़ की रिकॉर्डिंग नहीं रखी जातीं।")], "receipt": t["receipt"] if records else None,
            "active": [{"purpose": p, "label": f"{t['withdraw']}: {label(p)}", "effect": consent.WITHDRAW_EFFECT[p][lang] if p in consent.WITHDRAW_EFFECT else None} for p in sorted(consent.active(s.user))]}


CONTACT_PROBLEM = {"bad_name": ("Please add your name.", "कृपया अपना नाम लिखें।"), "bad_phone": ("Please enter a valid 10-digit mobile number.", "कृपया सही 10 अंकों का मोबाइल नंबर दें।"), "no_agree": ("Please tick the box so we may use these details.", "इन जानकारियों के उपयोग की अनुमति के लिए कृपया बॉक्स पर टिक करें।")}


def contact_view(s: Session) -> dict:
    """Name and mobile for the technician and order updates. The owner sees their own details in full."""
    W, saved = say(s), contacts.get(s.user)
    return {"title": W("How we reach you", "हम आपसे कैसे संपर्क करें"), "why": W("Our technician needs a number to arrange installation, and order updates go to it if you turned them on. You'll need this before paying.", "इंस्टॉलेशन तय करने के लिए हमारे तकनीशियन को एक नंबर चाहिए, और अगर आपने ऑर्डर अपडेट चालू किए हैं तो वे इसी पर आएँगे। भुगतान से पहले यह ज़रूरी है।"),
            "saved": {"name": saved["name"], "phone": saved["phone"]} if saved else None, "saved_label": W("Saved", "सहेजा गया"), "edit": W("Change", "बदलें"),
            "name": W("Your name", "आपका नाम"), "phone": W("Mobile number", "मोबाइल नंबर"), "agree": W("Accel Business may use these to arrange installation, send order updates and let me reopen my order with a code. Nothing else.", "Accel Business इनका उपयोग केवल इंस्टॉलेशन तय करने, ऑर्डर अपडेट भेजने और कोड से मेरा ऑर्डर फिर से खोलने देने के लिए करे।"),
            "if_no": W("If you say no: we can't arrange installation. You can withdraw this later on the Your data page, which deletes them.", "अगर आप मना करते हैं: हम इंस्टॉलेशन तय नहीं कर पाएँगे। बाद में 'आपका डेटा' पेज पर इसे वापस ले सकते हैं, जिससे यह जानकारी हट जाएगी।"), "save": W("Save my contact details", "मेरी संपर्क जानकारी सहेजें")}


def consent_page(s: Session) -> dict:
    W, t, lang = say(s), L[s.ui_lang], s.ui_lang
    active = consent.active(s.user)
    kyc_ok, updates_ok = consent.KYC in active, consent.UPDATES in active
    return {**chrome(s, "consent"), "title": t["consent"], "short": consent.NOTICE_SHORT[lang], "read": t["read_notice"], "full": consent.NOTICE[lang], "keep_ready": t["keep_ready"], "docs": [{"name": d[lang][0], "why": d[lang][1]} for d in consent.DOCS_NEEDED.values()], "tip": consent.DOCS_TIP[lang],
            "kyc": {"given": kyc_ok, "given_text": W("KYC consent is given.", "KYC सहमति दी गई है।"), "label": W("Use my documents for KYC verification (required)", "KYC सत्यापन के लिए मेरे दस्तावेज़ों का उपयोग करें (ज़रूरी)"), "if_no": W("If you say no: we can't check your documents, so we can't activate your connection.", "अगर आप मना करते हैं: हम आपके दस्तावेज़ नहीं जाँच पाएँगे, इसलिए आपका कनेक्शन चालू नहीं हो पाएगा।")},
            "updates": {"given": updates_ok, "given_text": W("Order updates consent is given.", "ऑर्डर अपडेट की सहमति दी गई है।"), "label": W("Send order updates on WhatsApp/SMS (optional)", "WhatsApp/SMS पर ऑर्डर अपडेट भेजें (वैकल्पिक)"), "if_no": W("If you say no: nothing else changes, and you can still check your order in the tracker. In this demo no messages are sent.", "अगर आप मना करते हैं: और कुछ नहीं बदलेगा, आप ट्रैकर में अपना ऑर्डर देख सकते हैं। इस डेमो में कोई मैसेज नहीं भेजा जाता।")},
            "contact": contact_view(s),
            "tick_first": W("Tick KYC verification to continue.", "आगे बढ़ने के लिए KYC सत्यापन पर टिक करें।"), "save": W("Save consent", "सहमति सहेजें"), "next": t["kyc"], "panel": consent_panel(s) if consent.records(s.user) else None}


def _lookup_notices(s: Session) -> list[dict]:
    W, out = say(s), []
    found = s.lookup
    if "gst" in found:
        state, masked = found["gst"]["state"], found["gst"].get("masked", "")
        if state == "active": out.append({"tone": "success", "text": W(f"GSTIN {masked} is active. You can go ahead.", f"GSTIN {masked} सक्रिय है। आप आगे बढ़ सकते हैं।")})
        elif state in ("cancelled", "suspended"):
            word = W(state, KM.STATUS[state.title()][1])
            out.append({"tone": "danger", "person": True, "text": W(f"GSTIN {masked} is {word}, so we can't activate on it. If that's wrong, please talk to a person. You don't need to upload anything yet.", f"GSTIN {masked} {word} है, इसलिए इस पर सेवा चालू नहीं हो सकती। अगर यह ग़लत है, तो कृपया किसी व्यक्ति से बात करें। अभी कुछ अपलोड करने की ज़रूरत नहीं।")})
        elif state == "not_found": out.append({"tone": "warning", "text": W("We couldn't find this GSTIN in the registry. Please check it. You can still upload, and a person will review it.", "यह GSTIN रजिस्ट्री में नहीं मिला। कृपया जाँच लें। आप फिर भी अपलोड कर सकते हैं, कोई व्यक्ति इसकी जाँच करेगा।")})
        else: out.append({"tone": "warning", "text": W("That doesn't look like a valid GSTIN. Please check for a typo. It has 15 characters, like 27ABCDE1234F1Z5.", "यह सही GSTIN नहीं लगता। कृपया टाइपिंग की ग़लती जाँच लें। इसमें 15 अक्षर होते हैं, जैसे 27ABCDE1234F1Z5।")})
    if "udyam" in found:
        state, masked = found["udyam"]["state"], found["udyam"].get("masked", "")
        if state == "found": out.append({"tone": "success", "text": W(f"Udyam number {masked} is in the registry.", f"Udyam नंबर {masked} रजिस्ट्री में है।")})
        elif state == "not_found": out.append({"tone": "warning", "text": W("We couldn't find this Udyam number in the registry. Please check it. You can still upload, and a person will review it.", "यह Udyam नंबर रजिस्ट्री में नहीं मिला। कृपया जाँच लें। आप फिर भी अपलोड कर सकते हैं, कोई व्यक्ति इसकी जाँच करेगा।")})
        else: out.append({"tone": "warning", "text": W("That doesn't look like a Udyam number. It should look like UDYAM-MH-00-1234567.", "यह Udyam नंबर नहीं लगता। यह UDYAM-MH-00-1234567 जैसा होना चाहिए।")})
    return out


def need_contact_text(s: Session) -> dict:
    W = say(s)
    return {"text": W("Before paying, add a name and mobile number so our technician can reach you.", "भुगतान से पहले नाम और मोबाइल नंबर जोड़ें, ताकि हमारा तकनीशियन आपसे संपर्क कर सके।"), "link": W("Add contact details", "संपर्क जानकारी जोड़ें")}


def no_gst_needed(s: Session) -> bool:
    known_order(s)
    o = orders.get(s.order_id) if s.order_id else None
    return bool(o) and not orders.needs_gstin(o)


def upload_problem(s: Session, why: str, name: str) -> str:
    W = say(s)
    return name + " " + {"too_big": W(f"is larger than we accept (over {MAX_UPLOAD_MB} MB, or a very large image). Please send a smaller copy.", f"सीमा से बड़ी है ({MAX_UPLOAD_MB} MB से ज़्यादा, या बहुत बड़ी इमेज)। कृपया छोटी कॉपी भेजें।"), "too_many": W(f"has more than {MAX_PAGES} pages. Please send only the pages we need.", f"में {MAX_PAGES} से ज़्यादा पेज हैं। कृपया केवल ज़रूरी पेज भेजें।"), "bad_file": W("can't be opened. It may be damaged, password-protected or not a real image or PDF. Please choose another.", "खुल नहीं रही। हो सकता है यह ख़राब हो, पासवर्ड से सुरक्षित हो, या असली इमेज या PDF न हो। कृपया दूसरी चुनें।"), "busy": W("couldn't be held right now because the server is busy. Please try again shortly.", "अभी नहीं रखी जा सकी, क्योंकि सर्वर व्यस्त है। कृपया थोड़ी देर बाद कोशिश करें।")}[why]


def _kyc_result(s: Session) -> dict | None:
    W, t, lang = say(s), L[s.ui_lang], s.ui_lang
    res = s.kyc_result
    if res and consent.latest_kyc(s.user) is None:  # erased when consent was withdrawn: never show it
        s.kyc_result = res = None
    if not res: return None
    label = {"gstin": "GSTIN", "udyam": W("Udyam no.", "Udyam नंबर"), "id_no": W("ID no.", "ID नंबर"), "legal_name": W("Legal name", "कानूनी नाम"), "trade_name": W("Trade name", "व्यापार का नाम"), "constitution": W("Business type", "बिज़नेस का प्रकार"), "address": W("Address", "पता"), "name": W("Name", "नाम"), "city": W("City", "शहर"), "state": W("State", "राज्य"), "designation": W("Role", "पद"), "business": W("Business", "बिज़नेस"), "valid_till": W("Valid till", "मान्य तक"), "billed_to": W("Billed to", "बिल किसके नाम"), "date": W("Bill date", "बिल की तारीख")}
    verdict, issues = res["verdict"], res["issues"]
    shown = [x for x in issues if x[0] == "reject"] or issues
    reason = (KM.VERIFIED_HI if lang == "hi" else KM.VERIFIED_EN) if verdict == "verified" else " ".join(KM.issue_text(code, p, lang) for _, code, p in shown)
    docs = []
    for doc in FILES:
        mine = [x for x in issues if KM.issue_doc(x[1]) == doc]
        ok = [x for x in res["checks"] if KM.passed_doc(x[0]) == doc]
        read = res["read"].get(doc, {})
        docs.append({"name": KM.DOC_NAME[doc][lang], "state": "reject" if any(x[0] == "reject" for x in mine) else "review" if mine else "ok" if ok or read else "none", "issues": [{"tone": "danger" if sev == "reject" else "warning", "text": KM.issue_text(code, p, lang)} for sev, code, p in mine], "passed": [KM.passed_text(code, p, lang) for code, p in ok], "read_title": W("What we read", "हमने क्या पढ़ा"), "read": [f"{label.get(k, k)}: {v}" for k, v in read.items()]})
    f = res["fields"]
    saved = [x for x in (f"GSTIN {f['gstin_masked']}" if f.get("gstin_masked") else "", f"{W('Registry status', 'रजिस्ट्री स्थिति')}: {f['registry_status']}" if f.get("registry_status") else "", f"ID {f['id_masked']}" if f.get("id_masked") else "") if x]
    return {"who": f"{W('Result for', 'परिणाम:')} " + (W("your documents", "आपके दस्तावेज़") if res["source"] == "upload" else res["source"]), "verdict": verdict, "verdict_label": t["verdicts"][verdict], "reason": reason,
            "next": {"needs_review": W("What happens next: your order waits while a person on our team checks this. You can also fix what's marked below and verify again.", "आगे क्या होगा: जब तक हमारी टीम का कोई व्यक्ति इसकी जाँच करता है, आपका ऑर्डर रुका रहेगा। आप नीचे बताई गई चीज़ ठीक करके दोबारा सत्यापित भी कर सकते हैं।"), "rejected": W("What happens next: we can't activate on these documents. If you think this is wrong, a person can look at it.", "आगे क्या होगा: इन दस्तावेज़ों पर सेवा चालू नहीं हो सकती। अगर आपको लगता है कि यह ग़लत है, तो कोई व्यक्ति इसे देख सकता है।")}.get(verdict),
            "docs": docs, "saved": f"{t['stored']}: " + " · ".join(saved) if saved else None, "unused": W(f"We couldn't recognise {res['unused']} of your files, so we didn't use them.", f"आपकी {res['unused']} फ़ाइलें पहचानी नहीं जा सकीं, इसलिए उनका उपयोग नहीं हुआ।") if res.get("unused") else None, "seconds": W(f"Checked in {res['seconds']} seconds.", f"{res['seconds']} सेकंड में जाँचा गया।"), "note": t["kyc_note"]}


def kyc(s: Session) -> dict:
    W, t, lang = say(s), L[s.ui_lang], s.ui_lang
    head = chrome(s, "kyc")
    if consent.KYC not in consent.active(s.user):
        return {**head, "title": t["kyc"], "blocked": t["first_consent"], "consent": t["consent"]}
    job = s.kyc_job
    if job and job["state"] in ("queued", "running"):
        job_view = {"busy": True, "done": job["done"], "total": job["total"], "text": W("Waiting for a free slot…", "आपकी बारी का इंतज़ार…") if job["state"] == "queued" else W(f"Reading file {job['done'] + 1} of {job['total']}…", f"{job['total']} में से फ़ाइल {job['done'] + 1} पढ़ी जा रही है…"), "hint": W("You can keep this page open. Reading can take a minute or two.", "यह पेज खुला रखें। पढ़ने में एक-दो मिनट लग सकते हैं।")}
    else:
        job_view = {"busy": False, "error": W("We can't read documents right now. This isn't about your documents, and nothing has been saved. Please try again shortly.", "अभी हम दस्तावेज़ नहीं पढ़ पा रहे। इसका आपके दस्तावेज़ों से कोई लेना-देना नहीं, और कुछ सहेजा नहीं गया। कृपया थोड़ी देर बाद कोशिश करें।") if job and job["state"] == "error" else None}
    last = consent.latest_kyc(s.user)
    reviewed = None
    if last and json.loads(last["fields"] or "{}").get("reviewed"):  # a person decided after the automatic check: that decision counts
        s.kyc_result = None
        reviewed = {"tone": "success" if last["verdict"] == "verified" else "danger", "text": W("A person on our team checked your documents. Result: ", "हमारी टीम के एक व्यक्ति ने आपके दस्तावेज़ जाँचे। परिणाम: ") + t["verdicts"].get(last["verdict"], last["verdict"]) + "."}
    can_pay = bool(s.order_id and last and orders.can_pay(orders.get(s.order_id), last["verdict"]))
    need_contact = can_pay and not contacts.get(s.user)
    can_pay = can_pay and not need_contact
    paid_notice = t["paid"] if s.paid_notice else None
    s.paid_notice = False
    return {**head, "title": t["kyc"], "lookup": {"title": W("Check your numbers first (optional)", "पहले अपने नंबर जाँचें (वैकल्पिक)"), "intro": W("An instant registry check, before you upload anything. We show only the status.", "कुछ भी अपलोड करने से पहले तुरंत रजिस्ट्री जाँच। हम केवल स्थिति दिखाते हैं।"), "gstin": "GSTIN", "udyam": W("Udyam number", "Udyam नंबर"), "check": W("Check", "जाँचें"), "notices": _lookup_notices(s), "person": W("Talk to a person", "किसी व्यक्ति से बात करें")},
            "docs_label": t["docs"], "modes": {"specimen": t["specimen"], "upload": t["upload"]}, "applicant": t["applicant"], "applicants": [f"K{i:02d}" for i in range(1, 13)], "show_docs": W("Show these documents", "ये दस्तावेज़ दिखाएँ"), "reviewed": reviewed,
            "specimen_docs": {a: [{"key": d, "name": KM.DOC_NAME[d][lang]} for d in FILES if (KYC_DATA / "kyc_documents" / f"{a}_{FILES[d]}.png").exists()] for a in SPECIMEN_REVIEW}, "only_these": W("This applicant sent only these documents.", "इस आवेदक ने केवल ये दस्तावेज़ भेजे।"),
            "upload_intro": W(f"Add all your documents together, in any order. We work out which is which. Photos or PDFs, up to {MAX_UPLOAD_MB} MB each. Files are read in memory and never stored.", f"अपने सभी दस्तावेज़ एक साथ, किसी भी क्रम में जोड़ें। कौन-सा क्या है, यह हम पहचान लेंगे। फ़ोटो या PDF, हर फ़ाइल {MAX_UPLOAD_MB} MB तक। फ़ाइलें केवल मेमोरी में पढ़ी जाती हैं, सहेजी नहीं जातीं।"), "no_gst": W("Your plan doesn't need a GSTIN. If you don't have one, tick the box below, then your signatory ID and address proof are enough.", "आपके प्लान के लिए GSTIN ज़रूरी नहीं। GSTIN न हो तो नीचे का बॉक्स चुनें, फिर हस्ताक्षरकर्ता की ID और पते का प्रमाण काफ़ी है।") if no_gst_needed(s) else None,
            "no_gstin_label": W("I confirm my business has no GSTIN", "मैं पुष्टि करता/करती हूँ कि मेरे बिज़नेस के पास GSTIN नहीं है") if no_gst_needed(s) else None,
            "choose": W("Choose photos or PDFs", "फ़ोटो या PDF चुनें"), "pending": len(s.pending), "pending_label": W(f"{len(s.pending)} page(s) ready to check", f"{len(s.pending)} पेज जाँच के लिए तैयार"), "clear": W("Remove all", "सब हटाएँ"), "max_pages": MAX_PAGES, "verify": t["verify"], "job": job_view, "result": _kyc_result(s), "person": W("Talk to a person", "किसी व्यक्ति से बात करें"),
            "accept_first": W("Your documents are verified. Accept a quote to continue.", "आपके दस्तावेज़ सत्यापित हैं। आगे बढ़ने के लिए कोटेशन स्वीकार करें।") if last and last["verdict"] == "verified" and not s.order_id else None, "quote": t["quote"], "pay": {"label": f"{t['pay']} · ₹{orders.first_due(orders.get(s.order_id)):,}", "order": s.order_id} if can_pay else None, "paid_notice": paid_notice, "tracker": t["tracker"], "need_contact": need_contact_text(s) if need_contact else None}


def find_view(s: Session) -> dict:
    """Reopen an order from another day or phone: order number, the mobile given on the Consent page, then a code."""
    W = say(s)
    return {"title": W("Find my order", "मेरा ऑर्डर खोजें"), "intro": W("Ordered earlier, or on another phone? Enter your order number and the mobile number you gave us.", "पहले या किसी दूसरे फ़ोन से ऑर्डर किया था? अपना ऑर्डर नंबर और हमें दिया मोबाइल नंबर लिखें।"),
            "order": W("Order number", "ऑर्डर नंबर"), "phone": W("Mobile number", "मोबाइल नंबर"), "send": W("Send me a code", "मुझे कोड भेजें"),
            "code": W("6-digit code", "6 अंकों का कोड"), "open": W("Open my order", "मेरा ऑर्डर खोलें"), "again": W("Ask for a new code", "नया कोड माँगें"),
            "sent": W("Code sent to {to}.", "कोड {to} पर भेजा गया।"), "demo": W("Demo: no SMS is sent, so here is the code a real launch would text you:", "डेमो: कोई SMS नहीं भेजा जाता, इसलिए असली सेवा में भेजा जाने वाला कोड यह है:"),
            "fresh": W("Opening your order starts this browser afresh.", "ऑर्डर खोलने पर यह ब्राउज़र नए सिरे से शुरू होगा।")}


def tracker(s: Session) -> dict:
    W, t = say(s), L[s.ui_lang]
    head = chrome(s, "tracker")
    mine = orders.for_user(s.user)
    panel = consent_panel(s)
    if not mine:
        return {**head, "title": t["tracker"], "empty": t["no_order"], "quote": t["quote"], "panel": panel if consent.records(s.user) else None, "find": find_view(s)}
    oid = s.tracker_order if s.tracker_order in mine else s.order_id if s.order_id in mine else mine[0]
    names = dict(zip(orders.STAGES, t["stages"] or orders.STAGES))
    o = orders.get(oid)
    verdict = verdict_of(s)
    activated = o["stage_index"] == len(orders.STAGES) - 1
    consent_ok = consent.KYC in consent.active(s.user)
    step = orders.next_step(o)
    fromiso = orders.date.fromisoformat
    out = {**head, "title": t["tracker"], "order": oid, "order_no": W(f"Order number {oid}. Keep it to find this order again from another phone or day.", f"ऑर्डर नंबर {oid}। किसी दूसरे फ़ोन या दिन इस ऑर्डर को फिर से देखने के लिए इसे संभालकर रखें।"), "orders": [{"id": n, "label": f"#{n} · ₹{orders.get(n)['monthly']:,}{W('/month', '/माह')} · {names[orders.get(n)['stage']]}"} for n in mine] if len(mine) > 1 else None, "order_label": W("Order", "ऑर्डर"), "stage": names[o["stage"]], "progress": (o["stage_index"] + 1) / len(orders.STAGES)}
    if activated: out["activated"] = W("Your connection is active.", "आपका कनेक्शन चालू है।")
    elif verdict != "verified":
        # Hold: say why, what to do, and what happened to any payment. Refunds aren't in the rules, so none is promised.
        out["hold"] = {"text": t["hold"], "detail": None if consent_ok else W("KYC consent isn't active, so we can't use your documents.", "KYC सहमति सक्रिय नहीं है, इसलिए हम आपके दस्तावेज़ों का उपयोग नहीं कर सकते।"), "to": "/kyc" if consent_ok else "/consent", "label": t["kyc"] if consent_ok else t["consent"], "paid": W("Your payment is recorded. For questions about it, please talk to a person.", "आपका भुगतान दर्ज है। इसके बारे में सवालों के लिए कृपया किसी व्यक्ति से बात करें।") if o["stage_index"] >= 2 else None}
    else:
        nxt = {"title": W("Next", "अगला चरण"), "stage": names[step["stage"]], "who": W("You", "आप") if step["who"] == "you" else "Accel Business"}
        if step["estimate"]: nxt["estimate"] = W("Estimated installation: ", "अनुमानित इंस्टॉलेशन: ") + day(step["estimate"]) + W(" (an estimate, not a promise)", " (अनुमान, वादा नहीं)")
        elif step["stage"] == "Activated": nxt["estimate"] = W("We'll update this page when activation is done.", "सक्रिय होने पर यह पेज अपडेट हो जाएगा।")
        out["next"] = nxt
        if orders.can_pay(o, verdict):
            if contacts.get(s.user): out["pay"] = f"{t['pay']} · ₹{orders.first_due(o):,}"
            else: out["need_contact"] = need_contact_text(s)
        if o["stage"] == "Quote accepted": out["kyc_link"] = t["kyc"]
    if s.paid_notice: out["paid_notice"] = t["paid"]
    if s.pay_failed: out["pay_failed"] = W("The payment didn't go through. Nothing was charged. Please try again.", "भुगतान नहीं हो पाया। कोई पैसा नहीं कटा। कृपया दोबारा कोशिश करें।")
    s.paid_notice = s.pay_failed = False
    late = orders.delays(oid)
    if late and o["stage_index"] < 5:  # say what happened and the new date, before the owner has to call
        d = late[-1]
        why = {"fibre": W("Fibre can't reach your premises right now.", "अभी आपकी जगह फाइबर नहीं पहुँच पा रहा।"), "partner": W("Our installation partner needs more time.", "हमारे इंस्टॉलेशन पार्टनर को और समय चाहिए।"), "access": W("We couldn't get access to your site.", "हमें आपकी जगह तक पहुँच नहीं मिल पाई।")}[d["reason"]]
        out["delay"] = {"title": W("Your installation is delayed.", "आपका इंस्टॉलेशन देर से होगा।"), "body": why + W(f" New estimate: {day(fromiso(d['new_date']))}, moved from {day(fromiso(d['old_date']))}.", f" नया अनुमान: {day(fromiso(d['new_date']))}, पहले {day(fromiso(d['old_date']))} था।")}
        if d["reason"] == "fibre" and orders.can_switch_to_airfiber(o):
            air = catalogue()["P04"]
            out["delay"]["air"] = W(f"{air.name} is wireless and needs no fibre. To ask about switching, please talk to a person.", f"{air.name} वायरलेस है और इसमें फाइबर नहीं चाहिए। बदलने के लिए कृपया किसी व्यक्ति से बात करें।")
    if o.get("technician"): out["tech"] = f"{t['tech']}: {o['technician']}"
    done = {e["stage"]: e["ts"] for e in o["events"]}
    steps = []
    for st in orders.STAGES:
        when = orders.shown_time(done[st], o["created"]).strftime("%d %b, %I:%M %p") + " IST" if st in done else ""
        if st == "Installed" and st not in done and o["stage_index"] >= 2: when = W("about ", "लगभग ") + day(max(x for _, x in orders.product_dates(o)))
        steps.append({"label": names[st], "state": "done" if st in done else "now" if st == o["stage"] else "todo", "when": when})
    if not activated and o["stage_index"] + 1 < len(steps): steps[o["stage_index"] + 1]["state"] = "now"
    out["steps"], out["today_note"] = steps, W(f"This demo treats {day(TODAY)} as today.", f"यह डेमो {day(TODAY)} को आज की तारीख मानता है।")
    past = insights.activation_days(segment(s), s.advisor.profile.city_tier)
    if past and not activated:  # the old field process, as a yardstick: history, not a promise
        out["past"] = W(f"For comparison: through field sales, businesses like yours took {past['low']}–{past['high']} days from first contact to activation (the middle half of {past['n']} past activations).", f"तुलना के लिए: फ़ील्ड सेल्स से आप जैसे बिज़नेस को पहले संपर्क से सक्रिय होने में {past['low']}–{past['high']} दिन लगे ({past['n']} पुराने कनेक्शनों का बीच का आधा हिस्सा)।")
    out["moved"] = [W(f"Installation moved from {day(fromiso(m['old_date']))} to {day(fromiso(m['new_date']))}.", f"इंस्टॉलेशन {day(fromiso(m['old_date']))} से {day(fromiso(m['new_date']))} पर किया गया।") for m in orders.changes(oid)]
    if 3 <= o["stage_index"] < 5 and verdict == "verified":
        low, high = orders.earliest_install(o), TODAY + orders.timedelta(days=orders.MAX_RESCHEDULE_DAYS)
        out["reschedule"] = {"title": t["resched"], "label": t["new_date"], "value": o["install_date"], "min": low.isoformat(), "max": high.isoformat(), "hint": W(f"You can choose {day(low)} to {day(high)}.", f"आप {day(low)} से {day(high)} के बीच चुन सकते हैं।"), "button": t["resched_btn"]}
    cat = catalogue()
    dates = dict(orders.product_dates(o))
    out["ordered"] = {"title": W("What you ordered", "आपने क्या ऑर्डर किया"), "items": [{"name": cat[p].name + (f" × {n}" if n > 1 else ""), "when": "" if o["stage_index"] >= 5 else W(f"expected about {day(dates[p])}", f"लगभग {day(dates[p])} तक")} for p, n in json.loads(o["items"]).items()], "monthly": f"₹{o['monthly']:,} {t['per_month']}", "setup": f"{t['setup']}: ₹{o['setup']:,}", "contract": f"{t['contract']}: {o['contract']} {t['months']}"}
    wants = consent.UPDATES in consent.active(s.user)
    out["updates"] = {"title": W("Updates sent to you", "आपको भेजे गए अपडेट"), "items": [orders.shown_time(u["ts"], o["created"]).strftime("%d %b, %I:%M %p") + " · " + (W(f"Your installation is delayed. New estimate: {day(fromiso(u['new_date']))}.", f"आपका इंस्टॉलेशन देर से होगा। नया अनुमान: {day(fromiso(u['new_date']))}।") if u["stage"] == "delay" else W(f"Your order moved on: {names[u['stage']]}.", f"आपका ऑर्डर आगे बढ़ा: {names[u['stage']]}।")) for u in reversed(orders.updates_log(o))] if wants else [], "note": W("A log for this prototype. No SMS or WhatsApp is sent.", "यह प्रोटोटाइप का लॉग है। कोई SMS या WhatsApp नहीं भेजा जाता।") if wants else W("You haven't turned on order updates. You can on the consent page.", "आपने ऑर्डर अपडेट चालू नहीं किए हैं। सहमति पेज पर कर सकते हैं।")}
    out["person"] = W("Talk to a person", "किसी व्यक्ति से बात करें")
    if not activated:
        can_adv, can_pay_now = orders.can_advance(o, verdict), orders.can_pay(o, verdict)
        out["demo"] = {"title": t["demo"], "note": t["demo_note"], "advance": t["advance"] if can_adv else None, "fail": W("Simulate a failed payment", "असफल भुगतान का डेमो") if can_pay_now else None, "delay": W("Simulate a fibre delay", "फाइबर में देरी का डेमो") if verdict == "verified" and 3 <= o["stage_index"] < 5 and not late else None, "blocked": None if can_adv else W("Nothing to move right now: this step needs you first.", "अभी आगे बढ़ाने को कुछ नहीं: इस चरण में पहले आपकी ज़रूरत है।")}
    out["panel"] = panel
    return out


def data_page(s: Session) -> dict:
    """The owner's rights under the DPDP Act, 2023: see, correct, erase."""
    W = say(s)
    return {**chrome(s), "title": W("Your data", "आपका डेटा"), "intro": W("Your rights under the Digital Personal Data Protection Act, 2023: see what we hold, ask us to correct it, or erase it.", "डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023 के तहत आपके अधिकार: देखें हमारे पास क्या है, उसे ठीक करवाएँ, या मिटवाएँ।"),
            "panel": consent_panel(s), "ai": ai_settings(s), "export_title": W("Download everything we hold", "हमारे पास जो कुछ है, सब डाउनलोड करें"), "export": W("Download my data (JSON)", "मेरा डेटा डाउनलोड करें (JSON)"),
            "correct_title": W("Ask us to correct something", "कुछ ठीक करवाना है?"), "correct_label": W("What's wrong, and what should it say? Please don't type ID numbers.", "क्या ग़लत है, और सही क्या होना चाहिए? कृपया ID नंबर न लिखें।"), "correct": W("Send request", "अनुरोध भेजें"),
            "correct_sent": W(f"Sent. We aim to reply within {rights.REPLY_DAYS} days.", f"भेज दिया। हम {rights.REPLY_DAYS} दिनों में जवाब देने की कोशिश करेंगे।"), "correct_empty": W("Please say what to correct.", "कृपया बताएँ क्या ठीक करना है।"),
            "erase_title": W("Erase my data", "मेरा डेटा मिटाएँ"), "erase_note": W("This deletes your KYC result, call-back details, requests and any unpaid order, and withdraws every consent. A paid order is kept while your service runs, because billing and the contract need it. Consent records stay, marked withdrawn, as proof of what you agreed.",
            "इससे आपका KYC परिणाम, कॉल-बैक जानकारी, अनुरोध और बिना भुगतान वाला ऑर्डर हट जाएगा, और हर सहमति वापस हो जाएगी। भुगतान किया गया ऑर्डर सेवा चलने तक रहेगा, क्योंकि बिलिंग और अनुबंध के लिए ज़रूरी है। सहमति रिकॉर्ड प्रमाण के तौर पर 'वापस ली गई' लिखकर रहेंगे।"),
            "erase_sure": W("I understand this can't be undone", "मैं समझता/समझती हूँ कि यह वापस नहीं हो सकता"), "erase": W("Erase my data", "मेरा डेटा मिटाएँ"), "erased": W("Done. We've erased what we held, and this browser now starts fresh.", "हो गया। हमारे पास जो था वह मिटा दिया गया, और यह ब्राउज़र अब नए सिरे से शुरू होगा।")}


REASON = {"multi_site": "Several locations", "manufacturer_custom": "Factory with custom needs", "needs_scoping": "Wants a line they aren't eligible for", "frustration": "Asked for a person", "repeated_confusion": "Repeatedly confused", "tier_not_served": "Town not served yet", "no_eligible": "No eligible plan", "large_account": "Larger than a small business", "customer_request": "Asked for a call"}
VERDICT = {"needs_review": "Needs review", "rejected": "Rejected"}
AI_HOW = {"worded": "Worded by Gemini, checked", "template": "Standard text (AI off, busy or refused)", "refused": "Gemini attempt refused by the guard"}


def _table(headers, rows, empty, title=None, note=None) -> dict:
    return {"title": title, "note": note, "headers": headers, "rows": [["" if c is None else str(c) for c in r] for r in rows], "empty": empty}


def _dashboard() -> dict:
    steps = events.funnel()
    started, done = steps[0]["count"], steps[-1]["count"]
    with db.conn() as conn:
        all_orders = [orders.get(r[0]) | {"user": r[1]} for r in conn.execute("SELECT id,user FROM orders")]
    cat = catalogue()
    broken = sum(any(cat[p].requires_one_of and not set(cat[p].requires_one_of) & set(json.loads(o["items"])) for p in json.loads(o["items"])) for o in all_orders)
    unverified = sum((consent.latest_kyc(o["user"]) or {}).get("verdict") != "verified" and o["stage_index"] >= 3 for o in all_orders)
    watch = orders.watchlist()
    ab = events.ab_test()
    return {"note": "Counted from this server's own events since its database was created. Each event is a random funnel id and a step, never a person.", "tables": [
        _table(["Step", "Reached", "Of chats started", "Median minutes from previous step"], [[x["step"], x["count"], f"{x['share']:.0%}" if x["share"] is not None else "–", x["minutes"] if x["minutes"] is not None else "–"] for x in steps], "", "Funnel"),
        _table(["Metric", "Data baseline", "Target", "This app"], [
            ["Lead to activation", "7.4%", "11%", f"{done / started:.0%} ({done} of {started})" if started else "no chats yet"],
            ["Status chases per paid order", "3.0", "1 or fewer", f"{sum(w['chases'] for w in watch) / len(watch):.1f} (delays, reschedules, call-backs)" if watch else "no paid orders yet"],
            ["Days to activate", "17.6", "10", "n/a: demo controls skip ahead"],
            ["Rule-breaking bundles (keep at 0)", "56", "0", f"{broken} of {len(all_orders)} orders (product dependencies)"],
            ["Installs on unverified KYC (keep at 0)", "22 on inactive GSTINs", "0", unverified],
            ["False KYC rejections (keep at 0)", "not measured", "0", f"{reviews.overturned_rejections()} reversed by a person"]], "", "Against the deck's targets"),
        _table(["How the reply was made", "Count"], [[AI_HOW.get(k, k), v] for k, v in llm.stats.items()], "No AI replies yet.", "AI replies since the server started", f"Last AI problem: {llm.last_error}" if llm.last_error else None),
        _table(["Reason", "Count"], [[REASON.get(k, k), v] for k, v in sorted(events.counts("handoff").items(), key=lambda x: -x[1])], "No hand-offs yet.", "Hand-offs by reason"),
        _table(["Variant", "Saw a quote", "Accepted", "Rate"], [[{"A": "A: monthly price only", "B": "B: plus the daily figure"}[v], a["viewed"], a["accepted"], f"{a['rate']:.0%}" if a["rate"] is not None else "–"] for v, a in ab["arms"].items()], "",
               'A/B test: does "about ₹N a day" under the price help owners accept?', (f"Two-proportion test p = {ab['p']:.2f}. " if ab["p"] is not None else "") + ("Enough data to read." if ab["enough"] else "Too few visitors to call a winner: we'd wait for about 100 per variant before deciding."))]}


def _review(selfcheck: dict) -> dict:
    with db.conn() as conn:
        ids = {r["user"]: r["id"] for r in conn.execute("SELECT user, MAX(id) AS id FROM kyc GROUP BY user")}
    waiting_ids = {r["kyc_id"] for r in reviews.pending()}
    rows, open_cases = [], []
    for r in consent.kyc_queue():
        f = json.loads(r["fields"] or "{}")
        docs = list(dict.fromkeys(KM.DOC_NAME[KM.issue_doc(x)]["en"] for x in f.get("issues", []) if x in KM.ISSUE))
        case = ids[r["user"]]
        status = "Waiting for second person" if case in waiting_ids else "Open"
        if status == "Open": open_cases.append(case)
        rows.append([case, r["ts"], "…" + r["user"][-4:], VERDICT.get(r["verdict"], r["verdict"]), ", ".join(docs), r["reason"], "; ".join(forensics.describe(x) for x in f.get("signals", [])) or "none", status])
    return {"note": "Anything the automatic check couldn't verify. One person proposes a decision and a different person confirms it; only then does the owner's result change. File signals are for reviewers only and never change a verdict.",
            "queue": _table(["Case", "When", "Ref", "Result", "Check", "Why", "File signals", "Status"], rows, "Nothing waiting. Results that aren't verified appear here."),
            "open_cases": open_cases, "decisions": reviews.DECISIONS, "pending": [{"id": w["id"], "text": f"Case {w['kyc_id']} · {w['was']} → {reviews.DECISIONS[w['decision']]} · proposed by {w['maker']}", "note": w["note"]} for w in reviews.pending()],
            "rights": _table(["When", "Ref", "Kind", "Detail", "Reply by", "Status"], [[r["ts"], "…" + r["user"][-4:], r["kind"], r["detail"], r["due"], r["status"]] for r in rights.requests()], "No requests.", "Data rights requests"),
            "selfcheck": {"title": "KYC self-check on the 12 specimen applicants", "note": "Runs the live KYC code on this server and compares it with our own manual review of the images (not the judges' key). Nothing is stored.", "button": "Run the self-check", **selfcheck}}


def _leads(scores: dict) -> dict:
    cb = []
    for r in callback.queue():
        seg = insights.segment_of(r["profile"].get("business_type"), r["profile"].get("locations"))
        cb.append([r["ts"], r["name"][:1] + "…" if r["name"] else "", mask(r["phone"]), mask(r["email"]), r["best_time"], REASON.get(r["reason"], r["reason"]), r["profile"].get("business_type"), r["profile"].get("city"), insights.route(seg, r["reason"])["route"]])
    hand = []
    for l in db.list_leads():
        p = json.loads(l["profile"]); seg = insights.segment_of(p.get("business_type"), p.get("locations")); rt = insights.route(seg, l["reason"])
        hand.append([l["ts"], REASON.get(l["reason"], l["reason"]), p.get("business_type"), p.get("city"), p.get("employees"), p.get("locations"), ", ".join(p.get("needs", [])), rt["route"], rt["why"]])
    owner = {}
    with db.conn() as conn:
        for r in conn.execute("SELECT id, user FROM orders"): owner[r["id"]] = r["user"]
    watch = [[w["order"], contacts.masked(owner.get(w["order"], "")) or "not given", w["stage"], w["segment"], w["chases"], f"{w['level']} ({w['rate']:.0%})", " · ".join(w["reasons"])] for w in orders.watchlist()]
    dropped = [r + [insights.route(r[1])["route"]] for r in scores["rows"]]
    return {"tables": [
        _table(["When", "Name", "Phone", "Email", "Best time", "Why", "Business", "City", "Send"], cb, "No call-back requests yet.", "Call-back requests", "Contact details are masked because this demo page has no login. A real team view needs staff sign-in before showing them in full."),
        _table(["When", "Why", "Business", "City", "Staff", "Sites", "Needs", "Send", "Because"], hand, "No hand-offs yet. They appear here when the advisor passes a customer to a person.", "Advisor hand-offs", "Field visits only where a site survey is needed: elsewhere the data shows they cost several times as much per activation as a phone-led sale."),
        _table(["Order", "Contact", "Stage", "Segment", "Times chased", "Risk", "Because"], watch, "No paid orders yet.", "Orders to check in on", "Paid orders ranked by churn risk. In the data, owners who had to chase us churned far more (5.9% at 0–1 follow-up calls, 27.9% at 5 or more), so each delay, reschedule or call-back raises the risk. A rough guide for a proactive call, not a verdict."),
        _table(["Business", "Segment", "City", "Language", "Source", "Why it dropped", "Score", "Why this score", "Say first", "Send"], dropped, "No leads.", "Dropped leads to call first", f"Leads lost to our process, not refusals. The score only ranks them (cross-validated AUC {scores['auc']:.2f}, so a useful guide, not a verdict). \"Why\" names what lifts each score most; \"Say first\" answers why they dropped.")]}


def what_if(segment_name: str, share: float, price_move: float, churn_move: float) -> dict:
    base = insights.payback_base()
    if segment_name not in base: segment_name = insights.MICRO_SEG
    now, then = insights.what_if(segment_name), insights.what_if(segment_name, share, price_move, churn_move)
    moved = (share, price_move, churn_move) != (0, 0, 0)
    b = base[segment_name]
    delta = lambda key, fmt: (format(then[key] - now[key], fmt) if moved else None)
    return {"segment": segment_name, "metrics": [{"label": "Spend per activation", "value": f"₹{then['spend']:,.0f}", "delta": delta("spend", "+,.0f"), "good_down": True}, {"label": "Months to pay back", "value": f"{then['payback_months']:.1f}", "delta": delta("payback_months", "+.1f"), "good_down": True},
                                         {"label": "First-year revenue per ₹1 spent", "value": f"₹{then['return']:.2f}", "delta": delta("return", "+.2f"), "good_down": False}],
            "note": f"Starts from the data for {b['n']} activated {segment_name.lower()} customers: ₹{b['spend']:,.0f} spent per activation (all channels), ₹{b['value']:,.0f} a month, {b['churn']:.0%} churn in 6 months. Phone-led sales cost ₹{b['remote']:,.0f} per activation. Assumptions: demand doesn't change with price, and a customer who leaves in the first 6 months leaves at month 3. Revenue, not margin."}


ACTION_TEXT = {"order_reopened": "Reopened an order with a code", "consent_granted": "Gave consent", "consent_withdrawn": "Withdrew consent", "kyc_result": "KYC result", "kyc_review_proposed": "Reviewer proposed", "kyc_review_confirmed": "Reviewer confirmed",
               "kyc_review_sent_back": "Reviewer sent back", "rights_correction_requested": "Asked for a correction", "erasure": "Erased their data", "contact_saved": "Saved contact details", "deleted": "Data deleted"}
PURPOSE_TEXT = {consent.KYC: "KYC", consent.UPDATES: "order updates", consent.CALLBACK: "call-back", consent.VOICE: "voice", consent.CONTACT: "contact details"}


def grouped_logs(limit: int = 1000) -> dict:
    """The audit log, one entry per customer, newest activity first. Each opens to show what they did, oldest first.
    The name and number are masked: this page has no login."""
    groups: dict[str, list] = {}
    for r in db.audit_log(limit):
        groups.setdefault(r["actor"], []).append(r)
    out = []
    for actor, rows in groups.items():  # audit_log is newest first, so dict order is too
        steps = [{"when": r["ts"].replace("T", " ")[:19], "action": ACTION_TEXT.get(r["action"], r["action"]), "detail": PURPOSE_TEXT.get(r["detail"], r["detail"]) if r["action"].startswith("consent_") else r["detail"]} for r in reversed(rows)]
        out.append({"ref": "…" + actor[-4:], "who": contacts.masked(actor), "count": len(rows), "last": steps[-1]["action"], "last_when": steps[-1]["when"], "steps": steps})
    return {"note": "Every consent, withdrawal, KYC result, review and deletion, grouped by customer. Names and numbers are masked, and the log itself holds only codes.", "groups": out, "empty": "Nothing logged yet.",
            "headers": ["When", "Action", "Detail"], "count_label": "actions", "last_label": "Latest"}


def evidence(ev: dict, selfcheck: dict) -> dict:
    """Rerunnable proof for judges, next to the KYC self-check. Results come from running the checks now, never from a stored claim."""
    return {"title": "Evidence you can rerun", "note": "Runs the same checks as our CI on this computer, each in its own process with a throwaway database and no AI key, so live data is untouched. The whole run takes under a minute.",
            "button": "Rerun advisor scenarios and security probes", "headers": ["Check", "Result", "Command", "Failures"],
            "rows": [[r["label"], ("✓ " if r["ok"] else "✗ ") + r["result"], r["command"], "; ".join(r["failed"]) or "none"] for r in ev["rows"]],
            "summary": ("All checks passed." if ev["all_passed"] else "Some checks failed: see the table.") if ev["state"] == "done" else None, "ok": ev["all_passed"],
            "unavailable": "The tests folder isn't on this server, so these checks can't run here." if ev["state"] == "unavailable" else None,
            "state": ev["state"], "done": ev["done"], "total": ev["total"], "labels": ev.get("labels", []),
            "kyc": selfcheck,
            "terminal": [["pytest -q", "Every unit, web, KYC and data test"], ["python tests/kyc_stress.py", "KYC on degraded uploads and forged certificates (slow)"], ["python tests/live_check.py 8", "The hardest advisor scenarios with live Gemini (uses free quota)"]]}


def partner(scores: dict, selfcheck: dict, ev: dict | None = None) -> dict:
    """Staff only: a demo with no login, so contact details and identifiers are masked."""
    review = _review(selfcheck)
    return {"title": "Partner queue", "intro": "For specialists and channel partners. A demo view with no login, so contact details and identifiers are masked.",
            "tabs": [{"key": "dash", "label": "Live dashboard"}, {"key": "review", "label": "KYC review"}, {"key": "leads", "label": "Leads and routing"}, {"key": "money", "label": "Payback what-if"}, {"key": "logs", "label": "Logs"}, {"key": "evidence", "label": "Evidence"}],
            "dash": _dashboard(), "review": review, "leads": _leads(scores),
            "money": {"segments": list(insights.payback_base()), "default": insights.MICRO_SEG, **what_if(insights.MICRO_SEG, 0, 0, 0)},
            "logs": grouped_logs(), "evidence": evidence(ev or {"state": "idle", "done": 0, "total": 0, "rows": [], "all_passed": False}, review["selfcheck"]),
            "lang": "en", "nav": {"title": "Accel Business", "data": "Your data", "skip": "Skip to content", "switch": "Customer app", "switch_to": "/advisor", "banner": "Demo. All data is synthetic. Accel Telecom is fictional.", "language": "Language", "error": "Something went wrong. Please try again.", "offline": "We can't reach the server. Check your connection and try again.", "slow": "This is taking too long. Please try again."}, "journey": None}
