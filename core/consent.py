"""Purpose-specific consent records (DPDP Act 2023). One row per purpose; withdrawal is a timestamp, not a delete."""
from . import db

NOTICE_VERSION = "v1.2-2026-07"  # change this whenever NOTICE or NOTICE_SHORT changes, so each record shows what the person actually saw
KYC, UPDATES, CALLBACK = "kyc_verification", "order_updates", "callback_contact"
REQUIRED = {KYC}
PURPOSE_LABEL = {KYC: {"en": "KYC verification", "hi": "KYC सत्यापन"}, UPDATES: {"en": "Order updates", "hi": "ऑर्डर अपडेट"}, CALLBACK: {"en": "Call-back from our team", "hi": "हमारी टीम से कॉल बैक"}}
# Shown first. It keeps what DPDP s.5 needs up front: the data, the purpose, how to use your rights and how to complain.
NOTICE_SHORT = {
 "en": """
**We collect:** your GST and Udyam certificates, signatory ID and address proof.

**Why:** only to verify your business and activate your connection. Originals are deleted right after verification.

**Your rights:** withdraw any time on this page or in the tracker. For complaints, use "Talk to a person" on the Advisor page, then the Data Protection Board of India.
""",
 "hi": """
**हम क्या लेते हैं:** आपके GST और Udyam प्रमाणपत्र, हस्ताक्षरकर्ता की ID और पते का प्रमाण।

**क्यों:** केवल आपके बिज़नेस के सत्यापन और कनेक्शन चालू करने के लिए। मूल दस्तावेज़ सत्यापन के तुरंत बाद हटा दिए जाते हैं।

**आपके अधिकार:** इसी पेज पर या ट्रैकर में कभी भी सहमति वापस लें। शिकायत के लिए Advisor पेज पर "किसी व्यक्ति से बात करें" का उपयोग करें, फिर भारत के डेटा संरक्षण बोर्ड से संपर्क करें।
"""}
NOTICE = {
 "en": """
**What we collect:** GST and Udyam certificates, signatory ID, address proof.

**Why:** only to verify your business and activate your connection. Order updates are a separate choice below.

**How long:** original documents are deleted right after verification. Extracted details and the result are kept for the life of your service.

**Who sees it:** only the Accel Business KYC team. ID numbers show the last 4 digits only. Documents are never sent to an AI service.

**Your choices:** you can withdraw consent at any time on this page or in the tracker. Withdrawing KYC consent deletes your saved KYC result and puts your order on hold.

**Questions or complaints:** use "Talk to a person" on the Advisor page. If that doesn't resolve it, you can complain to the Data Protection Board of India.
""",
 "hi": """
**हम क्या लेते हैं:** GST और Udyam प्रमाणपत्र, हस्ताक्षरकर्ता की ID, पते का प्रमाण।

**क्यों:** केवल आपके बिज़नेस के सत्यापन और कनेक्शन चालू करने के लिए। ऑर्डर अपडेट नीचे एक अलग विकल्प है।

**कितने समय तक:** मूल दस्तावेज़ सत्यापन के तुरंत बाद हटा दिए जाते हैं। निकाली गई जानकारी और परिणाम सेवा अवधि तक रखे जाते हैं।

**कौन देखता है:** केवल Accel Business की KYC टीम। ID नंबर छिपाकर (अंतिम 4 अंक) दिखते हैं। दस्तावेज़ किसी AI सेवा को नहीं भेजे जाते।

**आपके विकल्प:** आप इसी पेज पर या ट्रैकर में कभी भी सहमति वापस ले सकते हैं। KYC सहमति वापस लेने पर आपका सेव किया KYC परिणाम हट जाएगा और ऑर्डर रुक जाएगा।

**सवाल या शिकायत:** Advisor पेज पर "किसी व्यक्ति से बात करें" का उपयोग करें। समाधान न होने पर आप भारत के डेटा संरक्षण बोर्ड से शिकायत कर सकते हैं।
"""}

