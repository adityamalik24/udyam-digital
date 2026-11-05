import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import timedelta
import common as c
import streamlit as st
from core import consent, orders
from core.pricing import TODAY
t = c.setup("Tracker")
c.journey("tracker", t)
st.subheader(t["tracker"])
oid = st.session_state.get("order_id") or orders.latest(c.user())
if not oid:
    st.info(t["no_order"])
    if consent.records(c.user()):  # withdrawal must not depend on having an order
        with st.expander(t["your_consent"]): c.consent_panel(t)
    st.stop()
o = orders.get(oid)
names = dict(zip(orders.STAGES, t["stages"] or orders.STAGES))
st.markdown(f"### {names[o['stage']]}")
st.progress((o["stage_index"] + 1) / len(orders.STAGES))
done = {e["stage"]: e["ts"] for e in o["events"]}
for s in orders.STAGES:
    st.markdown(f"{'✅' if s in done else '⬜'} {names[s]}" + (f" · {done[s][:16].replace('T', ' ')} UTC" if s in done else ""))
last = consent.latest_kyc(c.user())
verdict = last["verdict"] if last else None
active = o["stage_index"] < len(orders.STAGES) - 1
if active and not orders.can_advance(o, verdict):
    st.warning(t["hold"])
else:
    nx = orders.next_expected(o)
    if nx: st.markdown(f"**{t['next']}:** {nx}")
if o.get("technician"): st.markdown(f"**{t['tech']}:** {o['technician']}")
if 3 <= o["stage_index"] < 5:
    with st.expander(t["resched"]):
        d = st.date_input(t["new_date"], value=TODAY + timedelta(days=o["install_days"] + 1), min_value=TODAY)
        if st.button(t["resched_btn"]):
            orders.reschedule(oid, d); st.rerun()
with st.expander(t["demo"], expanded=st.session_state.get("demo_open", False)):  # stays open between taps
    st.caption(t["demo_note"])
    if orders.can_advance(o, verdict) and st.button(t["advance"]):
        orders.advance(oid); st.session_state.demo_open = True; st.rerun()
with st.expander(t["your_consent"]):
    c.consent_panel(t)
