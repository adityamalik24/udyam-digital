import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import streamlit as st
from core import consent, orders
from core.catalogue import catalogue
from core.pricing import TODAY
t = c.setup("Tracker")
c.journey("tracker", t)
st.subheader(t["tracker"])
hi = st.session_state.ui_lang == "hi"
W = (lambda en, h: h if hi else en)
day = lambda d: d.strftime("%d %b %Y")
help_link = lambda: c.link("pages/1_Advisor.py", label=W("Talk to a person", "किसी व्यक्ति से बात करें"), icon="🙋")
mine = orders.for_user(c.user())
if not mine:
    st.info(t["no_order"]); c.link("pages/2_Quote.py", label=t["quote"], icon="🧾")
    if consent.records(c.user()):  # withdrawal must not depend on having an order
        with st.expander(t["your_consent"]): c.consent_panel(t)
    st.stop()
oid = st.session_state.get("order_id") if st.session_state.get("order_id") in mine else mine[0]
if len(mine) > 1:  # a paid order must stay reachable after a separate one is started
    oid = st.selectbox(W("Order", "ऑर्डर"), mine, index=mine.index(oid), format_func=lambda n: f"#{n} · ₹{orders.get(n)['monthly']:,}{W('/month', '/माह')} · {dict(zip(orders.STAGES, t['stages'] or orders.STAGES))[orders.get(n)['stage']]}", key="tracker_order")
o = orders.get(oid)
names = dict(zip(orders.STAGES, t["stages"] or orders.STAGES))
st.markdown(f"### {names[o['stage']]}")
st.progress((o["stage_index"] + 1) / len(orders.STAGES))

last = consent.latest_kyc(c.user())
verdict = last["verdict"] if last else None
activated = o["stage_index"] == len(orders.STAGES) - 1
consent_ok = consent.KYC in consent.active(c.user())
step = orders.next_step(o)
if activated:
    st.success(W("Your connection is active.", "आपका कनेक्शन चालू है।"))
elif verdict != "verified":
    # Hold: say why, what to do, and what happened to any payment. Refunds aren't in the rules, so none is promised.
    st.warning(t["hold"])
    if not consent_ok:
        st.markdown(W("KYC consent isn't active, so we can't use your documents.", "KYC सहमति सक्रिय नहीं है, इसलिए हम आपके दस्तावेज़ों का उपयोग नहीं कर सकते।"))
        c.link("pages/3_Consent.py", label=t["consent"], icon="✅")
    else:
        c.link("pages/4_KYC.py", label=t["kyc"], icon="🪪")
    if o["stage_index"] >= 2:
        st.markdown(W("Your payment is recorded. For questions about it, please talk to a person.", "आपका भुगतान दर्ज है। इसके बारे में सवालों के लिए कृपया किसी व्यक्ति से बात करें।"))
else:
    who = W("You", "आप") if step["who"] == "you" else "Accel Business"
    st.markdown(f"**{W('Next', 'अगला चरण')}:** {names[step['stage']]} · {who}")
    if step["estimate"]:
        st.markdown(f"**{W('Estimated installation', 'अनुमानित इंस्टॉलेशन')}:** {day(step['estimate'])}" + W(" (an estimate, not a promise)", " (अनुमान, वादा नहीं)"))
    elif step["stage"] == "Activated":
        st.markdown(W("We'll update this page when activation is done.", "सक्रिय होने पर यह पेज अपडेट हो जाएगा।"))
    if orders.can_pay(o, verdict):
        if st.button(f"{t['pay']} · ₹{orders.first_due(o):,}", type="primary", use_container_width=True):
            orders.advance(oid, "Payment done"); st.session_state.paid_notice = True; st.rerun()
    if o["stage"] == "Quote accepted":
        c.link("pages/4_KYC.py", label=t["kyc"], icon="🪪")
if st.session_state.pop("paid_notice", False): st.success(t["paid"])
if st.session_state.pop("pay_failed", False): st.error(W("The payment didn't go through. Nothing was charged. Please try again.", "भुगतान नहीं हो पाया। कोई पैसा नहीं कटा। कृपया दोबारा कोशिश करें।"))
late = orders.delays(oid)
if late and o["stage_index"] < 5:  # say what happened and the new date, before the owner has to call
    d = late[-1]
    why = {"fibre": W("Fibre can't reach your premises right now.", "अभी आपकी जगह फाइबर नहीं पहुँच पा रहा।"), "partner": W("Our installation partner needs more time.", "हमारे इंस्टॉलेशन पार्टनर को और समय चाहिए।"), "access": W("We couldn't get access to your site.", "हमें आपकी जगह तक पहुँच नहीं मिल पाई।")}[d["reason"]]
    st.warning(W("**Your installation is delayed.** ", "**आपका इंस्टॉलेशन देर से होगा।** ") + why + W(f" New estimate: {day(orders.date.fromisoformat(d['new_date']))}, moved from {day(orders.date.fromisoformat(d['old_date']))}.", f" नया अनुमान: {day(orders.date.fromisoformat(d['new_date']))}, पहले {day(orders.date.fromisoformat(d['old_date']))} था।"))
    if d["reason"] == "fibre" and orders.can_switch_to_airfiber(o):
        air = catalogue()["P04"]
        st.markdown(W(f"{air.name} is wireless and needs no fibre. To ask about switching, please talk to a person.", f"{air.name} वायरलेस है और इसमें फाइबर नहीं चाहिए। बदलने के लिए कृपया किसी व्यक्ति से बात करें।"))
