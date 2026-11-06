import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent, orders
from core.kyc import messages as KM
from core.kyc.pipeline import FILES, MAX_UPLOAD_MB, load_specimen, open_upload, verify_images
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

mode = st.radio(t["docs"], ["specimen", "upload"], format_func=lambda m: t[m], horizontal=True)
images, source, problems = {}, None, False
if mode == "specimen":
    who = st.selectbox(t["applicant"], [f"K{i:02d}" for i in range(1, 13)])
    images, source = load_specimen(who), who
    if st.toggle(W("Show these documents", "ये दस्तावेज़ दिखाएँ")):
        for k, img in images.items(): st.image(img, caption=KM.DOC_NAME[k][lang], use_container_width=True)
        if len(images) < len(DOCS): st.caption(W("This applicant sent only these documents.", "इस आवेदक ने केवल ये दस्तावेज़ भेजे।"))
else:
    source = "upload"
    st.caption(W(f"PNG or JPG, up to {MAX_UPLOAD_MB} MB each. Files are read in memory and never stored.", f"PNG या JPG, हर फ़ाइल {MAX_UPLOAD_MB} MB तक। फ़ाइलें केवल मेमोरी में पढ़ी जाती हैं, सहेजी नहीं जातीं।"))
    nonce = st.session_state.setdefault("upload_nonce", 0)
    for k in DOCS:
        f = st.file_uploader(t[f"doc_{k}"], type=["png", "jpg", "jpeg"], key=f"up_{k}_{nonce}")
        if not f: continue
        img, why = open_upload(f)  # held in memory only, never written to disk
        if img is not None: images[k] = img
        else:
            problems = True
            st.error(W(f"This file is larger than we accept ({MAX_UPLOAD_MB} MB). Please send a smaller photo.", f"यह फ़ाइल सीमा ({MAX_UPLOAD_MB} MB) से बड़ी है। कृपया छोटी फ़ोटो भेजें।") if why == "too_big"
                     else W("We can't open this file. It may be damaged or not a real image. Please choose another.", "यह फ़ाइल खुल नहीं रही। हो सकता है यह ख़राब हो या असली इमेज न हो। कृपया दूसरी चुनें।"))
    if images and len(images) < len(DOCS) and not problems:
        st.caption(W(f"{len(images)} of {len(DOCS)} added. Anything missing goes to a person to review.", f"{len(DOCS)} में से {len(images)} जोड़े गए। जो नहीं है उसकी जाँच कोई व्यक्ति करेगा।"))

if st.button(t["verify"], type="primary", use_container_width=True, disabled=not images or problems):
    bar = st.progress(0.0, t["reading"])
    r = verify_images(images, progress=lambda k, n, total: bar.progress(n / total, W(f"Reading {KM.DOC_NAME[k]['en']}...", f"{KM.DOC_NAME[k]['hi']} पढ़ा जा रहा है...")))
    bar.empty(); images.clear()
    consent.save_kyc(c.user(), r.verdict, r.reason, json.dumps(r.fields))
    st.session_state.kyc_result = {"verdict": r.verdict, "source": source, "fields": r.fields, "read": r.read, "checks": r.checks,
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
    st.caption(t["kyc_note"])
last = consent.latest_kyc(c.user())
if last and last["verdict"] == "verified" and not oid:
    st.info(W("Your documents are verified. Accept a quote to continue.", "आपके दस्तावेज़ सत्यापित हैं। आगे बढ़ने के लिए कोटेशन स्वीकार करें।")); c.link("pages/2_Quote.py", label=t["quote"], icon="🧾")
if oid and last and last["verdict"] == "verified" and orders.get(oid)["stage"] == "KYC verified":
    if st.button(t["pay"], use_container_width=True):
        orders.advance(oid, "Payment done"); st.session_state.paid_notice = True; st.rerun()  # rerun so the progress bar shows it too
if st.session_state.pop("paid_notice", False): st.success(t["paid"])
c.link("pages/5_Tracker.py", label=t["tracker"], icon="📦")
