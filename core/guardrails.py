"""Input screening and output validation for the advisor."""
from __future__ import annotations
import re
from .catalogue import catalogue
from .pricing import Quote

_GAP = r"[\s.-]?"
AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
GSTIN = re.compile(rf"\b\d{{2}}{_GAP}[A-Za-z]{{5}}{_GAP}\d{{4}}{_GAP}[A-Za-z]{_GAP}[0-9A-Za-z]{_GAP}[0-9A-Za-z]{_GAP}[0-9A-Za-z]\b")
UDYAM_NO = re.compile(rf"\b(?:udyam{_GAP})[A-Za-z]{{2}}{_GAP}\d{{2}}{_GAP}\d{{6,7}}\b|\b[A-Za-z]{{2}}-\d{{2}}-\d{{6,7}}\b", re.I)
PAN = re.compile(rf"\b[A-Za-z]{{5}}{_GAP}\d{{4}}{_GAP}[A-Za-z]\b")
VOTER_ID = re.compile(r"\b[A-Za-z]{3}\d{7}\b")
IFSC = re.compile(r"\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b")
BANK = re.compile(r"(?:account|a/c|acct|khata|खाता|bank|बैंक)[^\d]{0,25}(\d(?:[\s-]?\d){8,17})", re.I)
LONG_DIGITS = re.compile(r"(?<!\d)\d{13,18}(?!\d)")
EMAIL_ADDR = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
UPI_ID = re.compile(r"\b[\w.-]+@[a-zA-Z][a-zA-Z0-9]{1,15}\b")
PHONE = re.compile(r"(?<![\d])(?:\+?91[ -]?)?[6-9](?:[\s.-]?\d){9}(?!\d)")
ANY_LONG_NUMBER = re.compile(r"(?<![\d-])\+?\d(?:[\s.()-]{0,2}\d){7,}(?![\d-])")  # however spaced: a phone, account or similar number
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NAME_GIVEN = re.compile(r"\b(?:my name is|name is|mera naam)\s+[^\W\d_]+(?:\s+(?!and\b|aur\b|hai\b|i\b|in\b)[^\W\d_]+){0,2}|मेरा नाम\s+\S+(?:\s+(?!है)\S+)?", re.I)
_INDIC_DIGIT = re.compile("[०-९০-৯੦-੯૦-૯୦-୯௦-௯౦-౯೦-೯൦-൯]")


def latin_digits(text: str) -> str:
    """Every Indic script's digits, written as 0-9, so one set of patterns covers them all."""
    return _INDIC_DIGIT.sub(lambda m: str((ord(m.group()) & 0xF) - 6), text)


def redact(text: str) -> tuple[str, list[str]]:
    """Remove identifiers before anything is stored, logged or sent to the LLM."""
    found = []
    def sub(rx, tag, s):
        s2, n = rx.subn(f"[{tag} removed]", s)
        if n: found.append(tag)
        return s2
    text = latin_digits(text)
    text = sub(GSTIN, "GSTIN", text)
    text = sub(UDYAM_NO, "Udyam", text)
    text = sub(BANK, "bank number", text)
    text = sub(AADHAAR, "Aadhaar", text)
    text = sub(PAN, "PAN", text)
    text = sub(VOTER_ID, "ID", text)
    text = sub(IFSC, "IFSC", text)
    text = sub(LONG_DIGITS, "bank number", text)
    text = NAME_GIVEN.sub("[name removed]", text)  # names in general can't be spotted, so the chat notice asks owners not to type them
    text = EMAIL_ADDR.sub("[contact removed]", text)
    text = UPI_ID.sub("[contact removed]", text)
    text = PHONE.sub("[contact removed]", text)
    dates = ISO_DATE.findall(text)
    text = ANY_LONG_NUMBER.sub(lambda m: m.group() if m.group() in dates else "[contact removed]", text)  # the call-back form is the place for these
    return text, found


