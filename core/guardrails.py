"""Input screening and output validation for the advisor."""
from __future__ import annotations
import re
from .catalogue import catalogue
from .pricing import Quote

AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
GSTIN = re.compile(r"\b\d{2}[A-Za-z]{5}\d{4}[A-Za-z][0-9A-Za-z]{3}\b")
PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
IFSC = re.compile(r"\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b")
BANK = re.compile(r"(?:account|a/c|acct|khata|खाता|bank|बैंक)[^\d]{0,25}(\d{9,18})", re.I)
LONG_DIGITS = re.compile(r"(?<!\d)\d{13,18}(?!\d)")
EMAIL_ADDR = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<![\d])(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)")


def redact(text: str) -> tuple[str, list[str]]:
    """Remove identifiers before anything is stored, logged or sent to the LLM."""
    found = []
    def sub(rx, tag, s):
        s2, n = rx.subn(f"[{tag} removed]", s)
        if n: found.append(tag)
        return s2
    text = sub(GSTIN, "GSTIN", text)
    text = sub(BANK, "bank number", text)
    text = sub(AADHAAR, "Aadhaar", text)
    text = sub(PAN, "PAN", text)
    text = sub(IFSC, "IFSC", text)
    text = sub(LONG_DIGITS, "bank number", text)
    text = EMAIL_ADDR.sub("[contact removed]", PHONE.sub("[contact removed]", text))  # the call-back form is the place for these
    return text, found


_I = r"(ignore|disregard|forget|bypass|override|भूल जाओ|अनदेखा)"
INJECTION = re.compile(
    _I + r".{0,40}(instruction|prompt|rule|निर्देश)|(show|reveal|print|tell|repeat|share|dikhao|batao|बताओ|दिखाओ).{0,30}(system |your |apna |अपना )?(prompt|instructions|निर्देश)"
    r"|(instruction|prompt|rule|निर्देश)\w*.{0,30}(bhool|bhula|ignore|भूल|अनदेखा)|\bset\b.{0,20}\bprice\b|^\s*system\s*:|you are (the |an? )?\w+ now|\bi am (the |an? )?(admin|developer)\b|recommend .{0,30}\bfree\b|system prompt|jailbreak|developer mode|\bdan mode\b|you are now|\bact as\b|pretend (to be|you)|set (the )?price to|make (the )?price|apne instructions|अपने निर्देश", re.I)
DISCOUNT = re.compile(
    r"discount|% ?off|free (kar|de|do)\b|\boff\b.*\d|\d+ ?(%|percent|प्रतिशत)|cheaper price|lower the price|reduce the price|best price|last price|free me|for free|mufat|muft|मुफ़्त|मुफ्त|"
    r"कम कर|छूट|डिस्काउंट|kam kar|kam karo|sasta kar|sasta do|chhoot|chhut|negotiat|(at|for|in)\s*(₹|rs\.?\s*)\d|\d+\s*(rupees|rupaye|रुपये)\s*(me|mein|में)|match .*price|match (that|this|it)\b|competitor.{0,30}(pay|charg|price|\d)|haggle|deal do", re.I)
OFF_TOPIC = re.compile(
    r"\b(weather|joke|poem|cricket|ipl|recipe|movie|song|capital of|prime minister|president|election|politics|homework|write (me )?(a|some) |python code|horoscope|stock tip|bitcoin|crypto|mausam|chutkula|gaana)\b|मौसम|चुटकुला|कविता|क्रिकेट|फिल्म", re.I)
FRUSTRATED = re.compile(
    r"\bspecialist\b|विशेषज्ञ|useless|waste of time|frustrat|fed up|annoy|stupid|pathetic|worst|talk to (a |an )?(human|person|agent|someone|executive|representative)|real person|please call me|call me back|have someone call|human agent|"
    r"bakwas|bekar|bekaar|pareshan|insaan se|kisi se baat|बकवास|बेकार|परेशान|इंसान से|किसी से बात|गुस्सा", re.I)
