"""Dashboard, data-backed insights, reviewer maker-checker, bill reading, file signals, data rights and the JSON receipt."""
import io, json, os, sys, tempfile, pathlib
ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "features.db")
import pandas as pd
import pytest
from PIL import Image, ImageDraw, ImageFont
from core import billscan, consent, events, insights, orders, reviews, rights
from core.kyc import forensics
from core.pricing import price

LEADS = pd.read_csv(ROOT / "data" / "smb_leads.csv")
ACT = LEADS[LEADS.outcome == "Activated"]


# ---- Insights match the raw data -------------------------------------------------------------------------------------
def test_segment_mapping():
    assert insights.segment_of("kirana") == insights.MICRO_SEG and insights.segment_of("clinic") == insights.PRO_SEG
    assert insights.segment_of("manufacturer") == insights.MFG_SEG and insights.segment_of("clinic", 3) == insights.MULTI_SEG and insights.segment_of(None) is None


def test_activation_days_are_the_middle_half_of_past_activations():
    g = ACT[(ACT.segment == insights.PRO_SEG) & (ACT.city_tier == 1)].days_lead_to_activation
    r = insights.activation_days(insights.PRO_SEG, 1)
    assert (r["low"], r["high"], r["n"]) == (round(g.quantile(.25)), round(g.quantile(.75)), len(g))
    small = insights.activation_days(insights.MFG_SEG, 2)  # too few in that cell: falls back to the whole segment
    assert small["n"] == (ACT.segment == insights.MFG_SEG).sum()


def test_peer_share_counts_products_in_bundles():
    g = ACT[ACT.segment == insights.PRO_SEG]
    want = g.bundle_products.apply(lambda b: any(p.split("x")[0] == "P16" for p in b.split(";"))).mean()
    assert insights.peer_share(insights.PRO_SEG, "P16")["share"] == pytest.approx(want) == 1.0
    assert insights.peer_share(None, "P16") is None


def test_churn_table_matches_the_deck_figures():
    t = insights.churn_table()
    assert round(t["segment"][insights.MICRO_SEG][0], 3) == 0.227 and round(t["base"][0], 3) == 0.152
    assert round(t["calls"]["0-1"][0], 3) == 0.059 and round(t["calls"]["5+"][0], 3) == 0.279


def test_churn_risk_rises_with_chasing_and_explains_itself():
    calm, chased = insights.churn_risk(insights.MICRO_SEG, True, 0), insights.churn_risk(insights.MICRO_SEG, True, 5)
    assert chased["rate"] > calm["rate"] and chased["level"] == "high" and any("chase" in r for r in chased["reasons"])
    assert insights.churn_risk(insights.MFG_SEG, True, 0)["level"] == "low"
    assert any("only 30" in r for r in insights.churn_risk(insights.MICRO_SEG, False, 0)["reasons"])


def test_routing_sends_only_site_surveys_to_the_field():
    assert insights.route(insights.MULTI_SEG, "multi_site")["route"] == "Field visit"
    g = LEADS[(LEADS.segment == insights.MICRO_SEG) & (LEADS.lead_source == "Field sales")]
    per_activation = g.acquisition_cost_inr.mean() / (g.outcome == "Activated").mean()
    r = insights.route(insights.MICRO_SEG)
    assert r["route"] == "Phone and app" and f"₹{per_activation:,.0f}" in r["why"]


def test_payback_starts_from_the_deck_number():
    b = insights.payback_base()[insights.MICRO_SEG]
    assert round(b["spend"]) == 20007 and round(b["value"]) == 2505
    assert round(insights.what_if(insights.MICRO_SEG)["payback_months"]) == 8
    moved = insights.what_if(insights.MICRO_SEG, digital_share=0.5)
    assert moved["spend"] < b["spend"] and moved["payback_months"] < 8
    assert insights.what_if(insights.MICRO_SEG, churn_change=-0.1)["first_year"] > insights.what_if(insights.MICRO_SEG)["first_year"]


def test_lead_reasons_and_openings():
    from core.propensity import score_leads
    df, auc = score_leads()
    assert round(auc, 2) == 0.71 and df.why.str.len().gt(0).all() and df.opening.notna().all()


