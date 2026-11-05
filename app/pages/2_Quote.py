import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import orders
from core.catalogue import catalogue
from core.pricing import price, first_payment, contract_total, summary_text
from core.rules import apply_addons, eligible, reason_text, ADJUSTABLE_UNITS, MAX_QTY
t = c.setup("Quote")
st.subheader(t["quote"])
s = st.session_state.advisor
if not (s.rec and s.rec.quote):
    st.info(t["no_plan"]); c.link("pages/1_Advisor.py", label=t["advisor"], icon="💬"); st.stop()
cat, rec = catalogue(), s.rec
hi = st.session_state.ui_lang == "hi"
lang = "hi" if hi else "en"
W = (lambda en, h: h if hi else en)
ADDONS = ["P09", "P22", "P23", "P20", "P16", "P17", "P15", "P14", "P19", "P18", "P07", "P11"]
UNIT = {"per camera": W("Cameras", "कैमरे"), "per line": W("Mobile lines", "मोबाइल लाइन"), "per user": W("Users", "यूज़र"), "per device": W("Devices", "डिवाइस"), "per vehicle": W("Vehicles", "गाड़ियाँ"),
        "per counter": W("Billing counters", "बिलिंग काउंटर"), "per channel": W("Phone channels", "फ़ोन चैनल"), "per number": W("Numbers", "नंबर"), "per IP": W("IP addresses", "IP पते"), "per pack": W("Packs", "पैक")}

# The page reads top to bottom as price, then details, then extras, but the price depends on the widgets below it.
price_box, notes_box, alt_box, lines_box = st.container(), st.container(), st.container(), st.container()

# Which plan: the recommended one, or the cheaper option if the owner switched. A new chat plan resets the choice.
plan_id = tuple(sorted(rec.items.items()))
if st.session_state.get("plan_id") != plan_id:
    st.session_state.plan_id, st.session_state.use_alt = plan_id, False
use_alt = bool(st.session_state.use_alt and rec.alternative)
base = rec.alternative if use_alt else rec.items

prof = s.profile
selected = set(st.session_state.get("addons", set()))
new_sel = set()
with st.expander(t["addons"], expanded=False):
    # The chat only asks what its plan depends on, so an add-on can need an answer it never asked for.
    if prof.has_gstin is None and st.checkbox(W("My business has a GSTIN", "मेरे बिज़नेस का GSTIN है"), key="quote_gstin"):
        prof = prof.model_copy(update={"has_gstin": True})
    for pid in [a for a in ADDONS if a not in base]:
        ok, reason = eligible(pid, prof)
        label = f"{cat[pid].name} · ₹{cat[pid].monthly:,}/{cat[pid].unit.replace('per ', '')}"
        if ok:
            if st.checkbox(label, value=pid in selected, key=f"addon_{pid}"): new_sel.add(pid)
        else:
            st.checkbox(f"{label} ({reason_text(reason, lang)})", value=False, disabled=True, key=f"addon_{pid}")
st.session_state.addons = new_sel

qty = {p: st.session_state[f"qty_{p}"] for p in cat if f"qty_{p}" in st.session_state}
res = apply_addons(prof, base, new_sel, qty)
q = price(res["items"])  # always recomputed on the server from product ids, never read from UI state

