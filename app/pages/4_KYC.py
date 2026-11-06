import sys, json, time; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent, orders
from core.kyc import messages as KM
from core.kyc.pipeline import FILES, MAX_PAGES, MAX_UPLOAD_MB, OcrUnavailable, load_specimen, look_up_gstin, look_up_udyam, open_upload, verify_files, verify_images
t = c.setup("KYC")
c.journey("kyc", t)
st.subheader(t["kyc"])
lang = st.session_state.ui_lang
hi = lang == "hi"
W = (lambda en, h: h if hi else en)
if consent.KYC not in consent.active(c.user()):
    st.warning(t["first_consent"]); c.link("pages/3_Consent.py", label=t["consent"], icon="✅"); st.stop()
DOCS = tuple(FILES)
LABEL = {"gstin": "GSTIN", "udyam": W("Udyam no.", "Udyam नंबर"), "id_no": W("ID no.", "ID नंबर"), "legal_name": W("Legal name", "कानूनी नाम"), "trade_name": W("Trade name", "व्यापार का नाम"),
         "constitution": W("Business type", "बिज़नेस का प्रकार"), "address": W("Address", "पता"), "name": W("Name", "नाम"), "city": W("City", "शहर"), "state": W("State", "राज्य"),
         "designation": W("Role", "पद"), "business": W("Business", "बिज़नेस"), "valid_till": W("Valid till", "मान्य तक"), "billed_to": W("Billed to", "बिल किसके नाम"), "date": W("Bill date", "बिल की तारीख")}

with st.form("lookup_form", clear_on_submit=True):  # clears the box: the number isn't kept on screen
    st.markdown(W("**Check your numbers first** (optional)", "**पहले अपने नंबर जाँचें** (वैकल्पिक)"))
    st.caption(W("An instant registry check, before you upload anything. We show only the status.", "कुछ भी अपलोड करने से पहले तुरंत रजिस्ट्री जाँच। हम केवल स्थिति दिखाते हैं।"))
    typed_g = st.text_input("GSTIN", placeholder="27ABCDE1234F1Z5", max_chars=20)
    typed_u = st.text_input(W("Udyam number", "Udyam नंबर"), placeholder="UDYAM-MH-00-1234567", max_chars=25)
    if st.form_submit_button(W("Check", "जाँचें"), use_container_width=True):
        found = {}
        if typed_g.strip():
            found["gst"] = look_up_gstin(typed_g)
            if found["gst"]["state"] != "bad_format": st.session_state.typed_gstin = typed_g  # compared with the certificate, then dropped; never stored
        if typed_u.strip(): found["udyam"] = look_up_udyam(typed_u)
        st.session_state.lookup = found
found = st.session_state.get("lookup") or {}
if "gst" in found:
    state, masked = found["gst"]["state"], found["gst"].get("masked", "")
    if state == "active": st.success(W(f"GSTIN {masked} is active. You can go ahead.", f"GSTIN {masked} सक्रिय है। आप आगे बढ़ सकते हैं।"))
    elif state in ("cancelled", "suspended"):
        word = W(state, KM.STATUS[state.title()][1])
        st.error(W(f"GSTIN {masked} is {word}, so we can't activate on it. If that's wrong, please talk to a person. You don't need to upload anything yet.", f"GSTIN {masked} {word} है, इसलिए इस पर सेवा चालू नहीं हो सकती। अगर यह ग़लत है, तो कृपया किसी व्यक्ति से बात करें। अभी कुछ अपलोड करने की ज़रूरत नहीं।"))
        c.link("pages/1_Advisor.py", label=W("Talk to a person", "किसी व्यक्ति से बात करें"), icon="🙋")
    elif state == "not_found": st.warning(W("We couldn't find this GSTIN in the registry. Please check it. You can still upload, and a person will review it.", "यह GSTIN रजिस्ट्री में नहीं मिला। कृपया जाँच लें। आप फिर भी अपलोड कर सकते हैं, कोई व्यक्ति इसकी जाँच करेगा।"))
    else: st.warning(W("That doesn't look like a valid GSTIN. Please check for a typo. It has 15 characters, like 27ABCDE1234F1Z5.", "यह सही GSTIN नहीं लगता। कृपया टाइपिंग की ग़लती जाँच लें। इसमें 15 अक्षर होते हैं, जैसे 27ABCDE1234F1Z5।"))
if "udyam" in found:
    state, masked = found["udyam"]["state"], found["udyam"].get("masked", "")
    if state == "found": st.success(W(f"Udyam number {masked} is in the registry.", f"Udyam नंबर {masked} रजिस्ट्री में है।"))
    elif state == "not_found": st.warning(W("We couldn't find this Udyam number in the registry. Please check it. You can still upload, and a person will review it.", "यह Udyam नंबर रजिस्ट्री में नहीं मिला। कृपया जाँच लें। आप फिर भी अपलोड कर सकते हैं, कोई व्यक्ति इसकी जाँच करेगा।"))
    else: st.warning(W("That doesn't look like a Udyam number. It should look like UDYAM-MH-00-1234567.", "यह Udyam नंबर नहीं लगता। यह UDYAM-MH-00-1234567 जैसा होना चाहिए।"))

