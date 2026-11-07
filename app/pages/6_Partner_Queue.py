import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common as c
import pandas as pd
import streamlit as st
from core import callback, consent, db, events, insights, llm, orders, reviews, rights
from core.catalogue import catalogue
from core.kyc import forensics, messages as KM
from core.kyc.pipeline import SPECIMEN_REVIEW, verify_specimen
from core.kyc.validators import mask
from core.propensity import score_leads
c.setup("Partner queue")
st.subheader("Partner queue")
st.caption("For specialists and channel partners. A demo view with no login, so contact details and identifiers are masked.")
REASON = {"multi_site": "Several locations", "manufacturer_custom": "Factory with custom needs", "needs_scoping": "Wants a line they aren't eligible for", "frustration": "Asked for a person", "repeated_confusion": "Repeatedly confused", "tier_not_served": "Town not served yet", "no_eligible": "No eligible plan", "large_account": "Larger than a small business", "customer_request": "Asked for a call"}
table = lambda rows, empty: st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True) if rows else st.info(empty)
dash, review, leads_tab, money, logs = st.tabs(["Live dashboard", "KYC review", "Leads and routing", "Payback what-if", "Logs"])

# ---- Live dashboard: the deck's metrics, measured from this app ---------------------------------------------------------
with dash:
    st.caption("Counted from this server's own events since its database was created. Each event is a random funnel id and a step, never a person.")
    steps = events.funnel()
    st.markdown("**Funnel**")
    st.dataframe(pd.DataFrame([{"Step": s["step"], "Reached": s["count"], "Of chats started": f"{s['share']:.0%}" if s["share"] is not None else "–", "Median minutes from previous step": s["minutes"] if s["minutes"] is not None else "–"} for s in steps]), hide_index=True, use_container_width=True)
    started, done = steps[0]["count"], steps[-1]["count"]
    with db.conn() as conn:
        all_orders = [orders.get(r[0]) | {"user": r[1]} for r in conn.execute("SELECT id,user FROM orders")]
    cat = catalogue()
    broken = sum(any(cat[p].requires_one_of and not set(cat[p].requires_one_of) & set(json.loads(o["items"])) for p in json.loads(o["items"])) for o in all_orders)
    paid_orders = [o for o in all_orders if o["stage_index"] >= 2]
    unverified_paid = sum((consent.latest_kyc(o["user"]) or {}).get("verdict") != "verified" and o["stage_index"] >= 3 for o in paid_orders)
    watch = orders.watchlist()
    st.markdown("**Against the deck's targets**")
    st.dataframe(pd.DataFrame([
        {"Metric": "Lead to activation", "Data baseline": "7.4%", "Target": "11%", "This app": f"{done / started:.0%} ({done} of {started})" if started else "no chats yet"},
        {"Metric": "Status chases per paid order", "Data baseline": "3.0", "Target": "1 or fewer", "This app": f"{sum(w['chases'] for w in watch) / len(watch):.1f} (delays, reschedules, call-backs)" if watch else "no paid orders yet"},
        {"Metric": "Days to activate", "Data baseline": "17.6", "Target": "10", "This app": "n/a: demo controls skip ahead"},
        {"Metric": "Rule-breaking bundles (keep at 0)", "Data baseline": "56", "Target": "0", "This app": f"{broken} of {len(all_orders)} orders (product dependencies)"},
        {"Metric": "Installs on unverified KYC (keep at 0)", "Data baseline": "22 on inactive GSTINs", "Target": "0", "This app": str(unverified_paid)},
        {"Metric": "False KYC rejections (keep at 0)", "Data baseline": "not measured", "Target": "0", "This app": f"{reviews.overturned_rejections()} reversed by a person"},
    ]), hide_index=True, use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.markdown("**AI replies since the server started**")
        total = sum(llm.stats.values())
        if total:
            st.dataframe(pd.DataFrame([{"How the reply was made": {"worded": "Worded by Gemini, checked", "template": "Standard text (AI off, busy or refused)", "refused": "Gemini attempt refused by the guard"}.get(k, k), "Count": v} for k, v in llm.stats.items()]), hide_index=True, use_container_width=True)
        else: st.info("No AI replies yet.")
        if llm.last_error: st.caption(f"Last AI problem: {llm.last_error}")
    with right:
        st.markdown("**Hand-offs by reason**")
        h = events.counts("handoff")
        table([{"Reason": REASON.get(k, k), "Count": v} for k, v in sorted(h.items(), key=lambda x: -x[1])], "No hand-offs yet.")
    st.markdown("**A/B test: does \"about ₹N a day\" under the price help owners accept?**")
    ab = events.ab_test()
    st.dataframe(pd.DataFrame([{"Variant": {"A": "A: monthly price only", "B": "B: plus the daily figure"}[v], "Saw a quote": a["viewed"], "Accepted": a["accepted"], "Rate": f"{a['rate']:.0%}" if a["rate"] is not None else "–"} for v, a in ab["arms"].items()]), hide_index=True, use_container_width=True)
    st.caption((f"Two-proportion test p = {ab['p']:.2f}. " if ab["p"] is not None else "") + ("Enough data to read." if ab["enough"] else "Too few visitors to call a winner: we'd wait for about 100 per variant before deciding."))

# ---- KYC review: maker-checker ------------------------------------------------------------------------------------------
with review:
    st.caption("Anything the automatic check couldn't verify. One person proposes a decision and a different person confirms it; only then does the owner's result change. File signals are for reviewers only and never change a verdict.")
    queue = consent.kyc_queue()
    with db.conn() as conn:
        ids = {r["user"]: r["id"] for r in conn.execute("SELECT user, MAX(id) AS id FROM kyc GROUP BY user")}
    open_reviews = {r["kyc_id"] for r in reviews.pending()}
    rows = []
    for r in queue:
        f = json.loads(r["fields"] or "{}")
        docs = list(dict.fromkeys(KM.DOC_NAME[KM.issue_doc(x)]["en"] for x in f.get("issues", []) if x in KM.ISSUE))
        rows.append({"Case": ids[r["user"]], "When": r["ts"], "Ref": "…" + r["user"][-4:], "Result": {"needs_review": "Needs review", "rejected": "Rejected"}.get(r["verdict"], r["verdict"]), "Check": ", ".join(docs), "Why": r["reason"],
                     "File signals": "; ".join(forensics.describe(s) for s in f.get("signals", [])) or "none", "Status": "Waiting for second person" if ids[r["user"]] in open_reviews else "Open"})
    table(rows, "Nothing waiting. Results that aren't verified appear here.")
    can_propose = [r["Case"] for r in rows if r["Status"] == "Open"]
    if can_propose:
        with st.form("propose", clear_on_submit=True):
            st.markdown("**Propose a decision**")
            case = st.selectbox("Case", can_propose)
            decision = st.radio("Decision", list(reviews.DECISIONS), format_func=reviews.DECISIONS.get, horizontal=True)
            note = st.text_area("What you checked (shown to the owner; ID numbers are removed)", max_chars=300)
            maker = st.text_input("Your name")
            if st.form_submit_button("Propose", use_container_width=True):
                problem = reviews.propose(case, decision, note, maker)
                (st.error(reviews.PROBLEM[problem]) if problem else st.rerun())
    waiting = reviews.pending()
    if waiting:
        st.markdown("**Waiting for a second person**")
        for w in waiting:
            with st.container(border=True):
                st.markdown(f"Case {w['kyc_id']} · {w['was']} → **{reviews.DECISIONS[w['decision']]}** · proposed by {w['maker']}  \n{w['note']}")
                checker = st.text_input("Your name (must differ)", key=f"chk_{w['id']}")
                a, b = st.columns(2)
                for col, accept, label in ((a, True, "Confirm"), (b, False, "Send back")):
                    if col.button(label, key=f"{label}_{w['id']}", use_container_width=True):
                        problem = reviews.confirm(w["id"], checker, accept)
                        (st.error(reviews.PROBLEM[problem]) if problem else st.rerun())
    st.markdown("**Data rights requests**")
    table([{"When": r["ts"], "Ref": "…" + r["user"][-4:], "Kind": r["kind"], "Detail": r["detail"], "Reply by": r["due"], "Status": r["status"]} for r in rights.requests()], "No requests.")
    with st.expander("KYC self-check on the 12 specimen applicants"):
        st.caption("Runs the live KYC code on this server and compares it with our own manual review of the images (not the judges' key). Nothing is stored.")
        if st.button("Run the self-check", use_container_width=True):
            bar, out = st.progress(0.0), []
            for n, (k, (want, code)) in enumerate(SPECIMEN_REVIEW.items()):
                bar.progress(n / len(SPECIMEN_REVIEW), f"Checking {k}...")
                res = verify_specimen(k); codes = [x.code for x in res.issues]
                out.append({"Applicant": k, "Same as review": "✓" if res.verdict == want and (code is None or code in codes) else "✗", "Result": res.verdict, "Expected": want, "Why": res.reason})
            bar.empty(); st.session_state.selfcheck = out
        if st.session_state.get("selfcheck"):
            done_rows = st.session_state.selfcheck
            same = sum(x["Same as review"] == "✓" for x in done_rows)
            (st.success if same == len(done_rows) else st.error)(f"{same} of {len(done_rows)} match our review.")
            st.dataframe(pd.DataFrame(done_rows), hide_index=True, use_container_width=True)

# ---- Leads and routing ----------------------------------------------------------------------------------------------------
with leads_tab:
    st.markdown("**Call-back requests**")
    st.caption("Contact details are masked because this demo page has no login. A real team view needs staff sign-in before showing them in full.")
    rows = []
    for r in callback.queue():
        seg = insights.segment_of(r["profile"].get("business_type"), r["profile"].get("locations"))
        rows.append({"When": r["ts"], "Name": r["name"][:1] + "…" if r["name"] else "", "Phone": mask(r["phone"]), "Email": mask(r["email"]), "Best time": r["best_time"], "Why": REASON.get(r["reason"], r["reason"]),
                     "Business": r["profile"].get("business_type"), "City": r["profile"].get("city"), "Send": insights.route(seg, r["reason"])["route"]})
    table(rows, "No call-back requests yet.")
    st.markdown("**Advisor hand-offs**")
    st.caption("Field visits only where a site survey is needed: elsewhere the data shows they cost several times as much per activation as a phone-led sale.")
    rows = []
    for l in db.list_leads():
        p = json.loads(l["profile"]); seg = insights.segment_of(p.get("business_type"), p.get("locations")); r = insights.route(seg, l["reason"])
        rows.append({"When": l["ts"], "Why": REASON.get(l["reason"], l["reason"]), "Business": p.get("business_type"), "City": p.get("city"), "Staff": p.get("employees"), "Sites": p.get("locations"), "Needs": ", ".join(p.get("needs", [])), "Send": r["route"], "Because": r["why"]})
    table(rows, "No hand-offs yet. They appear here when the advisor passes a customer to a person.")
    st.markdown("**Orders to check in on**")
    st.caption("Paid orders ranked by churn risk. In the data, owners who had to chase us churned far more (5.9% at 0–1 follow-up calls, 27.9% at 5 or more), so each delay, reschedule or call-back raises the risk. A rough guide for a proactive call, not a verdict.")
    table([{"Order": w["order"], "Stage": w["stage"], "Segment": w["segment"], "Times chased": w["chases"], "Risk": f"{w['level']} ({w['rate']:.0%})", "Because": " · ".join(w["reasons"])} for w in watch], "No paid orders yet.")
    st.markdown("**Dropped leads to call first**")
    @st.cache_data(show_spinner="Scoring leads...")
    def scored(): return score_leads()
    df, auc = scored()
    st.caption(f"Leads lost to our process, not refusals. The score only ranks them (cross-validated AUC {auc:.2f}, so a useful guide, not a verdict). \"Why\" names what lifts each score most; \"Say first\" answers why they dropped.")
    show = df.head(25).copy()
    show["send"] = [insights.route(s)["route"] for s in show["segment"]]
    st.dataframe(show.rename(columns={"business_name": "Business", "segment": "Segment", "city": "City", "preferred_language": "Language", "lead_source": "Source", "drop_reason": "Why it dropped", "score": "Score", "why": "Why this score", "opening": "Say first", "send": "Send"}), hide_index=True, use_container_width=True)

# ---- Payback what-if ------------------------------------------------------------------------------------------------------
with money:
    base = insights.payback_base()
    seg = st.selectbox("Segment", list(base), index=list(base).index(insights.MICRO_SEG))
    a, b, cc = st.columns(3)
    share = a.slider("Sales moved to phone and app", 0, 100, 0, 10, format="%d%%") / 100
    price_move = b.slider("Price change", -20, 20, 0, 5, format="%d%%") / 100
    churn_move = cc.slider("Churn change (points)", -15, 10, 0, 1, format="%d") / 100
    now, then = insights.what_if(seg), insights.what_if(seg, share, price_move, churn_move)
    m1, m2, m3 = st.columns(3)
    moved = (share, price_move, churn_move) != (0, 0, 0)  # no arrows until something changes
    m1.metric("Spend per activation", f"₹{then['spend']:,.0f}", f"{then['spend'] - now['spend']:+,.0f}" if moved else None, delta_color="inverse")
    m2.metric("Months to pay back", f"{then['payback_months']:.1f}", f"{then['payback_months'] - now['payback_months']:+.1f}" if moved else None, delta_color="inverse")
    m3.metric("First-year revenue per ₹1 spent", f"₹{then['return']:.2f}", f"{then['return'] - now['return']:+.2f}" if moved else None)
    st.caption(f"Starts from the data for {base[seg]['n']} activated {seg.lower()} customers: ₹{base[seg]['spend']:,.0f} spent per activation (all channels), ₹{base[seg]['value']:,.0f} a month, {base[seg]['churn']:.0%} churn in 6 months. "
               f"Phone-led sales cost ₹{base[seg]['remote']:,.0f} per activation. Assumptions: demand doesn't change with price, and a customer who leaves in the first 6 months leaves at month 3. Revenue, not margin.")

# ---- Logs ---------------------------------------------------------------------------------------------------------------
with logs:
    st.caption("Every consent, withdrawal, KYC result, review and deletion: a session reference and a code, with no names, numbers or document details.")
    log = db.audit_log()
    table([{"When": r["ts"], "Ref": "…" + r["actor"][-4:], "Action": r["action"], "Detail": r["detail"]} for r in log], "Nothing logged yet.")