with price_box:
    st.markdown(f'<div class="big-price">₹{q.monthly:,}</div>{t["per_month"]}', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric(t["setup"], f"₹{q.setup:,}"); m2.metric(t["contract"], f"{q.contract} {t['months']}"); m3.metric(t["valid"], q.valid_until.strftime("%d %b %Y"))
    m4, m5 = st.columns(2)
    m4.metric(W("First payment", "पहला भुगतान"), f"₹{first_payment(q):,}", help=W("First month plus setup, due after KYC.", "पहला महीना और सेटअप, KYC के बाद।"))
    m5.metric(W(f"Total over {q.contract} months", f"{q.contract} महीनों में कुल"), f"₹{contract_total(q):,}")
    st.caption(W(f"Usually installed in about {q.install_days} days. This is an estimate; the real date appears in your tracker.", f"इंस्टॉलेशन में आमतौर पर लगभग {q.install_days} दिन लगते हैं। यह अनुमान है; असली तारीख ट्रैकर में दिखेगी।"))

with notes_box:
    for a, b in res["added"].items():
        st.info(t["needs"].format(a=cat[a].name, b=cat[b].name))
    for gone, link in res["removed"].items():
        st.info(W(f"{cat[link].name} replaces {cat[gone].name}, so you don't pay for two connections.", f"{cat[link].name} ने {cat[gone].name} की जगह ली है, ताकि आपको दो कनेक्शन का भुगतान न करना पड़े।"))
    base_contract = price(base).contract
    if q.contract != base_contract:
        st.info(W(f"These changes make the minimum contract {q.contract} months (it was {base_contract}).", f"इन बदलावों से न्यूनतम अनुबंध {q.contract} महीने हो गया है (पहले {base_contract} था)।"))

with alt_box:
    if rec.alternative:
        if use_alt:
            if st.button(W("Back to the recommended plan", "सुझाए गए प्लान पर वापस जाएँ"), use_container_width=True):
                st.session_state.use_alt = False; st.rerun()
        else:
            alt_q, saving = rec.alt_quote, rec.quote.monthly - rec.alt_quote.monthly
            names = ", ".join(cat[k].name for k in rec.alternative)
            extra = W(" It's mobile data only, with no fixed connection.", " इसमें केवल मोबाइल डेटा है, कोई फिक्स्ड कनेक्शन नहीं।") if rec.alt_kind == "mobile_only" else ""
            st.success(W(f"**Cheaper option:** {names}. Saves ₹{saving:,} a month.{extra}", f"**सस्ता विकल्प:** {names}। हर महीने ₹{saving:,} की बचत।{extra}"))
            if st.button(W("Switch to the cheaper option", "सस्ते विकल्प पर जाएँ"), use_container_width=True):
                st.session_state.use_alt = True; st.rerun()

with lines_box:
    for l in q.lines:
        st.markdown(f"**{l.name}**" + (f" × {l.qty}" if l.qty > 1 else "") + f" · ₹{l.monthly:,}  \n{cat[l.product_id].description}")
        if l.unit in ADJUSTABLE_UNITS:
            st.number_input(UNIT[l.unit], 1, MAX_QTY, l.qty, key=f"qty_{l.product_id}")

with st.expander(W("Compare with your current bill", "अपने मौजूदा बिल से तुलना करें")):
    now = st.number_input(W("What do you pay per month now for phone and internet? (₹)", "अभी फ़ोन और इंटरनेट पर हर महीने कितना देते हैं? (₹)"), 0, 10000000, 0, step=100, key="current_bill")  # never stored
    if now:
        gap = q.monthly - now
        st.write(W(f"This plan is ₹{abs(gap):,} a month {'more' if gap > 0 else 'less'} than what you pay now." if gap else "This plan costs the same as what you pay now.", f"यह प्लान आपके मौजूदा बिल से हर महीने ₹{abs(gap):,} {'ज़्यादा' if gap > 0 else 'कम'} है।" if gap else "यह प्लान आपके मौजूदा बिल के बराबर है।"))
        st.caption(W("Your current services may differ, so compare what's included too.", "आपकी मौजूदा सेवाएँ अलग हो सकती हैं, इसलिए क्या-क्या शामिल है यह भी देखें।"))

st.download_button(W("Download this quote", "यह कोटेशन डाउनलोड करें"), summary_text(q, {p: cat[p].description for p in res["items"]}), "accel_business_quote.txt", "text/plain", use_container_width=True)

already = st.session_state.get("accepted_items") == res["items"]  # a second tap must not create or change an order
if st.button(t["accept"], type="primary", use_container_width=True, disabled=already):
    oid = st.session_state.get("order_id")
    if not (oid and orders.update_quote(oid, res["items"], q)):  # changed the plan before KYC: same order, not a second one
        st.session_state.order_id = orders.create(c.user(), res["items"], q)
    st.session_state.accepted_items = dict(res["items"])
    st.rerun()
if already: st.success(t["accepted"])
if st.session_state.get("order_id"):
    c.link("pages/3_Consent.py", label=t["consent"], icon="✅")
