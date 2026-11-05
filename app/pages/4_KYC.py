import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from PIL import Image
from core import consent, orders
from core.kyc.pipeline import verify_images, load_specimen
t = c.setup("KYC")
c.journey("kyc", t)
st.subheader(t["kyc"])
if consent.KYC not in consent.active(c.user()):
    st.warning(t["first_consent"]); c.link("pages/3_Consent.py", label=t["consent"], icon="✅"); st.stop()
mode = st.radio(t["docs"], ["specimen", "upload"], format_func=lambda m: t[m], horizontal=True)
images = {}
if mode == "specimen":
    who = st.selectbox(t["applicant"], [f"K{i:02d}" for i in range(1, 13)])
    images = load_specimen(who)
else:
    nonce = st.session_state.setdefault("upload_nonce", 0)
    for k in ("gst", "udyam", "id", "bill"):
        f = st.file_uploader(t[f"doc_{k}"], type=["png", "jpg", "jpeg"], key=f"up_{k}_{nonce}")
        if f: images[k] = Image.open(f).copy()  # held in memory only, never written to disk
if st.button(t["verify"], type="primary", use_container_width=True, disabled=not images):
    with st.spinner(t["reading"]):
        r = verify_images(images)
    images.clear()
    consent.save_kyc(c.user(), r.verdict, r.reason, json.dumps(r.fields))
    st.session_state.kyc_result = {"verdict": r.verdict, "reason": r.reason, "passed": r.passed, "fields": r.fields}
    oid = st.session_state.get("order_id")
    if r.verdict == "verified" and oid and orders.get(oid)["stage"] == "Quote accepted":
        orders.advance(oid, "KYC verified")
    st.session_state.upload_nonce = st.session_state.get("upload_nonce", 0) + 1  # new widget keys drop the uploaded files from the session
    st.rerun()
res = st.session_state.get("kyc_result")
if res and consent.latest_kyc(c.user()) is None:  # erased when consent was withdrawn: never show it again
    st.session_state.pop("kyc_result"); res = None
if res:
    {"verified": st.success, "needs_review": st.warning, "rejected": st.error}[res["verdict"]](f"**{t['verdicts'][res['verdict']]}**: {res['reason']}")
    for p in res["passed"]: st.markdown(f"✓ {p}")
    if res["fields"]: st.caption(f"{t['stored']}: " + ", ".join(f"{k}: {v}" for k, v in res["fields"].items()))
    st.caption(t["kyc_note"])
last = consent.latest_kyc(c.user())
oid = st.session_state.get("order_id")
if oid and last and last["verdict"] == "verified" and orders.get(oid)["stage"] == "KYC verified":
    if st.button(t["pay"], use_container_width=True):
        orders.advance(oid, "Payment done"); st.session_state.paid_notice = True; st.rerun()  # rerun so the progress bar shows it too
if st.session_state.pop("paid_notice", False): st.success(t["paid"])
c.link("pages/5_Tracker.py", label=t["tracker"], icon="📦")
