import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import pandas as pd
import streamlit as st
from core import callback, db
from core.kyc.validators import mask
from core.propensity import score_leads
c.setup("Partner queue")
st.subheader("Partner queue")
st.caption("For specialists and channel partners. Read-only demo view, with no contact details or identifiers shown.")
REASON = {"multi_site": "Several locations", "manufacturer_custom": "Factory with custom needs", "frustration": "Asked for a person", "repeated_confusion": "Repeatedly confused", "tier_not_served": "Town not served yet", "no_eligible": "No eligible plan", "large_account": "Larger than a small business", "customer_request": "Asked for a call"}
st.markdown("**Call-back requests**")
st.caption("Contact details are masked because this demo page has no login. A real team view needs staff sign-in before showing them in full.")
cb = [{"When": r["ts"], "Name": r["name"][:1] + "…" if r["name"] else "", "Phone": mask(r["phone"]), "Email": mask(r["email"]), "Best time": r["best_time"], "Why": REASON.get(r["reason"], r["reason"]), "Business": r["profile"].get("business_type"), "City": r["profile"].get("city"), "Needs": ", ".join(r["profile"].get("needs", []))} for r in callback.queue()]
if cb: st.dataframe(pd.DataFrame(cb), hide_index=True, use_container_width=True)
else: st.info("No call-back requests yet.")
st.markdown("**Advisor hand-offs**")
rows = []
for l in db.list_leads():
    p = json.loads(l["profile"])
    rows.append({"When": l["ts"], "Why": REASON.get(l["reason"], l["reason"]), "Business": p.get("business_type"), "City": p.get("city"), "Staff": p.get("employees"), "Sites": p.get("locations"), "Needs": ", ".join(p.get("needs", []))})
if rows: st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
else: st.info("No hand-offs yet. They appear here when the advisor passes a customer to a person.")
st.markdown("**Dropped leads to call first**")
@st.cache_data(show_spinner="Scoring leads...")
def scored(): return score_leads()
df, auc = scored()
st.caption(f"Leads lost to our process, not refusals. The score only ranks them (cross-validated AUC {auc:.2f}, so a useful guide, not a verdict).")
st.dataframe(df.head(25), hide_index=True, use_container_width=True)