_I = r"(ignore|disregard|forget|bypass|override|भूल जाओ|अनदेखा)"
INJECTION = re.compile(
    _I + r".{0,40}(instruction|prompt|rule|निर्देश)|(show|reveal|print|tell|repeat|share|dikhao|batao|बताओ|दिखाओ).{0,30}(system |your |apna |अपना )?(prompt|instructions|निर्देश)"
    r"|(instruction|prompt|rule|निर्देश)\w*.{0,30}(bhool|bhula|ignore|भूल|अनदेखा)|\bset\b.{0,20}\bprice\b|^\s*system\s*:|you are (the |an? )?\w+ now|\bi am (the |an? )?(admin|developer)\b|recommend .{0,30}\bfree\b|system prompt|jailbreak|developer mode|\bdan mode\b|you are now|\bact as\b|pretend (to be|you)|set (the )?price to|make (the )?price|apne instructions|अपने निर्देश", re.I)
DISCOUNT = re.compile(
    r"discount|% ?off|free (kar|de|do)\b|\boff\b.*\d|\d+ ?(%|percent|प्रतिशत)|cheaper price|lower the price|reduce the price|best price|last price|free me|for free|mufat|muft|मुफ़्त|मुफ्त|"
    r"कम कर|छूट|डिस्काउंट|kam kar|kam karo|sasta kar|sasta do|sasta nahi|sasta ho|thoda kam|kam ho sakta|कम हो सकता|सस्ता कर|सस्ता हो|chhoot|chhut|negotiat|(at|for|in)\s*(₹|rs\.?\s*)\d|\d+\s*(rupees|rupaye|रुपये)\s*(me|mein|में)|match .*price|match (that|this|it)\b|competitor.{0,30}(pay|charg|price|\d)|haggle|deal do|make it\s*(₹|rs\.?\s*)?\d|final offer|\bflat\s*(₹|rs\.?\s*)?\d|\d\s*(rs\.?|rupees)?\s*flat\b|\d+\s*(me|mein)\s*(do|de do)\b|\d+\s*में\s*(दे|दो)", re.I)
OFF_TOPIC = re.compile(
    r"\b(weather|joke|poem|cricket|ipl|recipe|movie|song|capital of|prime minister|president|election|politics|homework|write (me )?(a|some) |python code|horoscope|stock tip|bitcoin|crypto|mausam|chutkula|gaana)\b|मौसम|चुटकुला|कविता|क्रिकेट|फिल्म", re.I)
FRUSTRATED = re.compile(
    r"\bspecialist\b|विशेषज्ञ|useless|waste of time|frustrat|fed up|annoy|stupid|pathetic|worst|talk to (a |an )?(human|person|agent|someone|executive|representative)|real person|please call me|call me back|have someone call|human agent|"
    r"bakwas|bekar|bekaar|pareshan|insaan se|kisi se baat|बकवास|बेकार|परेशान|इंसान से|किसी से बात|गुस्सा", re.I)
CONFUSED = re.compile(r"don'?t understand|do not understand|confus|what do you mean|what does (that|it|this) mean|\bmatlab\b|मतलब|samajh nahi|samjha nahi|nahi samjha|समझ नहीं|समझा नहीं", re.I)
PROMISE_ASK = re.compile(r"how long|kitne din|कितने दिन|install.*(when|date|tomorrow|today|kab)|when.*install|kab (tak|lagega|hoga|aayega)|by tomorrow|कब|free (upgrade|router|install)|guarantee|upgrade free|फ्री|फ़्री|अपग्रेड", re.I)
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
    (re.compile(r"\b(dth|tv|ott|netflix|hotstar|iptv|prime video)\b(?! (shop|store|repair|service|centre|center|showroom|dealer))|(?<!सी)टीवी", re.I), "TV or OTT plans", None),
    (re.compile(r"\b(laptop|desktop|computer|printer|tablet|phone handset|mobile phone)s?\b(?! (shop|store|repair|service|centre|center|institute|class|classes|training|dealer|showroom|press|cover|covers|accessories|parts))", re.I), "hardware such as computers or phones", "P19"),
    (re.compile(r"\b(erp|tally|crm|sap|payroll|accounting software)\b", re.I), "ERP or accounting software", None),
    (re.compile(r"\b(vpn|mpls)\b", re.I), "VPN or MPLS", "P10"),
    (re.compile(r"\b(loan|insurance|credit card|payment gateway)\b(?! (agency|agencies|agent|agents|advisor|advisors|adviser|broker|brokers|company|office|firm|consultant|consultants|business|shop|center|centre))|लोन|बीमा(?! (एजेंसी|एजेंट|सलाहकार|कंपनी))", re.I), "financial products", None),
    (re.compile(r"\b(10|25|50) ?g(bps)?\b|dark fibre|data ?cent(er|re)|colocation", re.I), "that kind of data-centre or ultra-high-speed service", "P06"),
    (re.compile(r"\b(alexa|drone|solar|ai chatbot)\b", re.I), "that service", None),
]


