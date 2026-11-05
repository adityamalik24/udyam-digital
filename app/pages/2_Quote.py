import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import orders
from core.catalogue import catalogue
from core.pricing import price
from core.rules import apply_addons, eligible, reason_text
t = c.setup("Quote")
st.subheader(t["quote"])
s = st.session_state.advisor
if not (s.rec and s.rec.quote):
    st.info(t["no_plan"]); c.link("pages/1_Advisor.py", label=t["advisor"], icon="💬"); st.stop()
cat, base = catalogue(), s.rec.items
lang = "hi" if st.session_state.ui_lang == "hi" else "en"
ADDONS = ["P09", "P22", "P23", "P20", "P16", "P17", "P15", "P14", "P19", "P18", "P07", "P11"]
selected = set(st.session_state.get("addons", set()))
new_sel = set()
with st.expander(t["addons"], expanded=False):
    for pid in [a for a in ADDONS if a not in base]:
        ok, reason = eligible(pid, s.profile)
        label = f"{cat[pid].name} · ₹{cat[pid].monthly:,}/{cat[pid].unit.replace('per ', '')}"
        if ok:
            if st.checkbox(label, value=pid in selected, key=f"addon_{pid}"): new_sel.add(pid)
        else:
            st.checkbox(f"{label} ({reason_text(reason, lang)})", value=False, disabled=True, key=f"addon_{pid}")
st.session_state.addons = new_sel
res = apply_addons(s.profile, base, new_sel)
q = price(res["items"])  # always recomputed on the server from product ids, never read from UI state
st.markdown(f'<div class="big-price">₹{q.monthly:,}</div>{t["per_month"]}', unsafe_allow_html=True)
for a, b in res["added"].items():
    st.info(t["needs"].format(a=cat[a].name, b=cat[b].name))
c1, c2, c3 = st.columns(3)
c1.metric(t["setup"], f"₹{q.setup:,}"); c2.metric(t["contract"], f"{q.contract} {t['months']}"); c3.metric(t["valid"], q.valid_until.strftime("%d %b %Y"))
for l in q.lines:
    st.markdown(f"**{l.name}**" + (f" × {l.qty}" if l.qty > 1 else "") + f" · ₹{l.monthly:,}  \n{cat[l.product_id].description}")
already = st.session_state.get("accepted_items") == res["items"]  # a second tap must not create a second order
if st.button(t["accept"], type="primary", use_container_width=True, disabled=already):
    st.session_state.order_id = orders.create(c.user(), res["items"], q)
    st.session_state.accepted_items = dict(res["items"])
    already = True
if already: st.success(t["accepted"])
if st.session_state.get("order_id"):
    c.link("pages/3_Consent.py", label=t["consent"], icon="✅")
