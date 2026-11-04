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
    text = PHONE.sub("[phone removed]", text)  # contact detail, not an ID: removed without a warning
    return text, found


_I = r"(ignore|disregard|forget|bypass|override|भूल जाओ|अनदेखा)"
INJECTION = re.compile(
    _I + r".{0,40}(instruction|prompt|rule|निर्देश)|(show|reveal|print|tell|repeat|share|dikhao|batao|बताओ|दिखाओ).{0,30}(system |your |apna |अपना )?(prompt|instructions|निर्देश)"
    r"|system prompt|jailbreak|developer mode|\bdan mode\b|you are now|act as|pretend (to be|you)|set (the )?price to|make (the )?price|apne instructions|अपने निर्देश", re.I)
DISCOUNT = re.compile(
    r"discount|% ?off|\boff\b.*\d|\d+ ?(%|percent|प्रतिशत)|cheaper price|lower the price|reduce the price|best price|last price|free me|for free|mufat|muft|मुफ़्त|मुफ्त|"
    r"कम कर|छूट|डिस्काउंट|kam kar|kam karo|sasta kar|sasta do|chhoot|chhut|negotiat|(at|for|in)\s*(₹|rs\.?\s*)\d|\d+\s*(rupees|rupaye|रुपये)\s*(me|mein|में)|match .*price|haggle|deal do", re.I)
OFF_TOPIC = re.compile(
    r"\b(weather|joke|poem|cricket|ipl|recipe|movie|song|capital of|prime minister|president|election|politics|homework|write (me )?(a|some) |python code|horoscope|stock tip|bitcoin|crypto|mausam|chutkula|gaana)\b|मौसम|चुटकुला|कविता|क्रिकेट|फिल्म", re.I)
FRUSTRATED = re.compile(
    r"useless|waste of time|frustrat|fed up|annoy|stupid|pathetic|worst|talk to (a |an )?(human|person|agent|someone|executive|representative)|real person|call me|call my|human agent|"
    r"bakwas|bekar|bekaar|pareshan|insaan se|kisi se baat|बकवास|बेकार|परेशान|इंसान से|किसी से बात|गुस्सा", re.I)
CONFUSED = re.compile(r"don'?t understand|do not understand|confus|what do you mean|samajh nahi|samjha nahi|nahi samjha|समझ नहीं|समझा नहीं", re.I)
PROMISE_ASK = re.compile(r"install.*(when|date|tomorrow|today|kab)|when.*install|kab (tak|lagega|hoga|aayega)|by tomorrow|कब|free (upgrade|router|install)|guarantee|upgrade free", re.I)
PROCEED = re.compile(r"^\W*(ok(ay)?\W+)?(proceed|go ahead|let'?s go|buy|confirm|book it|place order|done|yes,? (book|proceed)|aage badho|kar do|chalega|theek hai|ठीक है|आगे बढ़ो|बुक करो)\b", re.I)
CHEAPER_ASK = re.compile(r"cheaper|too (costly|expensive)|mehenga|mehnga|sasta|महंगा|सस्ता|budget", re.I)
NOT_IN_CATALOGUE = [
    (re.compile(r"satellite|starlink|vsat|सैटेलाइट", re.I), "satellite internet", "P04"),
    (re.compile(r"landline|लैंडलाइन|epabx|pbx", re.I), "a landline or PBX", "P12"),
    (re.compile(r"\b(dth|tv|ott|netflix|hotstar|iptv|prime video)\b|टीवी", re.I), "TV or OTT plans", None),
    (re.compile(r"\b(laptop|desktop|computer|printer|tablet|phone handset|mobile phone)s?\b", re.I), "hardware such as computers or phones", "P19"),
    (re.compile(r"\b(erp|tally|crm|sap|payroll|accounting software)\b", re.I), "ERP or accounting software", "P19"),
    (re.compile(r"\b(vpn|mpls)\b", re.I), "VPN or MPLS", "P10"),
    (re.compile(r"\b(loan|insurance|credit card|payment gateway)\b|लोन|बीमा", re.I), "financial products", None),
    (re.compile(r"\b(10|25|50) ?g(bps)?\b|dark fibre|data ?cent(er|re)|colocation", re.I), "that kind of data-centre or ultra-high-speed service", "P06"),
    (re.compile(r"\b(alexa|drone|solar|ai chatbot)\b", re.I), "that service", None),
]


def out_of_catalogue(text: str):
    for rx, label, near in NOT_IN_CATALOGUE:
        if rx.search(text): return label, near
    return None


AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+)|(\d[\d,]{2,})\s*(?:rupees?|रुपये|rupaye)", re.I)
BAD_PROMISE = re.compile(r"guarantee|free upgrade|install(ed)? (by|tomorrow|today)|discount|गारंटी|मुफ़्त|मुफ्त|\bfree\b", re.I)
CODE = re.compile(r"\bP\d{2}\b")


def allowed_amounts(q: Quote | None, alt: Quote | None = None) -> set[int]:
    out = set()
    for x in (q, alt):
        if x:
            out |= {x.monthly, x.setup}
            for l in x.lines: out |= {l.unit_price, l.monthly, l.setup}
    return out


def check_reply(reply: str, q: Quote | None, alt: Quote | None = None, excluded: set[str] = frozenset()) -> list[str]:
    """Empty list means the reply is safe to show. Any mismatch forces regeneration."""
    probs = []
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
    if BAD_PROMISE.search(reply): probs.append("unsupported promise")
    if redact(reply)[1]: probs.append("identifier in reply")
    return probs
