"""Works out what kind of message the owner sent, so the advisor can answer it instead of treating everything as an answer
to its last question. Decides nothing about products or prices."""
import re

_G = r"hi+|hello+|hey+|hii+|namaste|namaskar|नमस्ते|नमस्कार|good (morning|afternoon|evening)"
_HOW = r"how are you( doing)?|how's it going|kaise ho|kaise hain( aap)?|aap kaise hain|kya haal( hai)?|आप कैसे हैं|कैसे हो"
_SOCIAL = {
    "how_are_you": re.compile(rf"^\W*(({_G})\W+)?({_HOW})\W*$", re.I),
    "greeting": re.compile(rf"^\W*({_G})(\W+there)?\W*$", re.I),
    "thanks": re.compile(r"^\W*((ok|okay|great|cool)\W+)?(thanks?( a lot| so much)?|thank you( so much)?|thx|ty|shukriya|dhanyavaad|dhanyawad|धन्यवाद|शुक्रिया)(\W+(that|this|it)?\W*(makes sense|helps|helped))?\W*$", re.I),
    "filler": re.compile(r"^\W*(ok+|okay|okk+|hm+|hmm+|cool|nice|great|acha|achha|accha|sure|alright|got it|understood|makes sense|that makes sense|samajh gaya|अच्छा|ठीक|समझ गया)\W*$", re.I),
}
_TOPICS = {
    "compare_link": re.compile(r"(fib\w*|air ?fib\w*|5g|फाइबर).{0,50}(difference|farak|fark|antar|अंतर|फर्क|फ़र्क)|(difference|differ|farak|fark|antar|अंतर|फर्क|फ़र्क|compare|\bvs\b|versus|better|behtar|बेहतर).{0,40}(fib|air ?fib|5g|फाइबर)|(fib\w*|फाइबर).{0,25}(\bor\b|\bya\b|या|\bvs\b|versus).{0,25}(air ?fib|5g|wireless)\W*(\?|kya|which|कौन)|(air ?fib\w*|5g).{0,25}(\bor\b|\bya\b|या|\bvs\b|versus).{0,25}fib\w*\W*\?", re.I),
    "why_costly": re.compile(r"\bwhy\b.{0,30}(expensive|costly|so much|so high|price|cost)|(so|this) (expensive|costly)|itna (mehenga|mehnga|zyada)|(mehenga|mehnga|costly) (kyun|kyu)|इतना (महंगा|ज़्यादा|ज्यादा)|महंगा क्यों", re.I),
    "need_item": re.compile(r"do i (really |actually )?need|is (the |this |that )?.{0,25}(necessary|needed|required|a must|mandatory)|why (do i need|did you add|have you added|is there|add)|what('s| is) .{0,20}\bfor\b|(zaroori|zaruri|jaroori) (hai|h)|(kyun|kyu) (chahiye|add|joda|lagaya)|ज़रूरी है|जरूरी है|क्यों (चाहिए|जोड़ा)", re.I),
    "pick": re.compile(r"what (do|would) you (think|suggest|recommend|pick|advise)|which (one )?(would|should|do you)|what should i (get|take|buy|choose)|what do i need|\byou (decide|choose|tell me)\b|aap (hi |hee )?(bata|batao|batayein|bataiye|decide)|kya lena chahiye|kya lu\b|kya loon|क्या लेना चाहिए|क्या लूँ|सुझाए|सुझाव दीजिए|आप ही बता|आप बताइए|आप बताओ", re.I),
    "capabilities": re.compile(r"what can you do|what do you (do|offer|sell|have)|how can you help|who are you|what is this( app)?\W*$|kya kya (milta|hai|mil)|aap kya (karte|kar sakte)|आप क्या (करते|कर सकते)|क्या क्या मिलता", re.I),
    "what_is": re.compile(r"^\W*(what('s| is| are)|tell me about|explain)\b(?!.*\b(price|cost|plan)\b)|\bkya (hota|hoti|hai)\W*$|क्या (होता|होती) है", re.I),
}
_QUESTION = re.compile(r"\?\s*$|^\W*(why|what|how|which|when|where|who|does|do|did|is|are|can|could|will|would|should|kya|kaise|kyun|kyu|kitna|kitne|kaun|क्या|कैसे|क्यों|कितना|कितने|कौन)\b", re.I)
PLAN_ASK = re.compile(r"\bplan\b|price|cost|how much|again|show|summary|total|kitna|kitne|दिखा|कीमत|कितना|प्लान", re.I)
_PROBLEM = re.compile(r"keeps? (dropping|failing|going)|\bdrops?\b|dropping|\bslow\b|not working|doesn'?t work|complain|problem|\bissue|trouble|band ho|nahi chal|nahin chal|dikkat|pareshan|समस्या|दिक्कत|परेशान|बंद हो|नहीं चल", re.I)