# ---- Events and the A/B test ---------------------------------------------------------------------------------------------
def test_funnel_counts_each_step_once_per_funnel(monkeypatch, tmp_path):
    from core import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "events.db")  # its own database: other tests log funnel events too
    for f in ("f1", "f2", "f3"):
        events.log(f, "chat_started"); events.log(f, "chat_started")
    events.log("f1", "plan_shown"); events.log("f1", "quote_viewed", variant="A"); events.log("f1", "quote_accepted", variant="A")
    events.log("f2", "quote_viewed", variant="B")
    steps = {s["step"]: s for s in events.funnel()}
    assert steps["Chat started"]["count"] == 3 and steps["Plan shown"]["count"] == 1 and steps["Quote accepted"]["share"] == pytest.approx(1 / 3)
    ab = events.ab_test()
    assert ab["arms"]["A"] == {"viewed": 1, "accepted": 1, "rate": 1.0} and ab["arms"]["B"]["rate"] == 0.0 and not ab["enough"]
    assert 0 <= ab["p"] <= 1
    events.log("f1", "handoff", code="frustration"); events.log("f2", "handoff", code="frustration")
    assert events.counts("handoff") == {"frustration": 2}


# ---- Maker-checker review ------------------------------------------------------------------------------------------------
def _held(user, verdict="needs_review"):
    consent.grant(user, consent.KYC, "en")
    oid = orders.create(user, {"P04": 1}, price({"P04": 1}))
    consent.save_kyc(user, verdict, "Blurry ID", json.dumps({"issues": ["blurry_id"]}))
    from core import db
    with db.conn() as c:
        kid = c.execute("SELECT MAX(id) FROM kyc WHERE user=?", (user,)).fetchone()[0]
    return oid, kid


def test_review_needs_two_different_people_and_then_unlocks_the_order():
    oid, kid = _held("demo-rev1", "rejected")
    assert reviews.propose(kid, "verified", "", "Asha") == "no_note"
    assert reviews.propose(kid, "verified", "ID clear on re-check, Aadhaar 2345 6789 0123", "Asha") is None
    assert reviews.propose(kid, "verified", "again", "Ravi") == "already_proposed"
    rid = reviews.pending()[-1]["id"]
    assert "0123" not in reviews.pending()[-1]["note"]  # notes are redacted
    assert reviews.confirm(rid, "asha", True) == "same_person"
    assert consent.latest_kyc("demo-rev1")["verdict"] == "rejected"  # nothing changes before the second person
    assert reviews.confirm(rid, "Ravi", True) is None
    last = consent.latest_kyc("demo-rev1")
    assert last["verdict"] == "verified" and json.loads(last["fields"])["reviewed"] and orders.get(oid)["stage"] == "KYC verified"
    assert reviews.overturned_rejections() >= 1


def test_review_sent_back_or_stale_changes_nothing():
    oid, kid = _held("demo-rev2")
    reviews.propose(kid, "rejected", "Name doesn't match", "Asha")
    assert reviews.confirm(reviews.pending()[-1]["id"], "Ravi", False) is None
    assert consent.latest_kyc("demo-rev2")["verdict"] == "needs_review"
    reviews.propose(kid, "verified", "Fine", "Asha")
    consent.withdraw("demo-rev2", consent.KYC)
    assert reviews.confirm(reviews.pending()[-1]["id"], "Ravi", True) in ("stale", None)
    assert consent.latest_kyc("demo-rev2") is None and orders.get(oid)["stage"] == "Quote accepted"


def test_a_newer_result_closes_the_old_case():
    _, kid = _held("demo-rev3")
    consent.save_kyc("demo-rev3", "verified", "ok", "{}")
    assert reviews.propose(kid, "verified", "x", "Asha") == "not_waiting"


# ---- Bill reading --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,want", [("Total Amount Due ₹ 1,299.00", 1299), ("Amount payable (INR)\n2,450", 2450), ("Bill date 2026-05-30\nAmount due (INR) 33,615", 33615),
                                       ("Net payable: Rs. 899", 899), ("कुल देय राशि ₹ 1,180", 1180), ("Account no 9876543210\nPlan 999", None), ("Amount due 0", None)])
def test_amount_from_text(text, want):
    assert billscan.amount_from_text(text) == want


def test_reads_the_amount_from_a_bill_photo():
    assert billscan.read_bill(Image.open(ROOT / "data" / "kyc_documents" / "K03_address_proof.png")) == 33615
    img = Image.new("RGB", (1240, 900), "white"); d = ImageDraw.Draw(img); font = ImageFont.load_default(size=34)
    for y, line in [(80, "Telecom Services Ltd - Monthly Bill"), (180, "Account 1234567890"), (260, "Plan charges 999.00"), (340, "GST 179.82"), (420, "Total Amount Due Rs. 1,178.82")]:
        d.text((80, y), line, fill="black", font=font)
    assert billscan.read_bill(img) == 1179
    assert billscan.read_bill(Image.new("RGB", (800, 600), "white")) is None


# ---- File signals --------------------------------------------------------------------------------------------------------
def test_specimens_raise_no_file_signals():
    for p in sorted((ROOT / "data" / "kyc_documents").glob("*.png")):
        assert forensics.signals(p.read_bytes()) == [], p.name