def out_of_catalogue(text: str):
    for rx, label, near in NOT_IN_CATALOGUE:
        if rx.search(text): return label, near
    return None


AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr|रु\.?)\s*([\d,]+)|(\d[\d,]{2,})\s*(?:rupees?|रुपये|rupaye|per month|a month|/month|/mo\b|प्रति माह)", re.I)
NUMBER = re.compile(r"\d[\d,]*")
BAD_PROMISE = re.compile(r"सबसे सही|sabse sahi|great fit|just for you|built for you|tailored|friendlier|budget.friendly|affordable|\bbest\b|perfect|सबसे बढ़िया|सबसे अच्छा|sabse (badhiya|accha|achha)|guarantee|free upgrade|install(ed)? (by|tomorrow|today)|discount|गारंटी|मुफ़्त|मुफ्त|\bfree\b", re.I)
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
    if "{" in reply or "}" in reply: probs.append("not a sentence")
    if any(ch.isdigit() for ch in text) or _NUMBER_WORD.search(text): probs.append("number")
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
        if re.match(r"\W*(hi\b|hello\b|namaste\b|नमस्ते)", reply, re.I) and not re.match(r"\W*(hi\b|hello\b|namaste\b|नमस्ते)", draft, re.I): probs.append("added greeting")
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

ANSWER_BANNED = re.compile(r"सबसे सही|sabse sahi|right step|right choice|discount|\bfree\b|guarantee|promise[sd]?\b|tomorrow|today|next week|recommend|suggest|you should|you must|\bbest\b|perfect|great fit|\beligible\b|\bqualif|sign up|मुफ़्त|मुफ्त|छूट|गारंटी|वादा|सुझाव|सिफ़ारिश|muft|guarantee|sifarish", re.I)