if o.get("technician"): st.markdown(f"**{t['tech']}:** {o['technician']}")

done = {e["stage"]: e["ts"] for e in o["events"]}
for s in orders.STAGES:
    when = orders.shown_time(done[s], o["created"]).strftime("%d %b, %I:%M %p") + " IST" if s in done else ""
    if s == "Installed" and s not in done and o["stage_index"] >= 2: when = W("about ", "लगभग ") + day(max(d for _, d in orders.product_dates(o)))
    st.markdown(f"{'✅' if s in done else '⬜'} {names[s]}" + (f" · {when}" if when else ""))
st.caption(W(f"This demo treats {day(TODAY)} as today.", f"यह डेमो {day(TODAY)} को आज की तारीख मानता है।"))

moved = orders.changes(oid)
for m in moved:
    st.caption(W(f"Installation moved from {day(orders.date.fromisoformat(m['old_date']))} to {day(orders.date.fromisoformat(m['new_date']))}.", f"इंस्टॉलेशन {day(orders.date.fromisoformat(m['old_date']))} से {day(orders.date.fromisoformat(m['new_date']))} पर किया गया।"))
if 3 <= o["stage_index"] < 5 and verdict == "verified":
    with st.expander(t["resched"]):
        low, high = orders.earliest_install(o), TODAY + orders.timedelta(days=orders.MAX_RESCHEDULE_DAYS)
        d = st.date_input(t["new_date"], value=orders.date.fromisoformat(o["install_date"]), min_value=low, max_value=high, key=f"new_date_{oid}")
        st.caption(W(f"You can choose {day(low)} to {day(high)}.", f"आप {day(low)} से {day(high)} के बीच चुन सकते हैं।"))
        if st.button(t["resched_btn"], disabled=d.isoformat() == o["install_date"]):
            orders.reschedule(oid, d); st.rerun()

cat = catalogue()
with st.expander(W("What you ordered", "आपने क्या ऑर्डर किया")):
    for pid, n in json.loads(o["items"]).items():
        due = dict(orders.product_dates(o))[pid]
        st.markdown(f"- {cat[pid].name}" + (f" × {n}" if n > 1 else "") + ("" if o["stage_index"] >= 5 else W(f" · expected about {day(due)}", f" · लगभग {day(due)} तक")))
    st.markdown(f"**₹{o['monthly']:,}** {t['per_month']}  \n{t['setup']}: ₹{o['setup']:,}  \n{t['contract']}: {o['contract']} {t['months']}")
with st.expander(W("Updates sent to you", "आपको भेजे गए अपडेट")):
    if consent.UPDATES in consent.active(c.user()):
        for u in reversed(orders.updates_log(o)):
            when = orders.shown_time(u["ts"], o["created"]).strftime("%d %b, %I:%M %p")
            st.markdown(f"{when} · " + (W(f"Your installation is delayed. New estimate: {day(orders.date.fromisoformat(u['new_date']))}.", f"आपका इंस्टॉलेशन देर से होगा। नया अनुमान: {day(orders.date.fromisoformat(u['new_date']))}।") if u["stage"] == "delay" else W(f"Your order moved on: {names[u['stage']]}.", f"आपका ऑर्डर आगे बढ़ा: {names[u['stage']]}।")))
        st.caption(W("A log for this prototype. No SMS or WhatsApp is sent.", "यह प्रोटोटाइप का लॉग है। कोई SMS या WhatsApp नहीं भेजा जाता।"))
    else:
        st.caption(W("You haven't turned on order updates. You can on the consent page.", "आपने ऑर्डर अपडेट चालू नहीं किए हैं। सहमति पेज पर कर सकते हैं।"))
help_link()
if not activated:
    with st.expander(t["demo"], expanded=st.session_state.get("demo_open", False)):  # stays open between taps
        st.caption(t["demo_note"])
        if orders.can_advance(o, verdict) and st.button(t["advance"]):
            orders.advance(oid); st.session_state.demo_open = True; st.rerun()
        if orders.can_pay(o, verdict) and st.button(W("Simulate a failed payment", "असफल भुगतान का डेमो")):
            st.session_state.pay_failed = True; st.session_state.demo_open = True; st.rerun()
        if verdict == "verified" and 3 <= o["stage_index"] < 5 and not orders.delays(oid) and st.button(W("Simulate a fibre delay", "फाइबर में देरी का डेमो")):
            orders.mark_delay(oid, "fibre"); st.session_state.demo_open = True; st.rerun()
        if not orders.can_advance(o, verdict):
            st.caption(W("Nothing to move right now: this step needs you first.", "अभी आगे बढ़ाने को कुछ नहीं: इस चरण में पहले आपकी ज़रूरत है।"))
with st.expander(t["your_consent"]):
    c.consent_panel(t)