mode = st.radio(t["docs"], ["specimen", "upload"], format_func=lambda m: t[m], horizontal=True)
images, pages, source, problems = {}, [], None, False
if mode == "specimen":
    who = st.selectbox(t["applicant"], [f"K{i:02d}" for i in range(1, 13)])
    images, source = load_specimen(who), who
    if st.toggle(W("Show these documents", "ये दस्तावेज़ दिखाएँ")):
        for k, img in images.items(): st.image(img, caption=KM.DOC_NAME[k][lang], use_container_width=True)
        if len(images) < len(DOCS): st.caption(W("This applicant sent only these documents.", "इस आवेदक ने केवल ये दस्तावेज़ भेजे।"))
else:
    source = "upload"
    st.caption(W(f"Add all your documents together, in any order. We work out which is which. Photos or PDFs, up to {MAX_UPLOAD_MB} MB each. Files are read in memory and never stored.", f"अपने सभी दस्तावेज़ एक साथ, किसी भी क्रम में जोड़ें। कौन-सा क्या है, यह हम पहचान लेंगे। फ़ोटो या PDF, हर फ़ाइल {MAX_UPLOAD_MB} MB तक। फ़ाइलें केवल मेमोरी में पढ़ी जाती हैं, सहेजी नहीं जातीं।"))
    the_order = orders.get(st.session_state["order_id"]) if st.session_state.get("order_id") else None
    no_gst_needed = bool(the_order) and not orders.needs_gstin(the_order)
    if no_gst_needed: st.info(W("Your plan doesn't need a GSTIN. If you don't have one, your signatory ID and address proof are enough.", "आपके प्लान के लिए GSTIN ज़रूरी नहीं। GSTIN न हो तो हस्ताक्षरकर्ता की ID और पते का प्रमाण काफ़ी है।"))
    nonce = st.session_state.setdefault("upload_nonce", 0)
    files = st.file_uploader(t["docs"], type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key=f"up_all_{nonce}")
    WHY = {"too_big": W(f"is larger than we accept ({MAX_UPLOAD_MB} MB). Please send a smaller copy.", f"सीमा ({MAX_UPLOAD_MB} MB) से बड़ी है। कृपया छोटी कॉपी भेजें।"),
           "too_many": W(f"has more than {MAX_PAGES} pages. Please send only the pages we need.", f"में {MAX_PAGES} से ज़्यादा पेज हैं। कृपया केवल ज़रूरी पेज भेजें।"),
           "bad_file": W("can't be opened. It may be damaged, password-protected or not a real image or PDF. Please choose another.", "खुल नहीं रही। हो सकता है यह ख़राब हो, पासवर्ड से सुरक्षित हो, या असली इमेज या PDF न हो। कृपया दूसरी चुनें।")}
    for f in files:
        got, why = open_upload(f)  # held in memory only, never written to disk
        pages += got
        if why:
            problems = True
            st.error(W(f"{f.name} ", f"{f.name} ") + WHY[why])
    if len(pages) > MAX_PAGES:
        problems = True
        st.error(W(f"That's {len(pages)} pages. Please send {MAX_PAGES} or fewer.", f"ये {len(pages)} पेज हैं। कृपया {MAX_PAGES} या कम भेजें।"))

if st.button(t["verify"], type="primary", use_container_width=True, disabled=not (images or pages) or problems):
    bar, started = st.progress(0.0, t["reading"]), time.monotonic()
    try:
        if mode == "specimen":
            r = verify_images(images, progress=lambda k, n, total: bar.progress(n / total, W(f"Reading {KM.DOC_NAME[k]['en']}...", f"{KM.DOC_NAME[k]['hi']} पढ़ा जा रहा है...")))
        else:
            r = verify_files(pages, st.session_state.get("typed_gstin"), progress=lambda n, total: bar.progress(n / total, W(f"Reading file {n + 1} of {total}...", f"{total} में से फ़ाइल {n + 1} पढ़ी जा रही है...")), gst_optional=no_gst_needed)
            st.session_state.pop("typed_gstin", None)
    except OcrUnavailable:  # nothing was read, so this says nothing about the documents
        bar.empty()
        st.error(W("We can't read documents right now. This isn't about your documents, and nothing has been saved. Please try again shortly.", "अभी हम दस्तावेज़ नहीं पढ़ पा रहे। इसका आपके दस्तावेज़ों से कोई लेना-देना नहीं, और कुछ सहेजा नहीं गया। कृपया थोड़ी देर बाद कोशिश करें।"))
        st.stop()
    bar.empty(); images.clear(); pages.clear()
    st.session_state.pop("lookup", None)  # the result below replaces it, and an old "go ahead" must not sit above a different verdict
    consent.save_kyc(c.user(), r.verdict, r.reason, json.dumps(r.fields))
    st.session_state.kyc_result = {"verdict": r.verdict, "source": source, "fields": r.fields, "read": r.read, "checks": r.checks, "unused": r.unused, "seconds": round(time.monotonic() - started, 1),
                                   "issues": [(i.severity, i.code, i.params) for i in r.issues]}
    oid = st.session_state.get("order_id")
    if r.verdict == "verified" and oid and orders.get(oid)["stage"] == "Quote accepted":
        orders.advance(oid, "KYC verified")
    st.session_state.upload_nonce = st.session_state.get("upload_nonce", 0) + 1  # new widget keys drop the uploaded files from the session
    st.rerun()

