"""Conversation logic. Code decides the next step and every product and price."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from . import guardrails as G, llm
from .catalogue import catalogue
from .kyc import registry
from .rules import Profile, Recommendation, recommend, reason_text, NEEDS, MICRO, QUESTION_VALUES, question_matters, gstin_product, alt_diff, mentionable

TIER1 = {"delhi": "दिल्ली", "mumbai": "मुंबई", "bengaluru": "बेंगलुरु", "bangalore": "बैंगलोर", "chennai": "चेन्नई", "kolkata": "कोलकाता", "hyderabad": "हैदराबाद", "pune": "पुणे", "ahmedabad": "अहमदाबाद",
         "gurgaon": "गुड़गांव", "gurugram": "गुरुग्राम", "noida": "नोएडा"}
TIER2 = {"kochi": "कोच्चि", "ludhiana": "लुधियाना", "nagpur": "नागपुर", "jaipur": "जयपुर", "visakhapatnam": "विशाखापत्तनम", "vizag": "वाइज़ैग", "lucknow": "लखनऊ", "bhopal": "भोपाल", "surat": "सूरत",
         "mysuru": "मैसूर", "mysore": "मैसूरु", "coimbatore": "कोयंबटूर", "indore": "इंदौर", "nashik": "नासिक", "vadodara": "वडोदरा", "patna": "पटना"}
# Data covers tier 1 and 2 only; these are recognised so we can say honestly that we don't serve them yet.
TIER3 = {"sitapur": "सीतापुर", "hardoi": "हरदोई", "ballia": "बलिया", "buxar": "बक्सर", "barmer": "बाड़मेर", "chhindwara": "छिंदवाड़ा", "darbhanga": "दरभंगा", "gaya": "गया", "bareilly": "बरेली", "sagar": "सागर",
         "satara": "सातारा", "jhansi": "झांसी", "ratlam": "रतलाम", "hisar": "हिसार", "karnal": "करनाल", "muzaffarpur": "मुजफ्फरपुर"}
TIER2.update({"kanpur": "कानपुर", "agra": "आगरा", "varanasi": "वाराणसी", "chandigarh": "चंडीगढ़", "rajkot": "राजकोट", "amritsar": "अमृतसर", "ranchi": "रांची", "raipur": "रायपुर", "guwahati": "गुवाहाटी", "bhubaneswar": "भुवनेश्वर", "dehradun": "देहरादून", "madurai": "मदुरै", "vijayawada": "विजयवाड़ा", "thiruvananthapuram": "तिरुवनंतपुरम", "aurangabad": "औरंगाबाद", "meerut": "मेरठ"})
TIER1.update({"bombay": "बॉम्बे", "calcutta": "कलकत्ता", "madras": "मद्रास"})
TIER2.update({"cochin": "कोचीन", "baroda": "बड़ौदा", "trivandrum": "त्रिवेंद्रम"})
CITY_TIER = {**{c: 1 for c in TIER1}, **{c: 2 for c in TIER2}, **{c: 3 for c in TIER3}}
HI_CITY = {v: k for d in (TIER1, TIER2, TIER3) for k, v in d.items()}

# These are also everyday words or names ("internet band ho gaya", "Sagar Medical"), so they need place context.
AMBIGUOUS = {"gaya", "sagar"}
NOT_PLACE = {"the", "our", "my", "one", "english", "hindi", "hinglish", "town", "tier", "metro", "india", "business", "this", "that", "all", "each", "small", "home", "night", "morning", "evening", "day", "daytime", "office", "shop", "store", "clinic", "market", "future", "present", "total", "general", "case", "peak", "summer", "winter", "rain", "rains", "monsoon", "advance", "front", "addition", "cash", "person", "bulk", "touch", "time", "charge", "short", "mind", "place", "life", "years", "months", "days", "house", "area", "city", "village", "both", "any", "every", "some", "there", "here", "which", "what", "order", "you", "your", "scratch", "accel", "customers", "them", "us", "it", "need", "just", "only", "last", "next", "first"}
ASKING = re.compile(r"\?|^\W*(what|why|how|which|when|where|who|kya|kaise|kyun|क्या|कैसे|क्यों)\b|^\W*$")  # a question or nothing is not an answer
VAGUE = re.compile(r"not sure|no idea|don'?t know|dont know|\bidk\b|pata nahi|pata nahin|kuch bhi|jo best|aap batao|you (decide|tell|suggest)|whatever|anything|पता नहीं|कुछ भी|आप बताओ|आप बताइए|^\W*(hi|hello|hey|namaste|नमस्ते)\W*$", re.I)
GST_WORD = r"(?:gst(?:in| number| no| registration)?|जीएसटी(?:आईएन)?)"
GST_BAD = re.compile(rf"{GST_WORD}\W+(\w+\W+){{0,3}}(cancel|suspend|expired|revoked|band ho|applied|pending|in process|not received|रद्द|निलंबित)|(cancel\w*|suspend\w*|expired|revoked)\W+(\w+\W+){{0,2}}{GST_WORD}|appl(y|ied)\w*\W+(for\W+)?{GST_WORD}", re.I)
GST_UNSURE = re.compile(rf"(not sure|don'?t know|dont know|no idea|pata nahi|unsure|पता नहीं).{{0,30}}{GST_WORD}|{GST_WORD}.{{0,30}}(not sure|don'?t know|pata nahi|पता नहीं)", re.I)
EXISTING = re.compile(r"(already|existing|pehle se)\W+(\w+\W+){0,3}(internet|broadband|fibre|fiber|wi-?fi|net connection)|(?<!don't )(?<!dont )\b(we|i) (have|use|got) (an? |our )?(?!no\b|not\b|poor\b|bad\b|slow\b)(\w+ )?(internet|broadband|fibre|fiber)\b|(internet|broadband|fibre|fiber|wi-?fi) (already|pehle se)|पहले से.{0,20}(इंटरनेट|ब्रॉडबैंड)|(इंटरनेट|ब्रॉडबैंड).{0,10}पहले से", re.I)
NEG_BEFORE = re.compile(r"(don'?t|dont|do not)\s+(want|need|require)\b|\bno need\b|\b(remove|drop|delete|cancel|skip|exclude)\b|(?<!can't work )(?<!cannot work )\bwithout\b|\b(hatao|hata do)\b|हटाओ|हटा दो", re.I)
NEG_AFTER = re.compile(r"^\W*(?:\S+\s+){0,2}?(nahi chahiye|nahin chahiye|nahi lena|mat (?:do|lagao|dena)|not needed|not required|hatao|hata do|ki zaroorat nahi|की ज़रूरत नहीं|नहीं चाहिए|हटाओ|हटा दो)", re.I)
CLAUSE = re.compile(r"[,.;]|\bbut\b|\bonly\b|\bjust\b|\bsirf\b|\bbas\b|\blekin\b|लेकिन|सिर्फ")


def _negated(t: str, start: int, end: int) -> bool:
    before = CLAUSE.split(t[:start])[-1]
    # A bare "no internet" means they lack it, so "no X" only declines products other than a connection.
    bare_no = bool(re.search(r"\b(no|not)\s+$", before)) and not re.match(r"internet|broadband|fibre|fiber|net\b|wi-?fi", t[start:end])
    return bool(bare_no or NEG_BEFORE.search(before) or NEG_AFTER.search(CLAUSE.split(t[end:])[0]))


def _find_city(t: str, text: str, awaiting: str | None) -> str | None:
    """Best city in the message. "in X" outranks a bare mention, so "Delhi Sweets in Pune" means Pune."""
    bare = awaiting == "city" and len(t.split()) <= 3
    hits = []
    for c in CITY_TIER:
        for m in re.finditer(rf"\b{c}\b", t):
            marked = bool(re.search(r"\b(in|at|from|near|to)\s+$", t[:m.start()]) or re.match(r"\s*(mein|me|se|city)\b", t[m.end():]))
            if c in AMBIGUOUS and not (marked or bare): continue
            hits.append((0 if marked else 1, m.start(), c))
    for hi, c in HI_CITY.items():
        i = text.find(hi)
        if i < 0: continue
        marked = bool(re.match(r"\s*(में|से|शहर)", text[i + len(hi):]))
        if c in AMBIGUOUS and not (marked or bare): continue
        hits.append((0 if marked else 1, i, c))
    return min(hits)[2] if hits else None


# Recognised as places, but with no tier in our data, so the advisor asks instead of guessing.
UNLISTED = ["kota", "goa", "udaipur", "jodhpur", "ajmer", "gwalior", "jabalpur", "mangalore", "hubli", "tirupati", "shimla", "jammu", "siliguri"]
BTYPES = [("manufacturer", r"manufactur|factory|textile|garment unit|auto.?parts|plastic|moulding|packaging unit|printing press|furniture(?! (?:shop|store|showroom))|food processing|workshop|फैक्ट्री|कारखाना|टेक्सटाइल|\bmill\b"),
          ("restaurant", r"restaurant|tiffin|cloud kitchen|caterer|catering|\bmess\b|cafe|café|hotel|dhaba|bakery chain|रेस्टोरेंट|रेस्तरां|ढाबा|होटल"), ("clinic", r"clinic|dental|dentist|doctor|hospital|diagnostic|physio|\blabs?\b|क्लिनिक|डॉक्टर|अस्पताल"),
          ("pharmacy", r"pharmacy|chemist|medical|दवा|फार्मेसी|मेडिकल"), ("kirana", r"kirana|grocery|general store|किराना|किराणा|परचून"), ("salon", r"salon|parlou?r|barber|सैलून|पार्लर"),
          ("ca_firm", r"\bca\b|chartered accountant|account(an|ing)|सीए\b"), ("coaching", r"coaching|tuition|institute|pre.?school|कोचिंग|ट्यूशन"), ("office", r"\blaw\b|lawyer|advocate|real estate|architect|insurance agen|travel agen|\boffice\b|ऑफिस|वकील"),
          ("retailer", r"retail|showroom|furniture|boutique|stationery|hardware store|electronics|optician|mobile repair|sweet shop|bakery|apparel|gym|\bshops?\b|\bstores?\b|dukaan|dukan|दुकान")]
NEED_RX = [("mobile_premium", r"\b150 ?gb\b|roaming|priority care"), ("mobile_line", r"\bsims?\b|sim card|mobile (line|plan|connection)|postpaid|सिम|मोबाइल (लाइन|प्लान)"),
           ("internet_for_upi_pos", r"\bupi\b|यूपीआई|qr code|payment|card machine|swip(e|ing)|कार्ड मशीन|स्वाइप"), ("pos_billing", r"\bpos\b|billing|बिलिंग|inventory|cash counter"),
           ("cloud_email", r"e-?mail|ईमेल|office suite|google workspace|gmail"), ("storage", r"storage|back ?up(?! (?:internet|link|line|connection|router|4g|5g|net))|बैकअप(?! (?:इंटरनेट|लिंक|लाइन))|स्टोरेज|los(?:e|ing) (?:my |our |the |all )?(?:data|files|records|them)"),
           ("cctv", r"cctv|camera|सीसीटीवी|कैमरा|surveillance"), ("firewall", r"firewall|फ़ायरवॉल"), ("security", r"antivirus|security|ransomware|hack|सुरक्षा|सिक्योरिटी|data safe|डेटा|(?:patient|client|customer)s?'?s? (?:records|data)"),
           ("customer_messaging", r"whats ?app|व्हाट्सएप|catalogue|customer messag"), ("sms", r"\bsms\b|एसएमएस|bulk message"), ("wifi", r"wi-?fi|वाईफाई|guest network"),
           ("website", r"website|वेबसाइट|domain"), ("dedicated_bandwidth", r"leased ?line|dedicated|लीज़्ड|लीज्ड|लीज लाइन|\bsla\b"), ("high_speed", r"\b1 ?g(bps)?\b|gigabit|100 ?mbps dedicated"),
           ("iot", r"\biot\b|machine monitoring|monitor\w*\W+(\w+\W+){0,2}machines?|machines?\W+(\w+\W+){0,2}monitor|sensor|आईओटी|(?<!कार्ड )(?<!बिलिंग )(?<!स्वाइप )मशीन"), ("fleet", r"fleet|gps|vehicle track|truck|गाड़ी|गाड़ियों"), ("telephony", r"\bivr\b|sip\b|telephony|call recording"), ("toll.free", r"toll.?free|1800|टोल"),
           ("static_ip", r"static ip|स्टैटिक"), ("sdwan", r"sd-?wan|central(ly)? manag|one dashboard"), ("failover", r"failover|back ?up (internet|link|line|connection|router|4g|5g|net)|बैकअप (इंटरनेट|लिंक|लाइन)|फेलओवर"),
           ("uptime", r"uptime|downtime|never go down|keeps? going down|drops?\b|कटता|बंद हो जाता"), ("internet", r"internet|broadband|fibre|fiber|\b5g\b|airfiber|wifi|net connection|इंटरनेट|ब्रॉडबैंड|फाइबर|\bnet\b")]
HINDI_NUM = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "cheh": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "pachees": 25, "tees": 30, "pachas": 50, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "eighteen": 18, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10}
NUM = r"(?<![a-z\d])(\d+|(?:" + "|".join(HINDI_NUM) + r")(?![a-z]))"
ROLES = r"doctors?|nurses?|assistants?|receptionists?|teachers?|lawyers?|advocates?|accountants?|helpers?|ladke|ladkiyan|bande|banda|karigar|mazdoor|technicians?|cooks?|waiters?|engineers?|operators?|डॉक्टर|नर्स|टीचर|शिक्षक|लड़के|कारीगर"
HING = re.compile(r"\b(hai|hain|nahi|nahin|chahiye|mera|meri|mere|hum|humara|hamara|mujhe|kya|kitna|kitne|aur|bhi|karna|karni|ke liye|kaise|batao|bataiye|haan|sirf|dukaan|dukan|wala|wali|log|lagega|kyun|abhi|accha|acha)\b", re.I)
ENG = re.compile(r"\b(the|is|are|my|we|have|want|need|please|what|how|for|with|and|our|i|about|can|you|only|staff|employees|business|shop|looking)\b", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

Q = {"business_type": {"en": "What kind of business do you run (for example a kirana store, clinic, CA firm, restaurant or factory)?", "hi": "आपका बिज़नेस किस तरह का है (जैसे किराना, क्लिनिक, सीए फर्म, रेस्टोरेंट या फैक्ट्री)?", "hinglish": "Aapka business kis type ka hai (jaise kirana, clinic, CA firm, restaurant ya factory)?"},
     "employees": {"en": "How many people work there, including you?", "hi": "आपके यहाँ आपको मिलाकर कितने लोग काम करते हैं?", "hinglish": "Aapko milakar kitne log kaam karte hain?"},
     "locations": {"en": "How many locations or branches do you have?", "hi": "आपकी कितनी लोकेशन या ब्रांच हैं?", "hinglish": "Aapki kitni locations ya branches hain?"},
     "city": {"en": "Which city are you in?", "hi": "आप किस शहर में हैं?", "hinglish": "Aap kis city mein hain?"},
     "city_tier": {"en": "I don't have that city listed. Is it a metro (Tier 1), a large city (Tier 2), or a smaller town (Tier 3)?", "hi": "यह शहर मेरी सूची में नहीं है। क्या यह मेट्रो (टियर 1), बड़ा शहर (टियर 2) या छोटा शहर (टियर 3) है?", "hinglish": "Yeh city meri list mein nahi hai. Kya yeh metro (Tier 1), bada sheher (Tier 2) ya chhota town (Tier 3) hai?"},
     "has_gstin": {"en": "Does your business have a GSTIN?", "hi": "क्या आपके बिज़नेस का GSTIN है?", "hinglish": "Kya aapke business ka GSTIN hai?"},
     "needs": {"en": "What's the main thing you need right now: reliable internet, UPI or billing, email, CCTV, customer messaging, or something else? If you already have internet, tell me that too.", "hi": "अभी आपको सबसे ज़्यादा क्या चाहिए: भरोसेमंद इंटरनेट, UPI या बिलिंग, ईमेल, सीसीटीवी, ग्राहकों को मैसेज, या कुछ और? अगर इंटरनेट पहले से है तो वह भी बताएँ।", "hinglish": "Abhi sabse zyada kya chahiye: reliable internet, UPI ya billing, email, CCTV, customer messaging, ya kuch aur? Agar internet already hai to woh bhi bataiye."}}
# What they need comes early: the staff, site and GSTIN questions are only asked when the answer changes that plan.
ORDER = ["business_type", "needs", "city", "city_tier", "employees", "locations", "has_gstin"]
TXT = {
 "welcome": {"en": "Hi! I'm your Accel Business advisor. Tell me about your business and I'll suggest the right plan with one clear monthly price. Hindi or English, both are fine.", "hi": "नमस्ते! मैं आपका Accel Business सलाहकार हूँ।", "hinglish": "Namaste! Main aapka Accel Business advisor hoon."},
 "injection": {"en": "I can't share or change how I work, but I'm happy to help you find the right plan.", "hi": "मैं अपने निर्देश साझा या बदल नहीं सकता, पर सही प्लान ढूँढने में ज़रूर मदद करूँगा।", "hinglish": "Main apne instructions share ya change nahi kar sakta, par sahi plan dhoondhne mein zaroor help karunga."},
 "decline_promise": {"en": "I can't promise that; it depends on the plan and your site.", "hi": "मैं इसका वादा नहीं कर सकता; यह प्लान और आपकी जगह पर निर्भर करता है।", "hinglish": "Main iska promise nahi kar sakta; yeh plan aur aapki site par depend karta hai."},
 "decline_price": {"en": "I can't change prices: every customer sees the same price.", "hi": "मैं कीमत नहीं बदल सकता: सभी ग्राहकों के लिए कीमत एक जैसी है।", "hinglish": "Main price change nahi kar sakta: sabke liye price same hai."},
 "discount": {"en": "I can't offer discounts or change prices: every customer sees the same price.", "hi": "मैं छूट नहीं दे सकता और न ही कीमत बदल सकता हूँ: सभी ग्राहकों के लिए कीमत एक जैसी है।", "hinglish": "Main discount nahi de sakta ya price change nahi kar sakta: sabke liye price same hai."},
 "off_topic": {"en": "I can only help with Accel Business plans.", "hi": "मैं केवल Accel Business प्लान में मदद कर सकता हूँ।", "hinglish": "Main sirf Accel Business plans mein help kar sakta hoon."},
 "pii": {"en": "For your safety, please don't share Aadhaar, PAN or bank numbers in chat. I haven't saved it. You can submit documents securely in the KYC step later.", "hi": "आपकी सुरक्षा के लिए कृपया चैट में आधार, पैन या बैंक नंबर न भेजें। मैंने इसे सेव नहीं किया है। दस्तावेज़ आप बाद में KYC चरण में सुरक्षित रूप से दे सकते हैं।", "hinglish": "Aapki safety ke liye chat mein Aadhaar, PAN ya bank number mat bhejiye. Maine ise save nahi kiya. Documents aap baad mein KYC step mein safely de sakte hain."},
 "handoff": {"en": "I'm sorry this has been difficult. I've saved a summary, so an Accel Business specialist can take it from here without you repeating anything.", "hi": "मुझे खेद है कि आपको परेशानी हुई। मैंने सारांश सेव कर लिया है, Accel Business के विशेषज्ञ यहीं से आगे बढ़ेंगे, आपको कुछ दोहराना नहीं पड़ेगा।", "hinglish": "Sorry, aapko pareshani hui. Maine summary save kar li hai, Accel Business specialist yahin se aage badhenge, aapko kuch repeat nahi karna padega."},
 "tier3": {"en": "Accel Business plans are sold only in Tier 1 and Tier 2 cities right now, so I can't offer a plan at your location, and I won't quote something we can't deliver. I've saved your details for a specialist to contact you if coverage reaches your town.", "hi": "Accel Business प्लान अभी केवल टियर 1 और टियर 2 शहरों में उपलब्ध हैं, इसलिए आपकी लोकेशन पर मैं प्लान नहीं दे सकता। मैंने आपकी जानकारी सेव कर ली है, कवरेज आने पर विशेषज्ञ संपर्क करेंगे।", "hinglish": "Accel Business plans abhi sirf Tier 1 aur Tier 2 cities mein available hain, isliye aapki location par main plan nahi de sakta. Maine aapki details save kar li hain, coverage aane par specialist contact karenge."},
 "rec": {"en": "Here's the smallest plan that covers what you asked for:", "hi": "आपकी ज़रूरत पूरी करने वाला सबसे छोटा प्लान यह है:", "hinglish": "Aapki zaroorat cover karne wala sabse chhota plan yeh hai:"},
 "monthly": {"en": "**₹{m:,} per month** · setup ₹{s:,} · {c}-month minimum contract", "hi": "**₹{m:,} प्रति माह** · सेटअप ₹{s:,} · न्यूनतम {c} महीने का अनुबंध", "hinglish": "**₹{m:,} per month** · setup ₹{s:,} · minimum {c} months ka contract"},
 "alt": {"en": "Cheaper option: {names} at ₹{m:,} per month.", "hi": "सस्ता विकल्प: {names}, ₹{m:,} प्रति माह।", "hinglish": "Sasta option: {names}, ₹{m:,} per month."},
 "alt_mobile": {"en": " It's mobile data only, so no fixed connection at the shop.", "hi": " इसमें केवल मोबाइल डेटा है, दुकान पर फिक्स्ड कनेक्शन नहीं।", "hinglish": " Isme sirf mobile data hai, shop par fixed connection nahi."},
 "excluded": {"en": "Not included: {x}.", "hi": "शामिल नहीं: {x}।", "hinglish": "Shamil nahi: {x}."},
 "dep": {"en": "{a} is added because {b} needs an internet connection.", "hi": "{a} जोड़ा गया है क्योंकि {b} के लिए इंटरनेट कनेक्शन चाहिए।", "hinglish": "{a} add kiya hai kyunki {b} ke liye internet connection chahiye."},
 "next": {"en": "Open the **Quote** page to review and toggle add-ons. Want to change anything?", "hi": "समीक्षा और ऐड-ऑन के लिए **Quote** पेज खोलें। कुछ बदलना है?", "hinglish": "Review aur add-ons ke liye **Quote** page kholiye. Kuch change karna hai?"},
 "multi": {"en": "Because you have several locations, a specialist can also review site-by-site needs; I've saved a summary for them.", "hi": "आपकी कई लोकेशन हैं, इसलिए विशेषज्ञ हर साइट की ज़रूरत भी देख सकते हैं; मैंने उनके लिए सारांश सेव किया है।", "hinglish": "Aapki kai locations hain, isliye specialist har site ki zaroorat bhi dekh sakte hain; maine unke liye summary save ki hai."},
 "custom": {"en": "Some of this depends on your exact setup, so I've saved a summary for an Accel Business specialist to follow up.", "hi": "इसका कुछ हिस्सा आपके सेटअप पर निर्भर है, इसलिए मैंने विशेषज्ञ के लिए सारांश सेव किया है।", "hinglish": "Iska kuch hissa aapke setup par depend karta hai, isliye maine specialist ke liye summary save ki hai."},
 "none": {"en": "None of our plans fit what you described at your size and registration status, so I've saved a summary for a specialist.", "hi": "आपकी स्थिति के लिए कोई प्लान फिट नहीं बैठता, इसलिए मैंने विशेषज्ञ के लिए सारांश सेव किया है।", "hinglish": "Aapke case mein koi plan fit nahi hota, isliye maine specialist ke liye summary save ki hai."},
 "nocat": {"en": "We don't offer {label} in the Accel Business catalogue.", "hi": "Accel Business कैटलॉग में {label} उपलब्ध नहीं है।", "hinglish": "Accel Business catalogue mein {label} available nahi hai."},
 "near": {"en": " The nearest thing we have is {name}: {desc}.", "hi": " सबसे नज़दीकी विकल्प {name} है।", "hinglish": " Sabse nazdeeki option {name} hai."},
 "promise": {"en": "I can't promise a specific date or anything free. {name} typically takes about {d} days to install; you'll see the real date in the tracker once it's scheduled.", "hi": "मैं कोई तय तारीख या मुफ़्त चीज़ का वादा नहीं कर सकता। {name} लगने में आमतौर पर लगभग {d} दिन लगते हैं; तारीख तय होने पर ट्रैकर में दिखेगी।", "hinglish": "Main koi fixed date ya free cheez ka promise nahi kar sakta. {name} lagne mein usually {d} din lagte hain; date fix hone par tracker mein dikhegi."},
 "promise0": {"en": "I can't promise a specific date or anything free; it depends on the plan and your site. Let's pick the plan first.", "hi": "मैं कोई तय तारीख या मुफ़्त चीज़ का वादा नहीं कर सकता। पहले प्लान चुन लेते हैं।", "hinglish": "Main koi fixed date ya free cheez ka promise nahi kar sakta. Pehle plan choose kar lete hain."},
 "proceed": {"en": "Great. Please open the **Quote** page to confirm your plan.", "hi": "बढ़िया। प्लान कन्फर्म करने के लिए **Quote** पेज खोलें।", "hinglish": "Badhiya. Plan confirm karne ke liye **Quote** page kholiye."},
 "price_is": {"en": "Your plan stays at ₹{m:,} per month.", "hi": "आपका प्लान ₹{m:,} प्रति माह ही रहेगा।", "hinglish": "Aapka plan ₹{m:,} per month hi rahega."},
 "regional": {"en": "Sorry, I can only chat in English or Hindi for now. Please continue in either one, or type \"specialist\" and I'll save your request for an Accel Business specialist.\n\nक्षमा करें, अभी मैं केवल अंग्रेज़ी या हिंदी में बात कर सकता हूँ। कृपया इनमें से किसी एक में लिखें, या \"specialist\" लिखें।"},
 "faq_contract": {"en": "Plans have a minimum contract of {lo} to {hi} months depending on the product, and your quote shows the exact figure. I don't have early-exit terms, so I won't guess: please check them with a specialist before you sign.", "hi": "प्लान का न्यूनतम अनुबंध प्रोडक्ट के अनुसार {lo} से {hi} महीने का होता है, सही अवधि आपके कोटेशन में दिखेगी। जल्दी बंद करने की शर्तें मेरे पास नहीं हैं, इसलिए साइन करने से पहले विशेषज्ञ से पूछ लें।", "hinglish": "Plans ka minimum contract product ke hisaab se {lo} se {hi} months ka hota hai, exact period quote mein dikhega. Early exit ki terms mere paas nahi hain, isliye sign karne se pehle specialist se confirm kar lijiye."},
 "faq_setup": {"en": "The one-time setup fee depends on the product, from ₹{lo:,} to ₹{hi:,}. Your quote shows the exact total before you commit.", "hi": "एक बार का सेटअप शुल्क प्रोडक्ट पर निर्भर है, ₹{lo:,} से ₹{hi:,} तक। सही राशि आपके कोटेशन में दिखेगी।", "hinglish": "One-time setup fee product par depend karti hai, ₹{lo:,} se ₹{hi:,} tak. Exact amount quote mein dikhega."},
 "faq_your_terms": {"en": "For your plan: setup ₹{s:,} once, and a {c}-month minimum contract. I don't have early-exit terms, so please check them with a specialist before you sign.", "hi": "आपके प्लान में: सेटअप ₹{s:,} एक बार, और न्यूनतम {c} महीने का अनुबंध। जल्दी बंद करने की शर्तें विशेषज्ञ से पूछ लें।", "hinglish": "Aapke plan mein: setup ₹{s:,} ek baar, aur minimum {c} months ka contract. Early exit ki terms specialist se confirm kar lijiye."},
 "cheapest": {"en": "Our lowest prices start at ₹{a:,} per month for {an} (mobile only) and ₹{b:,} per month for {bn} (internet at your site). The right one depends on your business.", "hi": "सबसे कम कीमत ₹{a:,} प्रति माह {an} (केवल मोबाइल) और ₹{b:,} प्रति माह {bn} (दुकान पर इंटरनेट) से शुरू है। सही प्लान आपके बिज़नेस पर निर्भर है।", "hinglish": "Sabse kam price ₹{a:,} per month {an} (sirf mobile) aur ₹{b:,} per month {bn} (site par internet) se shuru hai. Sahi plan aapke business par depend karta hai."},
 "hint": {"en": "No problem, a rough answer is fine.", "hi": "कोई बात नहीं, अंदाज़ा भी चलेगा।", "hinglish": "Koi baat nahi, andaaza bhi chalega."},
 "gst_why": {"en": "I'm asking because {name} can't be sold without one.", "hi": "मैं इसलिए पूछ रहा हूँ क्योंकि {name} इसके बिना नहीं दिया जा सकता।", "hinglish": "Main isliye pooch raha hoon kyunki {name} iske bina nahi di ja sakti."},
 "hint_gst": {"en": "A GSTIN is the 15-character number on a GST certificate. If you don't have one, just say no.", "hi": "GSTIN आपके GST प्रमाणपत्र पर लिखा 15 अंकों का नंबर है। अगर नहीं है तो \"नहीं\" लिख दें।", "hinglish": "GSTIN aapke GST certificate par likha 15-character number hai. Agar nahi hai to \"nahi\" likh dijiye."},
 "suggest": {"en": "No problem. Most businesses like yours start with reliable internet. Shall I go with that? Reply yes, or tell me what else you need.", "hi": "कोई बात नहीं। आपके जैसे ज़्यादातर बिज़नेस भरोसेमंद इंटरनेट से शुरू करते हैं। क्या वही लें? \"हाँ\" लिखें, या बताएँ कि और क्या चाहिए।", "hinglish": "Koi baat nahi. Aapke jaise zyadatar business reliable internet se shuru karte hain. Wahi le lein? \"Haan\" boliye, ya bataiye aur kya chahiye."},
 "gst_bad": {"en": "That GSTIN doesn't show as active in the registry, so I can only include products that don't need one.", "hi": "यह GSTIN रजिस्ट्री में सक्रिय नहीं दिख रहा, इसलिए मैं केवल वही प्रोडक्ट जोड़ सकता हूँ जिनमें इसकी ज़रूरत नहीं।", "hinglish": "Yeh GSTIN registry mein active nahi dikh raha, isliye main sirf wahi products add kar sakta hoon jinmein iski zaroorat nahi."},
 "faq_tax": {"en": "The prices I quote are the catalogue monthly prices. I don't have the tax breakdown, so please confirm with a specialist whether GST is added on the bill.", "hi": "मैं कैटलॉग की मासिक कीमत बताता हूँ। टैक्स का ब्योरा मेरे पास नहीं है, इसलिए बिल पर GST के बारे में विशेषज्ञ से पूछ लें।", "hinglish": "Main catalogue ka monthly price batata hoon. Tax ka breakup mere paas nahi hai, isliye bill par GST ke baare mein specialist se confirm kar lijiye."},
 "restart": {"en": "Sure, let's start over. I've cleared your earlier answers.", "hi": "ठीक है, फिर से शुरू करते हैं। मैंने आपके पिछले जवाब हटा दिए हैं।", "hinglish": "Theek hai, phir se shuru karte hain. Maine aapke pichhle answers hata diye hain."},
 "pause": {"en": "Okay, I'll stop asking for now. Message me whenever you're ready, or say \"start over\" for a fresh chat.", "hi": "ठीक है, अभी और नहीं पूछूँगा। जब चाहें मैसेज करें, या नई शुरुआत के लिए \"शुरू से\" लिखें।", "hinglish": "Theek hai, abhi aur nahi poochunga. Jab chahein message kijiye, ya fresh start ke liye \"shuru se\" likhiye."},
 "contact_form": {"en": "I don't keep contact details typed in chat. To hear from our team, please use the \"Talk to a person\" form on this page.", "hi": "चैट में लिखी संपर्क जानकारी मैं नहीं रखता। हमारी टीम से बात के लिए इसी पेज पर \"किसी व्यक्ति से बात करें\" फ़ॉर्म भरें।", "hinglish": "Chat mein likhi contact details main nahi rakhta. Team se baat karne ke liye isi page par \"Talk to a person\" form bhariye."},
 "more_help": {"en": "Could you tell me what you need it to do? For example, internet, email, CCTV or a mobile line.", "hi": "क्या बता सकते हैं कि आपको क्या चाहिए? जैसे इंटरनेट, ईमेल, सीसीटीवी या मोबाइल लाइन।", "hinglish": "Kya bata sakte hain ki aapko kya chahiye? Jaise internet, email, CCTV ya mobile line."},
}
NEEDS_CANON = {"toll.free": "toll_free"}
WHY_FIELD = {
 "business_type": ("It helps me suggest what businesses like yours actually use.", "इससे मैं आपके जैसे बिज़नेस के काम की चीज़ें सुझा पाता हूँ।", "Isse main aapke jaise business ke kaam ki cheezein suggest kar pata hoon."),
 "employees": ("Some products have a minimum team size, and email and security are priced per person.", "कुछ प्रोडक्ट के लिए न्यूनतम स्टाफ़ चाहिए, और ईमेल व सिक्योरिटी की कीमत प्रति व्यक्ति होती है।", "Kuch products ke liye minimum staff chahiye, aur email aur security ka price per person hota hai."),
 "locations": ("Connections are priced per site, and some products need several sites.", "कनेक्शन की कीमत प्रति साइट होती है, और कुछ प्रोडक्ट के लिए कई साइट चाहिए।", "Connection ka price per site hota hai, aur kuch products ke liye kai sites chahiye."),
 "city": ("What we can sell depends on your city.", "हम क्या दे सकते हैं, यह आपके शहर पर निर्भर है।", "Hum kya de sakte hain, yeh aapki city par depend karta hai."),
 "city_tier": ("What we can sell depends on your city's tier.", "हम क्या दे सकते हैं, यह आपके शहर के टियर पर निर्भर है।", "Hum kya de sakte hain, yeh aapki city ke tier par depend karta hai."),
 "has_gstin": ("Some products can't be sold without an active GSTIN.", "कुछ प्रोडक्ट सक्रिय GSTIN के बिना नहीं दिए जा सकते।", "Kuch products active GSTIN ke bina nahi diye ja sakte."),
 "needs": ("So I only suggest what you need, and nothing extra.", "ताकि मैं केवल वही सुझाऊँ जो आपको चाहिए, उससे ज़्यादा कुछ नहीं।", "Taaki main sirf wahi suggest karun jo aapko chahiye, usse zyada kuch nahi."),
}
# Plain-language reason for each product, keyed by the stated need that pulled it in.
WHY = {
 "internet": ("your main internet connection", "आपका मुख्य इंटरनेट कनेक्शन", "aapka main internet connection"),
 "internet_for_upi_pos": ("keeps UPI and card payments running", "UPI और कार्ड पेमेंट चालू रखता है", "UPI aur card payments chalu rakhta hai"),
 "uptime": ("keeps you online when the main line is down", "मुख्य लाइन बंद होने पर भी आपको ऑनलाइन रखता है", "main line band hone par bhi online rakhta hai"),
 "failover": ("keeps you online when the main line is down", "मुख्य लाइन बंद होने पर भी आपको ऑनलाइन रखता है", "main line band hone par bhi online rakhta hai"),
 "customer_messaging": ("reach customers and share your catalogue on WhatsApp", "WhatsApp पर ग्राहकों तक पहुँचें और कैटलॉग भेजें", "WhatsApp par customers tak pahunchein aur catalogue bhejein"),
 "sms": ("send alerts and offers by SMS", "SMS से अलर्ट और ऑफ़र भेजें", "SMS se alerts aur offers bhejein"),
 "cloud_email": ("business email and documents for your team", "आपकी टीम के लिए बिज़नेस ईमेल और दस्तावेज़", "team ke liye business email aur documents"),
 "storage": ("automatic backup of your files", "आपकी फ़ाइलों का अपने आप बैकअप", "files ka automatic backup"),
 "security": ("protects PCs and phones from viruses and ransomware", "PC और फ़ोन को वायरस और रैनसमवेयर से बचाता है", "PC aur phones ko virus aur ransomware se bachata hai"),
 "firewall": ("a managed firewall that protects your network", "आपके नेटवर्क की सुरक्षा के लिए मैनेज्ड फ़ायरवॉल", "network ki safety ke liye managed firewall"),
 "cctv": ("cameras with cloud recording you can view on your phone", "क्लाउड रिकॉर्डिंग वाले कैमरे, जिन्हें फ़ोन पर देख सकते हैं", "cloud recording wale cameras, jo phone par dekh sakte hain"),
 "wifi": ("secure Wi-Fi with a separate customer network", "ग्राहकों के लिए अलग नेटवर्क वाला सुरक्षित Wi-Fi", "customers ke liye alag network wala secure Wi-Fi"),
 "pos_billing": ("billing, inventory and UPI or card acceptance", "बिलिंग, इन्वेंटरी और UPI या कार्ड पेमेंट", "billing, inventory aur UPI ya card payment"),
 "website": ("a domain and simple website for your business", "आपके बिज़नेस के लिए डोमेन और वेबसाइट", "business ke liye domain aur website"),
 "dedicated_bandwidth": ("dedicated internet with a service commitment", "सर्विस कमिटमेंट के साथ समर्पित इंटरनेट", "service commitment ke saath dedicated internet"),
 "high_speed": ("high-speed fibre for heavy use", "ज़्यादा इस्तेमाल के लिए तेज़ फाइबर", "heavy use ke liye fast fibre"),
 "iot": ("tracks machine uptime and energy use", "मशीन के चलने और बिजली खपत पर नज़र रखता है", "machine uptime aur energy use track karta hai"),
 "fleet": ("live GPS tracking for your vehicles", "गाड़ियों की लाइव GPS ट्रैकिंग", "gaadiyon ki live GPS tracking"),
 "telephony": ("business phone lines with IVR and call recording", "IVR और कॉल रिकॉर्डिंग वाली बिज़नेस फ़ोन लाइन", "IVR aur call recording wali business phone lines"),
 "toll_free": ("an 1800 number for your customers", "ग्राहकों के लिए 1800 नंबर", "customers ke liye 1800 number"),
 "static_ip": ("a fixed IP for CCTV, servers or remote access", "CCTV, सर्वर या रिमोट एक्सेस के लिए फ़िक्स्ड IP", "CCTV, server ya remote access ke liye fixed IP"),
 "sdwan": ("manages the links across your sites in one place", "सभी साइटों के लिंक एक जगह से मैनेज करता है", "saari sites ke links ek jagah se manage karta hai"),
 "mobile_premium": ("a business mobile line with more data and roaming", "ज़्यादा डेटा और रोमिंग वाली बिज़नेस मोबाइल लाइन", "zyada data aur roaming wali business mobile line"),
 "mobile_line": ("a business mobile line with data and calls", "डेटा और कॉल वाली बिज़नेस मोबाइल लाइन", "data aur calls wali business mobile line"),
}


@dataclass
class State:
    profile: Profile = field(default_factory=Profile)
    asked: list[str] = field(default_factory=list)
    awaiting: str | None = None
    rec: Recommendation | None = None
    confusion: int = 0
    handoff: str | None = None
    history: list[tuple[str, str]] = field(default_factory=list)
    declined: list[str] = field(default_factory=list)
    stuck: int = 0
    restarted: bool = False  # tells the page to clear the visible chat


LINK_WHY = {
 "fibre_needed": ("{name} only works on wired fibre", "{name} केवल वायर्ड फाइबर पर चलता है", "{name} sirf wired fibre par chalta hai"),
 "closest": ("the fastest connection you can get right now, since Biz Fibre 1G isn't available to you", "आपके लिए उपलब्ध सबसे तेज़ कनेक्शन, क्योंकि Biz Fibre 1G आपके लिए उपलब्ध नहीं है", "aapke liye available sabse fast connection, kyunki Biz Fibre 1G aapke liye available nahi hai"),
 "asked_5g": ("the wireless 5G connection you asked for", "आपका माँगा हुआ वायरलेस 5G कनेक्शन", "aapka manga hua wireless 5G connection"),
 "asked_fibre": ("the wired fibre connection you asked for", "आपका माँगा हुआ वायर्ड फाइबर कनेक्शन", "aapka manga hua wired fibre connection"),
 "implied": ("this needs internet at your site; tell me if you already have it and I'll take this out", "इसके लिए आपकी साइट पर इंटरनेट चाहिए; पहले से है तो बताएँ, मैं इसे हटा दूँगा", "iske liye site par internet chahiye; already hai to bataiye, main ise hata dunga"),
 "staff": ("300 Mbps because {n} people will share it", "300 Mbps, क्योंकि इसे {n} लोग इस्तेमाल करेंगे", "300 Mbps, kyunki ise {n} log use karenge"),
 "sites": ("300 Mbps for each of your {n} locations", "आपकी {n} लोकेशन में से हर एक के लिए 300 Mbps", "aapki {n} locations mein se har ek ke liye 300 Mbps"),
 "micro": ("our lowest-priced fixed connection, and it's plug-and-play for a single shop", "हमारा सबसे कम कीमत वाला फिक्स्ड कनेक्शन, एक दुकान के लिए प्लग-एंड-प्ले", "hamara sabse kam price wala fixed connection, ek shop ke liye plug-and-play"),
 "lowest_wired": ("our lowest-priced wired connection, at 100 Mbps", "हमारा सबसे कम कीमत वाला वायर्ड कनेक्शन, 100 Mbps", "hamara sabse kam price wala wired connection, 100 Mbps"),
}
AUTO_SECURITY = ("I added this because offices like yours hold client data; say \"remove security\" if you don't want it", "मैंने इसे इसलिए जोड़ा क्योंकि आपके जैसे ऑफिस में क्लाइंट का डेटा होता है; नहीं चाहिए तो \"remove security\" लिखें", "Maine ise isliye add kiya kyunki aapke jaise office mein client data hota hai; nahi chahiye to \"remove security\" likhiye")
TRADE = {
 ("P02", "P01"): ("the faster 300 Mbps speed; you'd get 100 Mbps", "तेज़ 300 Mbps स्पीड; आपको 100 Mbps मिलेगा", "fast 300 Mbps speed; aapko 100 Mbps milega"),
 ("P01", "P04"): ("wired fibre; you'd get wireless 5G", "वायर्ड फाइबर; आपको वायरलेस 5G मिलेगा", "wired fibre; aapko wireless 5G milega"),
 ("P03", "P02"): ("1 Gbps speed and priority support; you'd get 300 Mbps", "1 Gbps स्पीड और प्रायोरिटी सपोर्ट; आपको 300 Mbps मिलेगा", "1 Gbps speed aur priority support; aapko 300 Mbps milega"),
 ("P06", "P05"): ("100 Mbps and the 99.9% SLA; you'd get 20 Mbps with a 99.5% SLA", "100 Mbps और 99.9% SLA; आपको 20 Mbps और 99.5% SLA मिलेगा", "100 Mbps aur 99.9% SLA; aapko 20 Mbps aur 99.5% SLA milega"),
 ("P04", "P07"): ("a fixed connection at your site; you'd only have mobile data (50 GB)", "आपकी साइट पर फिक्स्ड कनेक्शन; केवल मोबाइल डेटा (50 GB) मिलेगा", "site par fixed connection; sirf mobile data (50 GB) milega"),
 ("P08", "P07"): ("the extra data, roaming and priority care; you'd get 50 GB instead of 150 GB", "ज़्यादा डेटा, रोमिंग और प्रायोरिटी केयर; 150 GB की जगह 50 GB मिलेगा", "zyada data, roaming aur priority care; 150 GB ki jagah 50 GB milega"),
}
ALT_WORDS = {"lose": ("What you'd miss: {x}.", "आपको यह नहीं मिलेगा: {x}।", "Aapko yeh nahi milega: {x}."),
             "blocked": ("You also couldn't add {x}, which need wired fibre.", "आप {x} भी नहीं जोड़ पाएँगे, इनके लिए वायर्ड फाइबर चाहिए।", "Aap {x} bhi add nahi kar payenge, inke liye wired fibre chahiye."),
             "contract": ("You'd get a {b}-month contract instead of {a}.", "अनुबंध {a} की जगह {b} महीने का होगा।", "Contract {a} ki jagah {b} months ka hoga."),
             "install": ("Installation usually takes about {b} {day} instead of {a}.", "इंस्टॉलेशन में आमतौर पर {a} की जगह लगभग {b} दिन लगते हैं।", "Installation mein usually {a} ki jagah lagbhag {b} din lagte hain.")}


def _col(lang: str) -> int: return {"en": 0, "hi": 1, "hinglish": 2}.get(lang, 0)


def why_text(rec: Recommendation, pid: str, lang: str) -> str:
    """Why this product is in the plan, in plain words."""
    if rec.link_reason and rec.why.get(pid) and catalogue()[pid].category == "Connectivity" and pid in ("P01", "P02", "P04"):
        return LINK_WHY[rec.link_reason[0]][_col(lang)].format(**rec.link_reason[1])
    if pid == "P20" and rec.auto_security: return AUTO_SECURITY[_col(lang)]
    w = WHY.get(rec.why.get(pid, ""))
    return w[_col(lang)] if w else ""


def trade_text(rec: Recommendation, lang: str) -> str:
    """What the cheaper option gives up and what changes. Catalogue facts only."""
    d = alt_diff(rec)
    if not d: return ""
    i, parts = _col(lang), []
    lost = TRADE.get((d["old"], d["new"]))
    if lost: parts.append(ALT_WORDS["lose"][i].format(x=lost[i]))
    if d["blocked"]: parts.append(ALT_WORDS["blocked"][i].format(x=", ".join(d["blocked"])))
    a, b = d["contract"]
    if a != b: parts.append(ALT_WORDS["contract"][i].format(a=a, b=b))
    a, b = d["install"]
    if a != b: parts.append(ALT_WORDS["install"][i].format(a=a, b=b, day="day" if b == 1 else "days"))
    return " ".join(parts)


def detect_language(text: str, current: str) -> str:
    if DEVANAGARI.search(text): return "hi"
    if HING.search(text): return "hinglish"
    if ENG.search(text) and len(text.split()) >= 2: return "en"
    return current


def extract_profile(text: str, p: Profile, awaiting: str | None = None) -> dict:
    """Pure regex extraction. Later statements overwrite earlier ones so users can correct themselves."""
    t, u = text.lower(), {}
    t = re.sub(r"\b(what|how|why|which|where|when|who|you|we|they|i|can|should|does|did)\s+do\b|\bdo\s+(you|we|i|they)\b", " ", t)  # English "do" is not Hindi for 2
    t = re.sub(r"(?<![\w])-\s*\d+", " ", t)  # a negative count is not a count
    for name, rx in BTYPES:
        if re.search(rx, t): u["business_type"] = name; break
    def num(s): return HINDI_NUM.get(s, int(s) if s.isdigit() else None)
    m = re.search(NUM + r"\s*\+?\s*(?:staff|employee|people|person|log\b|workers?|member|team|लोग|कर्मचारी|स्टाफ)", t) or re.search(r"(?:staff|employees?|team)\s*(?:of|:|is|are|hai|hain)?\s*" + NUM + r"\b", t)
    if m and num(m.group(1)) is not None: u["employees"] = num(m.group(1))
    elif (roles := re.findall(NUM + rf"\s*(?:{ROLES})(?![a-z])", t)):
        u["employees"] = sum(num(x) for x in roles)
    elif (m := re.search(NUM + r"\s+of us\b", t)) or (m := re.search(r"\bhum\s+" + NUM + r"\b", t)):
        u["employees"] = num(m.group(1))
    elif re.search(r"\b(?:wife|husband|brother|sister|son|daughter|partner) and (?:me|i)\b", t):
        u["employees"] = 2
    elif re.search(r"\b(me|main|i) (and|aur) (my|mera|meri) \w+", t) or re.search(r"मैं और मेर[ाी] ", t):
        u["employees"] = 2
    if re.search(r"\b(just me|only me|myself|akela|sirf main)\b|अकेला|सिर्फ मैं", t): u["employees"] = 1
    m = re.search(NUM + r"\s*(?:outlets?|branch(?:es)?|locations?|sites?|stores?|shops?|offices?|clinics?|restaurants?|units?|salons?|pharmac(?:y|ies)|kiranas?|firms?|centres?|centers?|cafes?|plants?|workshops?|hotels?|dukaan|dukan|factories|ब्रांच|लोकेशन|आउटलेट|दुकानें|दुकान|शाखा)", t)
    if m and num(m.group(1)) is not None: u["locations"] = num(m.group(1))
    if re.search(r"single (shop|location|site|store|office)|only one (shop|location|site|branch)|one branch|ek hi|एक ही|\bek (jagah|location|branch|office|dukan|shop|outlet)\b|एक (जगह|लोकेशन|ब्रांच|दुकान|ऑफ़िस|आउटलेट)", t): u["locations"] = 1
    found = _find_city(t, text, awaiting)
    if found: u["city"], u["city_tier"] = found.title(), CITY_TIER[found]
    # An unknown word after "in" may be a town, but must not overwrite a city we already have ("drops in evening").
    if "city" not in u and (p.city is None or re.search(r"\b(moved|shifted|relocat\w*|actually)\b", t)):
        m = re.search(r"\b(?:in|from|based in)\s+([A-Za-z]{3,})(?:\s+(?:mein|me|city)\b)?", text)
        if m and m.group(1).lower() not in NOT_PLACE:
            u["city"] = m.group(1).title()
    if "city" not in u:
        for c in UNLISTED:
            if re.search(rf"\b{c}\b", t): u["city"] = c.title(); break
    m = re.search(r"tier[- ]?([123])|टियर[- ]?([123])", t)
    if m: u["city_tier"] = int(m.group(1) or m.group(2)); u.setdefault("city", p.city or f"Tier {u['city_tier']} city")
    elif re.search(r"\b(village|gaon|small town|chhota sheher|chhota town)\b|गाँव|गांव|छोटा शहर|कस्बा", t): u["city_tier"] = 3; u.setdefault("city", p.city or "your town")
    elif awaiting == "city_tier" and re.search(r"\bmetro\b|मेट्रो", t): u["city_tier"] = 1
    elif awaiting == "city_tier" and re.search(r"\b(large|big|bada)\b|बड़ा", t): u["city_tier"] = 2
    elif awaiting == "city_tier" and re.search(r"\b(small|smaller|chhota)\b|छोटा", t): u["city_tier"] = 3
    elif awaiting == "city_tier" and (m := re.search(r"(?<!\d)([123])(?!\d)", t)): u["city_tier"] = int(m.group(1))
    gst = r"(gst(in| number| no| registration)?|जीएसटी|जीएसटीआईएन)"
    if "[inactive gstin removed]" in t or GST_BAD.search(t):
        u["has_gstin"] = False
    elif GST_UNSURE.search(t) or G.FAQ_TAX.search(t) or G.GSTIN_ASK.search(t):
        pass  # unsure, or a question about tax: it says nothing about registration, so ask instead of guessing
    elif re.search(rf"(no|without|not|don'?t have|do not have|dont have|haven'?t|bina|बिना)\W+(\w+\W+){{0,2}}{gst}|{gst}\W+(\w+\W+){{0,2}}(nahi|nahin|नहीं|na\b|not)|\bunregistered\b|not registered", t, re.I):
        u["has_gstin"] = False
    elif re.search(gst, t, re.I) or "[gstin removed]" in t: u["has_gstin"] = True
    m = re.search(NUM + r"\s*(?:business\s+|mobile\s+|postpaid\s+)*(?:sims?|lines?|सिम)", t)
    if m and num(m.group(1)): u["sim_lines"] = num(m.group(1))
    m = re.search(NUM + r"\s*(?:cameras?|cctv|कैमरे|कैमरा)", t)
    if m and num(m.group(1)): u["cameras"] = num(m.group(1))
    m = re.search(r"(?:cameras?|cctv)\W+" + NUM + r"\s+of them", t)
    if m and num(m.group(1)): u["cameras"] = num(m.group(1))
    m = re.search(NUM + r"\s*(?:machines?|मशीन)", t)
    if m and num(m.group(1)): u["devices_iot"] = num(m.group(1))
    m = re.search(NUM + r"\s*(?:vehicles?|trucks?|गाड़ियों|गाड़ियाँ)", t)
    if m and num(m.group(1)): u["vehicles"] = num(m.group(1))
    needs = []
    # Tools they use today describe the current setup; they are not a request.
    tn = re.sub(r"(?:home (?:wi-?fi|broadband|internet)|(?:mobile )?hotspot|(?:personal |own )?gmail)", " ", t) if re.search(r"\b(on|use|using|have|with|from|through|chalate|chalta)\b", t) else t
    declined = []
    for n, rx in NEED_RX:
        hits = list(re.finditer(rx, tn))
        if not hits: continue
        n = NEEDS_CANON.get(n, n)
        (needs if any(not _negated(tn, h.start(), h.end()) for h in hits) else declined).append(n)
    if EXISTING.search(t):
        needs = [n for n in needs if n != "internet"]
    only_sim = re.search(r"\b(only|just|sirf|bas)\b.*\bsims?\b|\bsims?\b.*\b(only|just|sirf|bas)\b|सिर्फ.*सिम|केवल.*सिम", t)
    if "mobile_premium" in needs and "mobile_line" in needs: needs.remove("mobile_line")
    if "internet_for_upi_pos" in needs and "internet" in needs: needs.remove("internet")
    if only_sim: needs = ["mobile_premium" if "mobile_premium" in needs else "mobile_line"]; u["only"] = True
    if needs: u["needs"] = needs
    if declined: u["declined"] = declined
    if not EXISTING.search(t):
        if re.search(r"(?<!backup )(?<!back up )\b5g\b(?! backup| failover)|airfiber|wireless|वायरलेस", tn): u["link_pref"] = "5g"
        elif re.search(r"fibre|fiber|wired|फाइबर", tn): u["link_pref"] = "fibre"
    setup = []
    if EXISTING.search(t): setup.append("existing_link")
    if re.search(r"business broadband", t): setup.append("business_broadband")
    if re.search(r"(already|existing|current|have|hai).{0,20}leased line", t): setup.append("leased_line")
    if re.search(r"hotspot|हॉटस्पॉट", t): setup.append("hotspot")
    if re.search(r"home broadband|home wifi", t): setup.append("home_broadband")
    if setup: u["current_setup"] = setup
    # Bare answers to the pending question
    y = re.match(r"\s*((yes|yeah|yep|haan|han|ha|ji)\b|हाँ|हां|जी)", t); n = re.match(r"\s*((no|nope|nah|nahi|nahin)\b(?! idea)|नहीं|नही|ना\b)", t)
    if awaiting == "city_tier":  # that question also asks about GSTIN, so the yes or no can follow the tier
        y = y or re.search(r"\b(yes|haan|han|ji)\b|हाँ|हां", t); n = n or re.search(r"\b(no|nahi|nahin)\b(?! idea)|नहीं", t)
    if awaiting in ("has_gstin", "city_tier") and "has_gstin" not in u and not VAGUE.search(t):
        if y: u["has_gstin"] = True
        elif n: u["has_gstin"] = False
    if awaiting in ("employees", "locations") and not {"employees", "locations"} & set(u) and len(text.split()) <= 4:  # in a longer sentence the first number may be only part of the answer
        m = re.search(NUM, t)
        if m and num(m.group(1)) is not None and not re.search(r"\[", t): u[awaiting] = num(m.group(1))
    if awaiting == "business_type" and "business_type" not in u and text.strip() and not re.search(r"small business|chhota business|छोटा बिज़नेस|business$", t) and len(text.split()) <= 6 and not VAGUE.search(t) and not ASKING.search(t):
        u["business_type"] = "other"
    if awaiting == "city" and "city" not in u and text.strip() and len(text.split()) <= 3 and not n and not VAGUE.search(t) and not ASKING.search(t):
        u["city"] = text.strip().title()
    for k in ("employees", "locations"):
        if u.get(k) == 0: u[k] = 1  # "0 staff" still means the owner is there
    return u


THANKS = re.compile(r"^\W*(thanks|thank you|thx|ok|okay|cool|great|shukriya|dhanyavaad|धन्यवाद|शुक्रिया)\W*$", re.I)


def _merge(s: State, u: dict) -> None:
    p = s.profile
    for k, v in u.items():
        if k == "needs":
            p.needs = list(v) if u.get("only") else list(dict.fromkeys(p.needs + list(v)))
            s.declined = p.declined = [n for n in s.declined if n not in v]
        elif k == "declined":
            p.needs = [n for n in p.needs if n not in v]
            s.declined = p.declined = list(dict.fromkeys(s.declined + list(v)))
        elif k == "current_setup":
            p.current_setup = list(dict.fromkeys(p.current_setup + list(v)))
        elif k != "only":
            setattr(p, k, v)
    if "city" in u and "city_tier" not in u: p.city_tier = None


def _merge_llm(s: State, text: str, have: dict) -> None:
    """LLM fills only gaps the regex left. Output is validated like any other untrusted input."""
    if llm.client() is None: return
    raw = llm.extract(f"[Question just asked: {s.awaiting}] {text}" if s.awaiting else text, NEEDS)
    clean = {}
    for k, top in (("employees", 100000), ("locations", 10000)):
        if type(raw.get(k)) is int and 0 < raw[k] < top: clean[k] = raw[k]
    if isinstance(raw.get("has_gstin"), bool): clean["has_gstin"] = raw["has_gstin"]
    if raw.get("business_type") in {"kirana", "salon", "pharmacy", "clinic", "ca_firm", "coaching", "restaurant", "retailer", "manufacturer", "office", "other"}: clean["business_type"] = raw["business_type"]
    if isinstance(raw.get("city"), str):
        c = raw["city"].strip().lower()[:40]
        clean["city"] = c.title()
        if c in CITY_TIER: clean["city_tier"] = CITY_TIER[c]
    if raw.get("city_tier") in (1, 2, 3): clean["city_tier"] = raw["city_tier"]
    if isinstance(raw.get("needs"), list): clean["needs"] = [n for n in raw["needs"] if n in NEEDS and n not in s.declined]
    _merge(s, {k: v for k, v in clean.items() if k not in have and (k == "needs" or getattr(s.profile, k) is None)})


def next_question(s: State) -> str | None:
    p = s.profile
    for f in ORDER:
        val = getattr(p, f)
        if f == "city_tier" and p.city is None: continue
        if f == "needs":
            if not val: return f
        elif f in QUESTION_VALUES:
            if val is None and question_matters(f, p): return f
        elif val is None: return f
    return None


def _question(s: State, f: str, lang: str) -> str:
    q = Q[f][lang]
    if f == "has_gstin" and (name := gstin_product(s.profile)):
        q = _join(q, _lang_text("gst_why", lang, name=name))
    return q


def _lang_text(key, lang, **k): return TXT[key].get(lang, TXT[key]["en"]).format(**k)


def render_rec(s: State) -> str:
    rec, lang = s.rec, s.profile.language
    if not rec.serviceable: return _lang_text("tier3", lang)
    cat = catalogue()
    if not rec.quote: return _lang_text("none", lang) + _excluded(rec, lang)
    parts = [_lang_text("rec", lang)]
    for l in rec.quote.lines:
        why = why_text(rec, l.product_id, lang)
        parts.append(f"- {l.name}" + (f" × {l.qty}" if l.qty > 1 else "") + f": ₹{l.monthly:,}" + (f" ({why})" if why else ""))
    parts.append(_lang_text("monthly", lang, m=rec.quote.monthly, s=rec.quote.setup, c=rec.quote.contract))
    for a, b in rec.auto_added.items():
        parts.append(_lang_text("dep", lang, a=cat[a].name, b=cat[b].name))
    if rec.alternative:
        names = ", ".join(cat[k].name for k in rec.alternative)
        parts.append(_join(_lang_text("alt", lang, names=names, m=rec.alt_quote.monthly), trade_text(rec, lang)))
    x = _excluded(rec, lang)
    if x: parts.append(x.strip())
    if rec.handoff == "multi_site": parts.append(_lang_text("multi", lang))
    elif rec.handoff: parts.append(_lang_text("custom", lang))
    parts.append(_lang_text("next", lang))
    return "\n\n".join(parts)


def _excluded(rec, lang) -> str:
    cat = catalogue()
    seen, items = set(rec.items), []
    for pid, r in rec.excluded:
        if pid not in seen:
            seen.add(pid); items.append(f"{cat[pid].name} ({reason_text(r, lang)})")
    return " " + _lang_text("excluded", lang, x="; ".join(items)) if items else ""


def _polish(draft: str, s: State, client=None) -> str:
    """Optional LLM rewording, validated; a failed check regenerates once, then the checked draft is shown."""
    if client is None and llm.client() is None: return draft
    q, alt = s.rec.quote, s.rec.alt_quote
    for _ in range(2):
        out = llm.rewrite(draft, s.profile.language, client)
        if not out: break  # the service failed: don't make the owner wait for a second try
        if not G.check_reply(out, q, alt, mentionable(s.rec), draft) and not G.dropped_facts(out, draft, alt, [catalogue()[e[0]].name for e in s.rec.excluded]): return out
    return draft


def _converse(s: State, text: str, lang: str, client=None) -> str | None:
    """Natural reply to a message nothing else understood. Decides nothing; anything unsafe is dropped."""
    if (client is None and llm.client() is None) or VAGUE.search(text) or len(text.split()) < 3: return None
    p, q = s.profile, s.rec.quote if s.rec else None
    facts = f"business type {p.business_type or 'unknown'}, city {p.city or 'unknown'}."
    names = tuple(l.name for l in q.lines) if q else ()
    if q: facts += " Their plan: " + "; ".join(f"{l.name} ({catalogue()[l.product_id].description})" for l in q.lines)
    out = (llm.converse(text, lang, facts, client) or "").strip()
    return out if out and not G.check_chat(out, names) else None


def _steer(s: State) -> str:
    if s.rec and s.rec.quote:
        return _lang_text("price_is", s.profile.language, m=s.rec.quote.monthly)
    f = next_question(s)
    if f:
        s.awaiting = f
        return _question(s, f, s.profile.language)
    return ""


def _do_handoff(s: State, reason: str) -> None:
    if s.handoff == reason: return  # one lead per reason, however many turns follow
    s.handoff = reason
    from . import db
    db.save_lead(s.profile.model_dump_json(), reason)


def _join(*a): return " ".join(x for x in a if x)


def turn(s: State, raw: str, llm_client=None) -> str:
    """One advisor turn. Redaction runs before history, regex or LLM see the text."""
    typed = G.GSTIN.search(raw)
    rec = registry.lookup_gstin(typed.group().upper())[0] if typed else None
    bad_gstin = bool(typed) and (rec is None or rec["status"] != "Active")
    text, found = G.redact(raw)
    if bad_gstin: text = text.replace("[GSTIN removed]", "[inactive GSTIN removed]")
    s.restarted = False
    if not found and G.RESTART.search(text) and not G.NOT_RESTART.search(text) and len(text.split()) <= 8:
        return _restart(s, text)
    s.profile.language = detect_language(text, s.profile.language)
    lang = s.profile.language
    reply = _route(s, text, found, lang, llm_client)
    if bad_gstin: reply = _join(_lang_text("gst_bad", lang), reply)
    if "[contact removed]" in text: reply = _join(_lang_text("contact_form", lang), reply)
    s.history += [("user", text), ("assistant", reply)]
    return reply


def _restart(s: State, text: str) -> str:
    """Forget every answer. The language stays, and an accepted order is unaffected."""
    lang = detect_language(text, s.profile.language)
    s.profile, s.asked, s.awaiting, s.rec = Profile(language=lang), ["business_type"], "business_type", None
    s.confusion, s.handoff, s.declined, s.stuck, s.history = 0, None, [], 0, []
    s.restarted = True
    return _join(_lang_text("restart", lang), Q["business_type"][lang])


def _faq(s, text, lang) -> str | None:
    """Answers from catalogue or quote figures only."""
    cat = catalogue().values()
    if G.FAQ_TAX.search(text): return _lang_text("faq_tax", lang)
    if G.GSTIN_ASK.search(text): return _lang_text("hint_gst", lang)
    if G.FAQ_CONTRACT.search(text) or G.FAQ_SETUP.search(text):
        if s.rec and s.rec.quote:
            return _lang_text("faq_your_terms", lang, s=s.rec.quote.setup, c=s.rec.quote.contract)
        if G.FAQ_CONTRACT.search(text):
            c = [p.contract for p in cat]
            return _lang_text("faq_contract", lang, lo=min(c), hi=max(c))
        f = [p.setup for p in cat]
        return _lang_text("faq_setup", lang, lo=min(f), hi=max(f))
    if not s.rec and G.CHEAPEST.search(text):
        c = catalogue()
        return _lang_text("cheapest", lang, a=c["P07"].monthly, an=c["P07"].name, b=c["P04"].monthly, bn=c["P04"].name)
    return None


def _rest_of(s, text, asked, found, lang, llm_client) -> str | None:
    """A question we decline can arrive with real answers ("free upgrade? clinic in Delhi, 6 staff"): use them instead of asking again.
    Only before a plan exists, so a figure in a haggle can never change a quote."""
    rest = asked.sub(" ", text)
    if s.rec or asked.search(rest) or not extract_profile(rest, s.profile, None): return None
    return _route(s, rest, found, lang, llm_client)


def _route(s, text, found, lang, llm_client):
    sensitive = [f for f in found if f != "GSTIN"]
    if sensitive:
        u = extract_profile(re.sub(r"\[[^\]]*removed\]", "", text), s.profile, None)
        _merge(s, u)
        return _join(_lang_text("pii", lang), _steer(s))
    if G.REGIONAL.search(text) and not DEVANAGARI.search(text):
        return _join(TXT["regional"]["en"], _steer(s))
    if G.INJECTION.search(text):
        return _join(_lang_text("injection", lang), _steer(s))
    if G.FRUSTRATED.search(text):
        _do_handoff(s, "frustration")
        return _lang_text("handoff", lang)
    if G.DISCOUNT.search(text) and not G.PROMISE_ASK.search(text) and (re.search(r"discount|% ?off|छूट|डिस्काउंट", text, re.I) or not re.search(r"\d+\s*(staff|employee|people|log\b)", text, re.I)):
        rest = _rest_of(s, text, G.DISCOUNT, found, lang, llm_client)
        # Beside a plan, the shorter words: the reply check rightly objects to "discount" next to a price.
        return _join(_lang_text("decline_price" if rest and s.rec and s.rec.quote else "discount", lang), rest or _steer(s))
    if G.OFF_TOPIC.search(text):
        return _join(_lang_text("off_topic", lang), _steer(s))
    if G.PAUSE.search(text):
        s.awaiting, s.stuck = None, 0
        return _lang_text("pause", lang)
    field_asked = "needs" if s.awaiting == "needs_confirm" else s.awaiting
    if field_asked and G.WHY_ASK.search(text):
        return _join(WHY_FIELD[field_asked][{"en": 0, "hi": 1, "hinglish": 2}.get(lang, 0)], Q[field_asked][lang])
    miss = G.out_of_catalogue(text)
    u = extract_profile(text, s.profile, s.awaiting)
    if G.CONFUSED.search(text):
        s.confusion += 1
        if s.confusion >= 2:
            _do_handoff(s, "repeated_confusion")
            return _lang_text("handoff", lang)
        return _lang_text("more_help", lang)
    if miss:
        label, near = miss
        t = _lang_text("nocat", lang, label=label)
        if near:
            pr = catalogue()[near]
            t += _lang_text("near", lang, name=pr.name, desc=pr.description.lower())
        _merge(s, {k: v for k, v in u.items() if k != "needs" or s.profile.business_type == "manufacturer" or u.get("business_type") == "manufacturer"})  # factory needs go in the hand-off summary
        if s.profile.business_type == "manufacturer":  # custom need at a factory goes to a person
            _do_handoff(s, "manufacturer_custom")
            return _join(t, _lang_text("custom", lang))
        return _join(t, _steer(s))
    # A custom need at a factory goes to a person (rule 7), whichever order the owner mentioned the two in.
    factory = s.profile.business_type == "manufacturer" or u.get("business_type") == "manufacturer"
    if factory and s.handoff != "manufacturer_custom" and (G.asks_custom(text) or any(who == "user" and G.asks_custom(said) for who, said in s.history)):
        _merge(s, u)
        _do_handoff(s, "manufacturer_custom")
        return _lang_text("custom", lang)
    if G.PROMISE_ASK.search(text):
        if s.rec and s.rec.quote:
            l = max(s.rec.quote.lines, key=lambda x: x.install_days)
            return _lang_text("promise", lang, name=l.name, d=l.install_days)
        rest = _rest_of(s, text, G.PROMISE_ASK, found, lang, llm_client)
        return _join(_lang_text("decline_promise" if rest and s.rec and s.rec.quote else "promise0", lang), rest or _steer(s))
    faq = _faq(s, text, lang)
    if faq:
        _merge(s, {k: v for k, v in u.items() if k != "needs"})
        return _join(faq, _steer(s) if not (s.rec and s.rec.quote) else "")
    if s.rec and s.rec.quote and G.PROCEED.search(text) and not u:
        return _lang_text("proceed", lang)
    if s.rec and s.rec.alternative and G.CHEAPER_ASK.search(text) and not u:
        cat = catalogue()
        return _join(_lang_text("alt", lang, names=", ".join(cat[k].name for k in s.rec.alternative), m=s.rec.alt_quote.monthly), trade_text(s.rec, lang))
    if s.rec and THANKS.search(text) and not u:
        return _lang_text("next", lang)
    if s.awaiting == "needs_confirm" and not u.get("needs") and re.match(r"\s*((yes|yeah|ok|okay|haan|han|ji|theek)\b|हाँ|हां|जी|ठीक)", text.lower()):
        u["needs"] = ["internet_for_upi_pos" if s.profile.business_type in MICRO else "internet"]
    _merge(s, u)
    # Save free-tier quota: skip when nothing is missing, or for short answers like "6" or "Delhi".
    before = s.profile.model_dump()
    if next_question(s) and len(text.split()) > 3: _merge_llm(s, text, u)
    moved = bool(u) or s.profile.model_dump() != before
    if u.get("only") or (s.profile.needs and set(s.profile.needs) <= {"mobile_line", "mobile_premium"}):
        # A mobile-only request needs no site count; a staff count of 1 satisfies every P07 rule.
        s.profile.locations = s.profile.locations or 1
        s.profile.employees = s.profile.employees or 1
        s.profile.business_type = s.profile.business_type or "other"
    # A town we can't serve ends the discovery: further questions would waste the owner's time.
    f = None if s.profile.city_tier == 3 else next_question(s)
    if f:
        if not moved and s.awaiting is None and (said := _converse(s, text, lang, llm_client)):
            s.awaiting = f; s.rec = None
            if f not in s.asked: s.asked.append(f)
            return _join(said, _question(s, f, lang))
        if s.awaiting in (f, f + "_confirm") and not moved:  # the answer didn't move us on: clarify once, then a person helps
            s.stuck += 1
            # With the LLM up, side remarks get a real reply, and a person steps in a turn later.
            if s.stuck < 3 and (said := _converse(s, text, lang, llm_client)):
                s.awaiting = f
                return _join(said, _question(s, f, lang))
            if s.stuck >= 2:
                _do_handoff(s, "repeated_confusion")
                return _lang_text("handoff", lang)
            if f == "needs":
                s.awaiting = "needs_confirm"
                return _lang_text("suggest", lang)
            return _join(_lang_text("hint_gst" if f == "has_gstin" else "hint", lang), _question(s, f, lang))
        s.stuck = 0
        s.awaiting = f; s.rec = None
        if f == "city_tier" and s.profile.has_gstin is None and question_matters("has_gstin", s.profile):  # one turn for both, so an unlisted city stays within six questions
            s.asked.append("city_tier+has_gstin")
            return _join(Q[f][lang], _question(s, "has_gstin", lang))
        if f not in s.asked and not (f == "has_gstin" and "city_tier+has_gstin" in s.asked): s.asked.append(f)
        return _question(s, f, lang)
    if s.rec and s.rec.quote and not moved and (said := _converse(s, text, lang, llm_client)):
        return said  # a remark about the plan: answer it and keep the plan
    s.awaiting = None; s.stuck = 0
    s.rec = recommend(s.profile)
    if s.rec.handoff: _do_handoff(s, s.rec.handoff)
    draft = render_rec(s)
    return _polish(draft, s, llm_client) if s.rec.quote else draft