def social(text: str) -> str | None:
    return next((k for k, rx in _SOCIAL.items() if rx.search(text)), None)


def topic(text: str) -> str | None:
    return next((k for k, rx in _TOPICS.items() if rx.search(text)), None)


def is_question(text: str) -> bool:
    return bool(_QUESTION.search(text))


def has_problem(text: str) -> bool:
    return bool(_PROBLEM.search(text))


TALK = {
    "greeting": {"en": "Hello!", "hi": "नमस्ते!", "hinglish": "Namaste!"},
    "how_are_you": {"en": "I'm doing well, thanks for asking!", "hi": "मैं ठीक हूँ, पूछने के लिए धन्यवाद!", "hinglish": "Main theek hoon, poochne ke liye shukriya!"},
    "thanks": {"en": "You're welcome!", "hi": "आपका स्वागत है!", "hinglish": "Koi baat nahi!"},
    "filler": {"en": "Take your time.", "hi": "आराम से बताइए।", "hinglish": "Aaram se bataiye."},
    "problem": {"en": "Sorry you're dealing with that.", "hi": "यह सुनकर अफ़सोस हुआ।", "hinglish": "Yeh sunkar afsos hua."},
    "cant_confirm": {"en": "I can't confirm that here, but a specialist can if you use \"Talk to a person\".", "hi": "मैं यहाँ इसकी पुष्टि नहीं कर सकता, पर \"किसी व्यक्ति से बात करें\" से विशेषज्ञ बता सकते हैं।", "hinglish": "Main yahan iski confirm nahi kar sakta, par \"Talk to a person\" se specialist bata sakte hain."},
    "plan_stays": {"en": "Your plan is still ₹{m:,} per month. Tell me if you'd like to change anything, or open the Quote page.", "hi": "आपका प्लान अभी भी ₹{m:,} प्रति माह है। कुछ बदलना हो तो बताएँ, या Quote पेज खोलें।", "hinglish": "Aapka plan abhi bhi ₹{m:,} per month hai. Kuch change karna ho to bataiye, ya Quote page kholiye."},
    "capabilities": {"en": "I help small businesses find the smallest telecom plan that fits: internet, mobile lines, email, CCTV, WhatsApp, billing and more. You get one clear monthly price, then you can finish verification and track your order here.", "hi": "मैं छोटे बिज़नेस के लिए सबसे छोटा सही टेलीकॉम प्लान ढूँढने में मदद करता हूँ: इंटरनेट, मोबाइल लाइन, ईमेल, सीसीटीवी, WhatsApp, बिलिंग और भी बहुत कुछ। आपको एक साफ़ मासिक कीमत मिलती है, फिर आप यहीं सत्यापन पूरा करके ऑर्डर ट्रैक कर सकते हैं।", "hinglish": "Main small businesses ke liye sabse chhota sahi telecom plan dhoondhne mein help karta hoon: internet, mobile lines, email, CCTV, WhatsApp, billing aur bahut kuch. Aapko ek clear monthly price milta hai, phir aap yahin verification poora karke order track kar sakte hain."},
    "compare": {"en": "{a} is wired fibre at ₹{am:,} per month on a {ac}-month contract, and usually takes about {ad} days to install. {b} is wireless 5G at ₹{bm:,} per month on a {bc}-month contract, and usually takes about {bd} days. Backup failover and Static IP only work on wired fibre.",
                "hi": "{a} तार वाला फाइबर है: ₹{am:,} प्रति माह, {ac} महीने का अनुबंध, इंस्टॉलेशन में आमतौर पर लगभग {ad} दिन। {b} वायरलेस 5G है: ₹{bm:,} प्रति माह, {bc} महीने का अनुबंध, आमतौर पर लगभग {bd} दिन। बैकअप फेलओवर और Static IP केवल वायर्ड फाइबर पर चलते हैं।",
                "hinglish": "{a} wired fibre hai: ₹{am:,} per month, {ac} months ka contract, installation mein usually lagbhag {ad} din. {b} wireless 5G hai: ₹{bm:,} per month, {bc} months ka contract, usually lagbhag {bd} din. Backup failover aur Static IP sirf wired fibre par chalte hain."},
    "in_plan": {"en": "Your plan uses {name}: {why}", "hi": "आपके प्लान में {name} है: {why}", "hinglish": "Aapke plan mein {name} hai: {why}"},
    "breakdown": {"en": "Here's what makes up your ₹{m:,}: {lines}.", "hi": "आपके ₹{m:,} में यह शामिल है: {lines}।", "hinglish": "Aapke ₹{m:,} mein yeh shamil hai: {lines}."},
    "no_price_yet": {"en": "I haven't priced anything yet. You'll see one clear monthly price once I know a little more.", "hi": "मैंने अभी कोई कीमत नहीं बताई है। थोड़ी और जानकारी के बाद आपको एक साफ़ मासिक कीमत दिखेगी।", "hinglish": "Maine abhi koi price nahi bataya. Thodi aur jaankari ke baad aapko ek clear monthly price dikhega."},
    "alt_line": {"en": "The cheaper option is {names} at ₹{m:,} per month.", "hi": "सस्ता विकल्प {names} है, ₹{m:,} प्रति माह।", "hinglish": "Sasta option {names} hai, ₹{m:,} per month."},
    "optional": {"en": "It's your call: tell me if you'd like it removed, and the price updates.", "hi": "फ़ैसला आपका है: हटाना हो तो बताएँ, कीमत अपडेट हो जाएगी।", "hinglish": "Faisla aapka hai: hatana ho to bataiye, price update ho jayega."},
    "not_in_plan": {"en": "{name} isn't in your plan: {desc}. Tell me if you'd like it added.", "hi": "{name} आपके प्लान में नहीं है: {desc}। जोड़ना हो तो बताएँ।", "hinglish": "{name} aapke plan mein nahi hai: {desc}. Add karna ho to bataiye."},
    "explain": {"en": "{name}: {desc}.", "hi": "{name}: {desc}।", "hinglish": "{name}: {desc}."},
    "pick_plan": {"en": "From what you've told me, I'd stay with this plan: {why}", "hi": "आपकी बताई बातों के हिसाब से मैं यही प्लान रखूँगा: {why}", "hinglish": "Aapki batayi baaton ke hisaab se main yahi plan rakhunga: {why}"},
    "pick_later": {"en": "I'll pick the smallest plan that fits as soon as I have a bit more.", "hi": "थोड़ी और जानकारी मिलते ही मैं सबसे छोटा सही प्लान चुन दूँगा।", "hinglish": "Thodi aur jaankari milte hi main sabse chhota sahi plan chun dunga."},
    "got": {"en": "Got it", "hi": "समझ गया", "hinglish": "Samajh gaya"},
}
PEOPLE = {"en": ("{n} person", "{n} people"), "hi": ("{n} व्यक्ति", "{n} लोग"), "hinglish": ("{n} log", "{n} log")}
SITES = {"en": ("{n} location", "{n} locations"), "hi": ("{n} लोकेशन", "{n} लोकेशन"), "hinglish": ("{n} location", "{n} locations")}
KIND = {"kirana": ("a kirana store", "किराना", "kirana"), "salon": ("a salon", "सैलून", "salon"), "pharmacy": ("a pharmacy", "फ़ार्मेसी", "pharmacy"), "clinic": ("a clinic", "क्लिनिक", "clinic"),
        "ca_firm": ("a CA firm", "सीए फर्म", "CA firm"), "coaching": ("a coaching centre", "कोचिंग", "coaching"), "restaurant": ("a restaurant or cafe", "रेस्टोरेंट या कैफ़े", "restaurant ya cafe"), "retailer": ("a shop", "दुकान", "dukan"),
        "manufacturer": ("a factory", "फैक्ट्री", "factory"), "office": ("an office", "ऑफिस", "office")}