def test_editor_traces_and_resaved_pdfs_are_flagged():
    from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo(); info.add_text("Software", "GIMP 2.10")
    b = io.BytesIO(); Image.new("RGB", (50, 50)).save(b, "PNG", pnginfo=info)
    assert forensics.signals(b.getvalue())[0]["code"] == "editor_software"
    exif = Image.Exif(); exif[0x0131] = "Adobe Photoshop 25.0"
    j = io.BytesIO(); Image.new("RGB", (50, 50)).save(j, "JPEG", exif=exif)
    assert forensics.signals(j.getvalue())[0]["tool"].lower() == "photoshop"
    clean = io.BytesIO(); Image.new("RGB", (50, 50)).save(clean, "JPEG")
    assert forensics.signals(clean.getvalue()) == []
    pdf = io.BytesIO(); Image.new("RGB", (50, 50), "white").save(pdf, "PDF")
    assert forensics.signals(pdf.getvalue()) == []
    resaved = pdf.getvalue() + b"\n1 0 obj\n<< /Producer (iLovePDF) /CreationDate (D:20260501101010) /ModDate (D:20260601101010) >>\nendobj\n%%EOF\n"
    codes = {s["code"] for s in forensics.signals(resaved)}
    assert codes == {"pdf_resaved", "pdf_dates_differ", "editor_software"}
    assert all(forensics.describe(s) for s in forensics.signals(resaved))
    signed = pdf.getvalue() + b"\n2 0 obj\n<< /Type /Sig /ByteRange [0 10 20 30] >>\nendobj\n%%EOF\n"
    assert "pdf_resaved" not in {s["code"] for s in forensics.signals(signed)}


# ---- Data rights and the JSON receipt ---------------------------------------------------------------------------------------
def test_export_correct_and_erase():
    u = "demo-rights"
    consent.grant(u, consent.KYC, "en"); consent.grant(u, consent.UPDATES, "hi")
    unpaid = orders.create(u, {"P04": 1}, price({"P04": 1})); paid = orders.create(u, {"P01": 1}, price({"P01": 1}))
    orders.advance(paid, "KYC verified"); orders.advance(paid, "Payment done")
    consent.save_kyc(u, "verified", "ok", json.dumps({"id_masked": "••••1234"}))
    data = rights.export(u)
    assert len(data["orders"]) == 2 and data["kyc_results"][0]["fields"]["id_masked"] == "••••1234" and "document images" in data["not_held"]
    assert rights.request_correction(u, "  ") == "empty" and rights.request_correction(u, "City should be Pune. PAN ABCDE1234F") is None
    assert "ABCDE1234F" not in rights.requests()[0]["detail"]
    out = rights.erase(u)
    assert out == {"orders_deleted": 1, "orders_kept": 1}
    assert orders.get(unpaid) is None and orders.get(paid) is not None
    assert consent.active(u) == set() and consent.latest_kyc(u) is None and rights.export(u)["rights_requests"] == []
    assert all(r["withdrawn_at"] for r in consent.records(u))  # proof of what was agreed stays


def test_json_receipt_has_the_kantara_fields():
    u = "demo-receipt"
    consent.grant(u, consent.KYC, "en"); consent.grant(u, consent.VOICE, "hi")
    r = consent.receipt_json(u, "en")
    for key in ("version", "jurisdiction", "consentTimestamp", "collectionMethod", "consentReceiptID", "piiPrincipalId", "piiControllers", "policyUrl", "services", "sensitive"):
        assert key in r
    purposes = {p["purposeCode"]: p for p in r["services"][0]["purposes"]}
    assert purposes[consent.KYC]["primaryPurpose"] and purposes[consent.VOICE]["thirdPartyName"] == "Google (Gemini API)"
    assert r["jurisdiction"] == "IN" and json.dumps(r)


def test_watchlist_ranks_paid_orders_by_risk():
    u = "demo-watch"
    calm = orders.create(u, {"P04": 1}, price({"P04": 1})); orders.set_meta(calm, insights.MFG_SEG, True)
    late = orders.create(u, {"P01": 1}, price({"P01": 1})); orders.set_meta(late, insights.MICRO_SEG, False)
    for oid in (calm, late):
        orders.advance(oid, "KYC verified"); orders.advance(oid, "Payment done"); orders.advance(oid)
    orders.mark_delay(late, "fibre")
    mine = [w for w in orders.watchlist() if w["order"] in (calm, late)]
    assert mine[0]["order"] == late and mine[0]["chases"] == 1 and mine[0]["rate"] > mine[1]["rate"]