def check_answer(reply: str, facts: str) -> list[str]:
    """A free-form LLM answer may only repeat facts it was given, and may not decide or promise anything. Empty means safe."""
    probs, known = [], {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", facts)}
    if len(reply.split()) > 70: probs.append("too long")
    for n in re.findall(r"\d[\d,]*\.?\d*", reply):
        if n.rstrip(".,").replace(",", "") not in known: probs.append(f"number {n} not in facts")
    if any(ch.isdigit() and not ch.isascii() for ch in reply): probs.append("number in other script")
    if _NUMBER_WORD.search(reply): probs.append("spelled out an amount")
    if ANSWER_BANNED.search(reply): probs.append("decides or promises")
    if CODE.search(reply): probs.append("internal code")
    if "{" in reply or "}" in reply: probs.append("not a sentence")
    if redact(reply)[1] or "[contact removed]" in redact(reply)[0]: probs.append("identifier")
    return probs


# A request for something built to order, as opposed to a catalogue product. "customer" must never match.
CUSTOM_NEED = re.compile(r"\bcustom(?:i[sz]ed)?\b|\bbespoke\b|\btailor[- ]?made\b|\bspecial(?:i[sz]ed)? (?:setup|solution|requirements?|needs?)\b|\bscada\b|\bplc\b|कस्टम|अनुकूलित", re.I)
NOT_CUSTOM = re.compile(r"\b(?:no|not|nothing|without|don'?t (?:need|want)(?: any(?:thing)?)?)\s+(?:\w+\s+)?custom", re.I)


def asks_custom(text: str) -> bool:
    return bool(CUSTOM_NEED.search(text)) and not NOT_CUSTOM.search(text)


# --- Numbers and product names in LLM wording. Sentences come back with {{slots}} and code fills them in,
# so whatever the language, the model never types a price, a count or a product name itself. ---
_SLOT = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
_VALUE = re.compile(r"₹\s?\d[\d,]*(?:\.\d+)?|\d+G\b|\d[\d,]*(?:\.\d+)?(?:\s?(?:Mbps|Gbps|GB|TB|%))?")
_MONEY = re.compile(r"₹|\brs\.?(?=\s|\d|$)|\binr\b|rupee|rupay|रुपय|रुपए|रुपये|\$|%|percent|per cent|प्रतिशत|फीसदी", re.I)
_NUMBER_WORD = re.compile(r"\b(ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|lac|crore|sau|hazaar|hazar|pachas|sattar|assi|nabbe)\b|(?<![\u0900-\u097f])(?:दस|बीस|तीस|चालीस|पचास|साठ|सत्तर|अस्सी|नब्बे|हज़ार|हजार|लाख|करोड़)(?![\u0900-\u097f])", re.I)
_PROMISE = re.compile(r"(?<!feel )\bfree\b|\bwaive[ds]?\b|\bno charge\b|\bguarantee[ds]?\b|half off|half price|\bmuft\b|मुफ़्त|मुफ्त|गारंटी|\btomorrow\b|next week|\bkal tak\b|कल तक|\bbetter than\b|बेहतर है", re.I)


def mask_slots(draft: str) -> tuple[str, dict[str, str]]:
    """Swap every product name and number in checked text for a slot. Returns (masked text, slot -> value)."""
    slots, seen = {}, {}
    def slot(value: str, stem: str) -> str:
        if value not in seen:
            seen[value] = f"{stem}{sum(k.startswith(stem) for k in slots) + 1}"
            slots[seen[value]] = value
        return "{{" + seen[value] + "}}"
    out = draft
    for name in sorted((p.name for p in catalogue().values()), key=len, reverse=True):
        if name in out: out = out.replace(name, slot(name, "NAME"))
    parts = re.split(r"(\{\{[A-Z0-9_]+\}\})", out)
    return "".join(x if x.startswith("{{") else _VALUE.sub(lambda m: slot(m.group(), "VALUE"), x) for x in parts), slots


def fill_slots(text: str, slots: dict[str, str]) -> str:
    return _SLOT.sub(lambda m: slots.get(m.group(1), ""), text)


def check_slots(reply: str, slots: dict[str, str]) -> list[str]:
    """Empty means the model wrote only words, used every slot it was given, and invented none."""
    probs, used = [], {m.group(1) for m in _SLOT.finditer(reply)}
    if not reply.strip(): return ["empty"]
    if used - set(slots): probs.append("unknown slot")
    if set(slots) - used: probs.append("dropped a slot")
    own = _SLOT.sub(" ", reply)
    if "{" in own or "}" in own: probs.append("broken slot")
    if any(ch.isdigit() for ch in own): probs.append("typed a number")
    if _MONEY.search(own): probs.append("typed an amount")
    if _NUMBER_WORD.search(own): probs.append("spelled out an amount")
    if _PROMISE.search(own): probs.append("promise or comparison")
    if CODE.search(own): probs.append("internal code")
    low = own.lower()
    if any(p.name.lower() in low for p in catalogue().values()): probs.append("typed a product name")
    if redact(own)[1]: probs.append("identifier")
    return probs
