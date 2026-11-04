import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from PIL import Image
from core import consent, orders
from core.kyc.pipeline import verify_images, load_specimen
t = c.setup("KYC")
st.subheader(t["kyc"])
if consent.KYC not in consent.active(c.USER):
    st.warning("Please give consent first."); c.link("pages/3_Consent.py", label=t["consent"], icon="✅"); st.stop()
mode = st.radio("Documents", ["Use a specimen applicant (K01 to K12)", "Upload my own"], horizontal=True)
images = {}
if mode.startswith("Use"):
    who = st.selectbox("Applicant", [f"K{i:02d}" for i in range(1, 13)])
    images = load_specimen(who)
else:
    labels = {"gst": "GST certificate", "udyam": "Udyam certificate", "id": "Signatory ID", "bill": "Address proof (under 90 days old)"}
    for k, l in labels.items():
        f = st.file_uploader(l, type=["png", "jpg", "jpeg"], key=f"up_{k}")
        if f: images[k] = Image.open(f).copy()  # held in memory only, never written to disk
if st.button("Verify", type="primary", use_container_width=True, disabled=not images):
    with st.spinner("Reading documents..."):
        r = verify_images(images)
    images.clear()
    consent.save_kyc(c.USER, r.verdict, r.reason, json.dumps(r.fields))
    {"verified": st.success, "needs_review": st.warning, "rejected": st.error}[r.verdict](f"**{r.verdict.replace('_', ' ').title()}**: {r.reason}")
    for p in r.passed: st.markdown(f"✓ {p}")
    if r.fields: st.caption("Stored (masked): " + ", ".join(f"{k}: {v}" for k, v in r.fields.items()))
    st.caption("Documents were read in memory and not stored. Checked as of 15 Jul 2026.")
    oid = st.session_state.get("order_id")
    if r.verdict == "verified" and oid:
        o = orders.get(oid)
        if o["stage"] == "Quote accepted": orders.advance(oid, "KYC verified")
        st.session_state.kyc_ok = True
last = consent.latest_kyc(c.USER)
oid = st.session_state.get("order_id")
if oid and last and last["verdict"] == "verified" and orders.get(oid)["stage"] == "KYC verified":
    if st.button("Pay first month (mock)", use_container_width=True):
        orders.advance(oid, "Payment done"); st.success("Mock payment recorded. No money moved.")
c.link("pages/5_Tracker.py", label=t["tracker"], icon="📦")