res = st.session_state.get("kyc_result")
if res and (consent.latest_kyc(c.user()) is None or "checks" not in res):  # erased when consent was withdrawn, or from before a deploy: never show it
    st.session_state.pop("kyc_result"); res = None
oid = st.session_state.get("order_id")
if res:
    verdict, issues = res["verdict"], res["issues"]
    shown = [x for x in issues if x[0] == "reject"] or issues
    reason = (KM.VERIFIED_HI if hi else KM.VERIFIED_EN) if verdict == "verified" else " ".join(KM.issue_text(code, p, lang) for _, code, p in shown)
    who = W("your documents", "आपके दस्तावेज़") if res["source"] == "upload" else res["source"]
    st.markdown(f"**{W('Result for', 'परिणाम:')} {who}**")
    {"verified": st.success, "needs_review": st.warning, "rejected": st.error}[verdict](f"**{t['verdicts'][verdict]}**: {reason}")
    if verdict == "needs_review":
        st.markdown(W("**What happens next:** your order waits while a person on our team checks this. You can also fix what's marked below and verify again.", "**आगे क्या होगा:** जब तक हमारी टीम का कोई व्यक्ति इसकी जाँच करता है, आपका ऑर्डर रुका रहेगा। आप नीचे बताई गई चीज़ ठीक करके दोबारा सत्यापित भी कर सकते हैं।"))
    if verdict == "rejected":
        st.markdown(W("**What happens next:** we can't activate on these documents. If you think this is wrong, a person can look at it.", "**आगे क्या होगा:** इन दस्तावेज़ों पर सेवा चालू नहीं हो सकती। अगर आपको लगता है कि यह ग़लत है, तो कोई व्यक्ति इसे देख सकता है।"))
    if verdict != "verified":
        c.link("pages/1_Advisor.py", label=W("Talk to a person", "किसी व्यक्ति से बात करें"), icon="🙋")
    for doc in DOCS:
        mine = [x for x in issues if KM.issue_doc(x[1]) == doc]
        ok = [x for x in res["checks"] if KM.passed_doc(x[0]) == doc]
        read = res["read"].get(doc, {})
        icon = "❌" if any(x[0] == "reject" for x in mine) else "⚠️" if mine else "✅" if ok or read else "➖"
        with st.expander(f"{icon} {KM.DOC_NAME[doc][lang]}", expanded=bool(mine)):
            for sev, code, p in mine: (st.error if sev == "reject" else st.warning)(KM.issue_text(code, p, lang))
            for code, p in ok: st.markdown(f"✓ {KM.passed_text(code, p, lang)}")
            if read:
                st.caption(W("What we read", "हमने क्या पढ़ा"))
                st.markdown("  \n".join(f"{LABEL.get(k, k)}: {v}" for k, v in read.items()))
    f = res["fields"]
    saved = [f"GSTIN {f['gstin_masked']}" if f.get("gstin_masked") else "", f"{W('Registry status', 'रजिस्ट्री स्थिति')}: {f['registry_status']}" if f.get("registry_status") else "", f"ID {f['id_masked']}" if f.get("id_masked") else ""]
    if any(saved): st.caption(f"{t['stored']}: " + " · ".join(x for x in saved if x))
    if res.get("unused"): st.caption(W(f"We couldn't recognise {res['unused']} of your files, so we didn't use them.", f"आपकी {res['unused']} फ़ाइलें पहचानी नहीं जा सकीं, इसलिए उनका उपयोग नहीं हुआ।"))
    if res.get("seconds"): st.caption(W(f"Checked in {res['seconds']} seconds.", f"{res['seconds']} सेकंड में जाँचा गया।"))
    st.caption(t["kyc_note"])
last = consent.latest_kyc(c.user())
if last and last["verdict"] == "verified" and not oid:
    st.info(W("Your documents are verified. Accept a quote to continue.", "आपके दस्तावेज़ सत्यापित हैं। आगे बढ़ने के लिए कोटेशन स्वीकार करें।")); c.link("pages/2_Quote.py", label=t["quote"], icon="🧾")
if oid and last and orders.can_pay(orders.get(oid), last["verdict"]):
    if st.button(f"{t['pay']} · ₹{orders.first_due(orders.get(oid)):,}", use_container_width=True):
        orders.advance(oid, "Payment done"); st.session_state.paid_notice = True; st.rerun()  # rerun so the progress bar shows it too
if st.session_state.pop("paid_notice", False): st.success(t["paid"])
c.link("pages/5_Tracker.py", label=t["tracker"], icon="📦")