# What to keep ready. Each line says only what core/kyc/checks.py really checks.
DOCS_NEEDED = {
 "gst": {"en": ("GST certificate", "shows your business is registered and active."),
         "hi": ("GST प्रमाणपत्र", "दिखाता है कि आपका बिज़नेस पंजीकृत और सक्रिय है।")},
 "udyam": {"en": ("Udyam certificate", "confirms your enterprise's number, name and location."),
           "hi": ("Udyam प्रमाणपत्र", "आपके उद्यम का नंबर, नाम और जगह पुष्ट करता है।")},
 "id": {"en": ("Signatory ID", "shows who signs for the business. It must be for this business and not expired. If someone else signs, get it from them first."),
        "hi": ("हस्ताक्षरकर्ता की ID", "दिखाती है कि बिज़नेस के लिए कौन हस्ताक्षर करता है। यह इसी बिज़नेस की हो और इसकी अवधि बाकी हो। अगर कोई और हस्ताक्षर करता है, तो पहले उनसे ले लें।")},
 "bill": {"en": ("Address proof", "a bill under 90 days old, in your business's name and at its registered address."),
          "hi": ("पते का प्रमाण", "90 दिन से कम पुराना बिल, आपके बिज़नेस के नाम पर और उसके पंजीकृत पते का।")},
}
DOCS_TIP = {"en": "Clear photos or PDFs work best, because blurred ones can't be read. You can send them all at once, in any order. Missing a document? Send what you have and a person will review it.",
            "hi": "साफ़ फ़ोटो या PDF सबसे अच्छे रहते हैं, क्योंकि धुंधली फ़ोटो पढ़ी नहीं जा सकती। आप सब एक साथ, किसी भी क्रम में भेज सकते हैं। कोई दस्तावेज़ नहीं है? जो है वह भेजें, कोई व्यक्ति उसकी जाँच करेगा।"}
RECEIPT = {
 "en": dict(title="Accel Business consent receipt", ref="Reference", notice="Notice version", language="Language", given="Given", status="Status", active="Active", withdrawn="Withdrawn",
            foot="You can withdraw any active consent at any time on the consent page or in the tracker. All times are UTC. This is a demo with synthetic data."),
 "hi": dict(title="Accel Business सहमति रसीद", ref="संदर्भ", notice="सूचना संस्करण", language="भाषा", given="दी गई", status="स्थिति", active="सक्रिय", withdrawn="वापस ली गई",
            foot="आप किसी भी सक्रिय सहमति को कभी भी सहमति पेज पर या ट्रैकर में वापस ले सकते हैं। सभी समय UTC में हैं। यह सिंथेटिक डेटा वाला डेमो है।"),
}
LANGUAGE_NAME = {"en": "English", "hi": "हिन्दी"}


def grant(user: str, purpose: str, language: str) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO consent(user,purpose,notice_version,language,granted_at) VALUES(?,?,?,?,?)",
                  (user, purpose, NOTICE_VERSION, language, db.now()))


def active(user: str) -> set[str]:
    with db.conn() as c:
        return {r["purpose"] for r in c.execute("SELECT purpose FROM consent WHERE user=? AND withdrawn_at IS NULL", (user,))}


def withdraw(user: str, purpose: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE consent SET withdrawn_at=? WHERE user=? AND purpose=? AND withdrawn_at IS NULL", (db.now(), user, purpose))
        if purpose == KYC:  # stop processing and erase what that consent allowed us to keep
            c.execute("DELETE FROM kyc WHERE user=?", (user,))
        if purpose == CALLBACK:
            c.execute("DELETE FROM callbacks WHERE user=?", (user,))


def records(user: str) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT purpose,notice_version,language,granted_at,withdrawn_at FROM consent WHERE user=? ORDER BY id", (user,))]


def receipt_text(user: str, language: str) -> str:
    """What was agreed and when, from the stored records only. Never holds document details or contact details."""
    w, lines = RECEIPT[language], []
    when = lambda ts: ts[:16].replace("T", " ")
    lines += [w["title"], f"{w['ref']}: {user}", ""]
    for r in records(user):
        lines += [PURPOSE_LABEL.get(r["purpose"], {}).get(language, r["purpose"]),
                  f"  {w['notice']}: {r['notice_version']}",
                  f"  {w['language']}: {LANGUAGE_NAME.get(r['language'], r['language'])}",
                  f"  {w['given']}: {when(r['granted_at'])}",
                  f"  {w['status']}: " + (f"{w['withdrawn']} {when(r['withdrawn_at'])}" if r["withdrawn_at"] else w["active"]), ""]
    return "\n".join(lines + [w["foot"]]) + "\n"


def save_kyc(user: str, verdict: str, reason: str, fields_json: str) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO kyc(user,verdict,reason,fields,ts) VALUES(?,?,?,?,?)", (user, verdict, reason, fields_json, db.now()))


def kyc_queue() -> list[dict]:
    """Each person's latest KYC result that a person still has to look at. Reasons and codes hold no names or numbers."""
    with db.conn() as c:
        rows = c.execute("SELECT user,verdict,reason,fields,ts FROM kyc WHERE id IN (SELECT MAX(id) FROM kyc GROUP BY user) AND verdict<>'verified' ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def latest_kyc(user: str) -> dict | None:
    with db.conn() as c:
        r = c.execute("SELECT verdict,reason,fields,ts FROM kyc WHERE user=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
    return dict(r) if r else None
