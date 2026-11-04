import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date, timedelta
import common as c
import streamlit as st
from core import consent, orders
from core.pricing import TODAY
t = c.setup("Tracker")
st.subheader(t["tracker"])
oid = st.session_state.get("order_id") or orders.latest(c.USER)
if not oid:
    st.info(t["no_order"]); st.stop()
o = orders.get(oid)
st.markdown(f"### {o['stage']}")
st.progress((o["stage_index"] + 1) / len(orders.STAGES))
done = {e["stage"]: e["ts"] for e in o["events"]}
for i, s in enumerate(orders.STAGES):
    st.markdown(f"{'✅' if s in done else '⬜'} {s}" + (f" · {done[s][:16].replace('T', ' ')} UTC" if s in done else ""))
nx = orders.next_expected(o)
if nx: st.markdown(f"**Next expected (estimate):** {nx}")
if o.get("technician"): st.markdown(f"**Technician:** {o['technician']}")
if 3 <= o["stage_index"] < 5:
    with st.expander("Reschedule installation"):
        d = st.date_input("New date", value=TODAY + timedelta(days=o["install_days"] + 1), min_value=TODAY)
        if st.button("Reschedule"):
            orders.reschedule(oid, d); st.rerun()
with st.expander("Demo control"):
    st.caption("Moves the order one stage forward, for demo only.")
    if o["stage_index"] < len(orders.STAGES) - 1 and st.button("Advance stage"):
        orders.advance(oid); st.rerun()
with st.expander("Your consent"):
    for r in consent.records(c.USER):
        st.caption(f"{r['purpose']} · {r['notice_version']} · granted {r['granted_at']}" + (f" · withdrawn {r['withdrawn_at']}" if r["withdrawn_at"] else ""))
    for p in consent.active(c.USER):
        if st.button(f"Withdraw: {p}", key=f"w_{p}"):
            consent.withdraw(c.USER, p); st.rerun()