CONFUSED = re.compile(r"don'?t understand|do not understand|confus|what do you mean|what does (that|it|this) mean|\bmatlab\b|मतलब|samajh nahi|samjha nahi|nahi samjha|समझ नहीं|समझा नहीं", re.I)
PROMISE_ASK = re.compile(r"how long|kitne din|कितने दिन|install.*(when|date|tomorrow|today|kab)|when.*install|kab (tak|lagega|hoga|aayega)|by tomorrow|कब|free (upgrade|router|install)|guarantee|upgrade free", re.I)
PROCEED = re.compile(r"^\W*(ok(ay)?\W+)?(proceed|go ahead|let'?s go|buy|confirm|book it|place order|done|yes,? (book|proceed)|aage badho|kar do|chalega|theek hai|ठीक है|आगे बढ़ो|बुक करो)\b", re.I)
CHEAPER_ASK = re.compile(r"cheaper|too (costly|expensive)|mehenga|mehnga|sasta|महंगा|सस्ता|budget", re.I)
FAQ_TAX = re.compile(r"(gst|जीएसटी|tax|टैक्स)\W+(\w+\W+){0,3}(extra|on top|included?|inclusive|exclusive|separate|alag|lagega|शामिल|अलग)|(charge|include|including|excluding|add)\w*\W+(\w+\W+){0,2}(gst|जीएसटी|tax|टैक्स)", re.I)
FAQ_CONTRACT = re.compile(r"\bcontract\b|lock.?in|अनुबंध|कॉन्ट्रैक्ट", re.I)
FAQ_SETUP = re.compile(r"setup|set up (fee|cost|charge)|install\w* (fee|charge|cost)|one.?time|sign.?up fee|lagwane ka|सेटअप|इंस्टॉलेशन", re.I)
CHEAPEST = re.compile(r"cheapest|lowest (price|plan)|sabse sasta|सबसे सस्ता|(what|which) plans|plans? (do you|kya)|kya plans?|price of|how much (is|does|for)|kitne ka|kitna (price|paisa)|कितने का|क्या प्लान", re.I)
GSTIN_ASK = re.compile(r"(what|kya|क्या).{0,15}(gst|जीएसटी)|(gst|जीएसटी).{0,15}(kya|क्या|meaning|mean\b)", re.I)
RESTART = re.compile(r"start (?:\w+ )?(?:over|again|afresh)|restart|begin again|reset|new chat|from the (?:beginning|start)|from scratch|shuru se|phir se shuru|dobara shuru|fir se shuru|naye sire|शुरू से|फिर से शुरू|दोबारा शुरू", re.I)
NOT_RESTART = re.compile(r"router|modem|device|machine|internet|wi-?fi|connection|business|shop|dukaan|राउटर|मशीन|इंटरनेट", re.I)
WHY_ASK = re.compile(r"why (do|are|is|should|does)\b.{0,30}(ask|need|want|know|matter|question|this|that)|why (this|that)\b|kyun (pooch|chahiye|jaanna)|kyu (pooch|chahiye)|क्यों (पूछ|चाहिए)", re.I)
PAUSE = re.compile(r"^\W*(stop|not now|later|bye|goodbye|leave it|rehne do|baad mein|बाद में|रहने दो)\W*$|stop asking|too many questions|enough questions|(sawal|question)\w* (mat|band|bahut)|सवाल (मत|बंद|बहुत)", re.I)
REGIONAL = re.compile(r"[\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F]")
NOT_IN_CATALOGUE = [
    (re.compile(r"satellite|starlink|vsat|सैटेलाइट", re.I), "satellite internet", "P04"),
    (re.compile(r"landline|लैंडलाइन|epabx|pbx", re.I), "a landline or PBX", "P12"),
    (re.compile(r"\b(dth|tv|ott|netflix|hotstar|iptv|prime video)\b|टीवी", re.I), "TV or OTT plans", None),
    (re.compile(r"\b(laptop|desktop|computer|printer|tablet|phone handset|mobile phone)s?\b", re.I), "hardware such as computers or phones", "P19"),
    (re.compile(r"\b(erp|tally|crm|sap|payroll|accounting software)\b", re.I), "ERP or accounting software", None),
    (re.compile(r"\b(vpn|mpls)\b", re.I), "VPN or MPLS", "P10"),
    (re.compile(r"\b(loan|insurance|credit card|payment gateway)\b|लोन|बीमा", re.I), "financial products", None),
    (re.compile(r"\b(10|25|50) ?g(bps)?\b|dark fibre|data ?cent(er|re)|colocation", re.I), "that kind of data-centre or ultra-high-speed service", "P06"),
    (re.compile(r"\b(alexa|drone|solar|ai chatbot)\b", re.I), "that service", None),
]


def out_of_catalogue(text: str):
    for rx, label, near in NOT_IN_CATALOGUE:
        if rx.search(text): return label, near
    return None


AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr|रु\.?)\s*([\d,]+)|(\d[\d,]{2,})\s*(?:rupees?|रुपये|rupaye|per month|a month|/month|/mo\b|प्रति माह)", re.I)
NUMBER = re.compile(r"\d[\d,]*")
BAD_PROMISE = re.compile(r"budget.friendly|affordable|\bbest\b|perfect|सबसे बढ़िया|सबसे अच्छा|sabse (badhiya|accha|achha)|guarantee|free upgrade|install(ed)? (by|tomorrow|today)|discount|गारंटी|मुफ़्त|मुफ्त|\bfree\b", re.I)
CODE = re.compile(r"\bP\d{2}\b")


def allowed_amounts(q: Quote | None, alt: Quote | None = None) -> set[int]:
    out = set()
    for x in (q, alt):
        if x:
            out |= {x.monthly, x.setup}
            for l in x.lines: out |= {l.unit_price, l.monthly, l.setup}
    return out


CHAT_BANNED = re.compile(r"₹|\brs\.?\b|\binr\b|price|cost|cheap|discount|offer|free\b|guarantee|promise|tomorrow|today|\bweek|\bmonth|\bdays?\b|install|available|recommend|suggest|"
                         r"कीमत|दाम|छूट|मुफ़्त|मुफ्त|गारंटी|वादा|कल\b|आज\b|हफ़्ते|महीने|दिन\b|सुझा|sasta|keemat|daam|chhoot|muft|mahine|hafte|\bdin\b|\bkal\b|\baaj\b", re.I)
CHAT_PRODUCT_WORDS = re.compile(r"fibre|fiber|broadband|leased|airfiber|\b5g\b|\b4g\b|postpaid|\bsim\b|cctv|firewall|sd-?wan|whatsapp|फाइबर|ब्रॉडबैंड|सिम|सीसीटीवी|व्हाट्सएप", re.I)


def check_chat(reply: str, allowed_names: tuple[str, ...] = ()) -> list[str]:
    """Free-form small talk from the LLM may decide and promise nothing. Empty list means safe to show."""
    probs, text = [], reply
    for n in allowed_names: text = re.sub(re.escape(n), " ", text, flags=re.I)
    if len(reply.split()) > 45: probs.append("too long")
    if re.search(r"\d|[०-९]", text): probs.append("number")
    if CHAT_BANNED.search(text): probs.append("commercial wording")
    if CODE.search(reply): probs.append("internal code")
    low = text.lower()
    if any(p.name.lower() in low for p in catalogue().values()): probs.append("product not in plan")
    if not allowed_names and CHAT_PRODUCT_WORDS.search(text): probs.append("product before a plan")
    if redact(reply)[1] or "[contact removed]" in redact(reply)[0]: probs.append("identifier")
    return probs


def dropped_facts(reply: str, draft: str, alt: Quote | None, excluded_names: list[str]) -> list[str]:
    """A rewrite must keep the cheaper option and every exclusion the checked draft showed."""
    probs = []
    if alt and f"{alt.monthly:,}" in draft and f"{alt.monthly:,}" not in reply and str(alt.monthly) not in reply: probs.append("cheaper option dropped")
    probs += [f"exclusion {n} dropped" for n in excluded_names if n in draft and n.lower() not in reply.lower()]
    return probs


def check_reply(reply: str, q: Quote | None, alt: Quote | None = None, excluded: set[str] = frozenset(), draft: str | None = None) -> list[str]:
    """Empty list means the reply is safe to show. Any mismatch forces regeneration.
    With `draft`, every number in a rewrite must come from the checked draft, so no new dates, days or prices."""
    probs = []
    if draft is not None:
        known = {n.replace(",", "") for n in NUMBER.findall(draft)}
        probs += [f"number {n} not in draft" for n in NUMBER.findall(reply) if n.replace(",", "") not in known]
    allowed = allowed_amounts(q, alt)
    for m in AMOUNT.finditer(reply):
        v = int((m.group(1) or m.group(2)).replace(",", "") or 0)
        if v not in allowed: probs.append(f"amount {v} not from pricing engine")
    named = {l.name for x in (q, alt) if x for l in x.lines}
    for p in catalogue().values():
        if p.name.lower() in reply.lower() and p.name not in named and p.id not in excluded:
            probs.append(f"product {p.name} not in recommendation")
    if q and not re.search(rf"\b{q.monthly:,}\b|\b{q.monthly}\b", reply): probs.append("monthly price missing")
    for n in named:
        if q and n in {l.name for l in q.lines} and n.lower() not in reply.lower(): probs.append(f"{n} missing")
    if CODE.search(reply): probs.append("internal product code shown")
    if BAD_PROMISE.search(re.sub(r"toll[- ]free", "", reply, flags=re.I)): probs.append("unsupported promise")
    if redact(reply)[1]: probs.append("identifier in reply")
    return probs
