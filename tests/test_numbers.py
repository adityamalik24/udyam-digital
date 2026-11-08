"""Every figure in the business case, recomputed from smb_leads.csv and found in the deck. If the data or a slide moves, this fails.
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[1]))
All numbers describe synthetic data. Anything modelled is labelled as such on the slide."""
import pathlib
import numpy as np
import pandas as pd
import pytest
from pptx import Presentation

ROOT = pathlib.Path(__file__).parents[1]
D = pd.read_csv(ROOT / "data/smb_leads.csv", dtype={"gstin": str})
A = D[D.outcome == "Activated"]
CAT = pd.read_csv(ROOT / "data/product_catalogue.csv").fillna("").set_index("product_id")
REG = dict(pd.read_csv(ROOT / "data/mock_gstin_registry.csv")[["gstin", "status"]].values)
SEG = {"Professional offices": "Professional offices", "Small multi-site": "Small multi-site businesses", "Small manufacturers": "Small manufacturers", "Micro retail and services": "Micro retail & services"}


def rate(x): return (x.outcome == "Activated").mean() * 100
def churned(x): return x.churned_within_6_months.astype(str).isin(["1", "Y", "True", "1.0"]).mean() * 100
def spend_per_activation(x): return x.acquisition_cost_inr.sum() / (x.outcome == "Activated").sum()


@pytest.fixture(scope="module")
def deck():
    out = []
    for s in Presentation(ROOT / "docs/Udyam_Digital_Business_Case.pptx").slides:
        for sh in s.shapes:
            if sh.has_text_frame: out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out += [c.text for r in sh.table.rows for c in r.cells]
    return " ".join(out)


def test_ten_slides_or_fewer():
    assert len(Presentation(ROOT / "docs/Udyam_Digital_Business_Case.pptx").slides) <= 10


def test_headline_numbers(deck):
    assert f"{rate(D):.1f}%" == "7.4%" and "7.4%" in deck
    assert f"₹{spend_per_activation(D):,.0f}" == "₹15,053" and "₹15,053" in deck
    assert f"{A.days_lead_to_activation.mean():.1f}" == "17.6" and "17.6" in deck
    assert round(A.customer_follow_up_calls.mean()) == 3


def test_funnel_ties_out():
    assert [len(D), D.contacted_date.notna().sum(), D.needs_assessed_date.notna().sum(), D.quote_accepted_date.notna().sum(), D.kyc_complete_date.notna().sum(), len(A)] == [5000, 3406, 1974, 861, 588, 368]


@pytest.mark.parametrize("label,seg", SEG.items())
def test_segment_row(deck, label, seg):
    x, y = D[D.segment == seg], A[A.segment == seg]
    for value in (f"{len(x):,}", f"{rate(x):.1f}%", f"{y.monthly_bundle_value_inr.mean():,.0f}", f"{churned(y):.1f}%", f"₹{spend_per_activation(x):,.0f}", f"{spend_per_activation(x) / y.monthly_bundle_value_inr.mean():.1f} mo"):
        assert value in deck, (label, value)


def test_drop_reasons(deck):
    count = lambda *r: D.drop_reason.isin(r).sum()
    a, b, c = count("Owner had no time for a visit", "Visit not scheduled by sales"), count("Quote too complex to understand", "Quote took too long to arrive"), count("Found paperwork too long", "Document details did not match")
    assert (a, b, c) == (827, 385, 126) and f"{a + b + c:,} drops" in deck
    assert count("Price too high", "Competitor offered cheaper plan") == 621 and "621 of 1,113" in deck and (D.stage_reached == "Needs assessed").sum() == 1113
    assert count("Installation delayed beyond 21 days") == 98 and "98 drops" in deck


def test_value_model(deck):
    needs, quote, kyc = 368 / 1974, 368 / 861, 368 / 588
    add = [round(827 * .5 * needs), round(385 * .5 * quote), round(126 * .5 * kyc)]  # the slide's bars, which add up to its total
    assert add == [77, 82, 39] and 368 + sum(add) == 566 and "368 to 566" in deck
    assert round((368 + sum(add)) / 5000 * 100, 1) == 11.3 and "11.3%" in deck
    assert round(368 + sum(add) * .6) == 487 and round(368 + sum(add) * 1.4) == 645 and "487" in deck and "645" in deck


def test_field_visits_to_micro(deck):
    m = D[(D.segment == "Micro retail & services") & (D.lead_source == "Field sales")]
    assert f"{m.acquisition_cost_inr.sum() / D.acquisition_cost_inr.sum() * 100:.1f}%" == "25.8%" and "25.8%" in deck
    assert f"{(m.outcome == 'Activated').sum() / len(A) * 100:.1f}%" == "7.3%" and "7.3%" in deck
    assert f"₹{spend_per_activation(m):,.0f}" == "₹53,026" and "₹53,026" in deck


def test_rule_breaking_bundles_and_inactive_gstins(deck):
    inactive = A[A.gstin.map(REG).isin(["Cancelled", "Suspended"])]
    assert len(inactive) == 22 and "22 activations" in deck
    def breaks(r):
        items = dict((x.split("x")[0], x) for x in str(r.bundle_products).split(";") if "x" in x)
        for p in items:
            q = CAT.loc[p]
            if str(r.city_tier) not in str(q.available_city_tiers).split(";"): return True
            if q.min_employees != "" and r.employee_count < float(q.min_employees): return True
            if q.min_sites != "" and r.num_sites < float(q.min_sites): return True
            if q.requires_gstin == "Y" and (r.has_gstin != "Y" or REG.get(r.gstin) != "Active"): return True
            if q.requires_one_of and not set(q.requires_one_of.split("|")) & set(items): return True
        return False
    assert sum(breaks(r) for r in A.itertuples()) == 56 and "56 of 368" in deck


def test_signals(deck):
    by = lambda col, v: rate(D[D[col] == v])
    assert f"{by('lead_source', 'Referral'):.1f}%" == "14.8%" and f"{by('lead_source', 'WhatsApp campaign'):.1f}%" == "2.8%" and "14.8%" in deck and "2.8%" in deck
    assert f"{by('has_gstin', 'Y'):.1f}%" == "9.6%" and f"{by('has_gstin', 'N'):.1f}%" == "2.0%"
    micro = D[D.segment == "Micro retail & services"]
    assert f"{rate(micro[micro.has_gstin == 'Y']):.1f}%" == "6.3%" and f"{rate(micro[micro.has_gstin == 'N']):.1f}%" == "1.6%" and "6.3%" in deck and "1.6%" in deck
    assert f"{by('current_provider', 'Accel (mobile only)'):.1f}%" == "9.2%" and "9.2%" in deck
    assert round(by("preferred_language", "Tamil")) == 4 and round(by("preferred_language", "Punjabi")) == 4
    assert f"{churned(A[A.current_internet == 'Mobile hotspot']):.1f}%" == "24.7%" and f"{churned(A[A.current_internet == 'Business broadband']):.1f}%" == "8.3%" and "24.7%" in deck and "8.3%" in deck


def test_status_chases_against_churn_and_nps(deck):
    by = A.groupby("customer_follow_up_calls")
    assert [round(churned(by.get_group(n)), 1) for n in (1, 2, 3, 4, 5)] == [5.9, 14.3, 11.7, 20.0, 27.9]
    assert round(by.get_group(1).nps_score.mean(), 1) == 7.5 and round(by.get_group(5).nps_score.mean(), 1) == 6.0 and "7.5 to 6.0" in deck


def test_price_position():
    import re
    pos = []
    for r in A.itertuples():
        items = [(m[0], int(m[1])) for m in re.findall(r"(P\d\d)x(\d+)", str(r.bundle_products))]
        lo, hi = sum(CAT.loc[p].price_min_inr_per_month * n for p, n in items), sum(CAT.loc[p].price_max_inr_per_month * n for p, n in items)
        if hi > lo: pos.append((r.monthly_bundle_value_inr - lo) / (hi - lo))
    assert round(float(np.mean(pos)), 2) == 0.48


def test_top_tenth_lift(deck):
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from core.propensity import CAT as C, NUM as N
    X = D[C + N].copy(); X[C] = X[C].astype(str); X[N] = X[N].fillna(X[N].median()); y = (D.outcome == "Activated").astype(int)
    p = cross_val_predict(make_pipeline(ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), C), ("n", StandardScaler(), N)]), LogisticRegression(max_iter=2000, class_weight="balanced")), X, y, cv=5, method="predict_proba")[:, 1]
    assert round(y.iloc[np.argsort(-p)[:500]].mean() / y.mean(), 1) == 2.2 and "2.2 times" in deck


def test_bundle_examples_come_from_the_pricing_engine(deck):
    from core.pricing import price
    for items in ({"P04": 1}, {"P01": 1, "P16": 6, "P20": 6}, {"P02": 4, "P09": 4, "P23": 4, "P10": 4}, {"P05": 1, "P24": 2}):
        assert f"₹{price(items).monthly:,}" in deck


def test_no_gstin_and_cost_target(deck):
    no = D.has_gstin.astype(str).str.upper() == "N"
    micro = D.segment == "Micro retail & services"
    assert no.sum() == 1466 and round(no.mean() * 100) == 29 and round(no[micro].mean() * 100) == 47
    assert "1,466 leads (29%, and 47% of micro) have no GSTIN" in deck
    # The bundles called GSTIN-free really are: nothing in them needs a GSTIN.
    for items in (["P04"], ["P01", "P16", "P20"]):
        assert not any(CAT.loc[p, "requires_gstin"] == "Y" for p in items)
    # Slide 8's cost per activation at today's spend, which slide 9's ₹10,000 target rests on.
    assert f"₹{D.acquisition_cost_inr.sum() / 566:,.0f}" == "₹9,787" and "₹9,787" in deck and "₹10,000" in deck


def _deck_content(path):
    texts, nums, links = [], set(), set()
    for s in Presentation(path).slides:
        for sh in s.shapes:
            if sh.has_text_frame:
                texts.append(sh.text_frame.text)
                links |= {r.hyperlink.address for p in sh.text_frame.paragraphs for r in p.runs if r.hyperlink.address}
            if getattr(sh, "has_table", False) and sh.has_table: texts += [c.text for r in sh.table.rows for c in r.cells]
            if getattr(sh, "has_chart", False) and sh.has_chart: nums |= {f"{v:g}" for v in sh.chart.plots[0].series[0].values}
    t = " ".join(texts)
    return t, nums | set(__import__("re").findall(r"₹?\d[\d,]*(?:\.\d+)?%?", t)), links


def test_seven_slide_deck_keeps_everything():
    """The 7-slide version must carry every number, link and slide message of the 10-slide deck."""
    short = ROOT / "docs/Udyam_Digital_Business_Case_7_slides.pptx"
    full_t, full_n, full_l = _deck_content(ROOT / "docs/Udyam_Digital_Business_Case.pptx")
    t, n, l = _deck_content(short)
    assert len(Presentation(short).slides) == 7
    assert not (full_n - n), sorted(full_n - n)
    assert full_l <= l
    titles = [s.shapes.title.text_frame.text for s in list(Presentation(ROOT / "docs/Udyam_Digital_Business_Case.pptx").slides)[1:]]
    assert all(x.lower() in t.lower() for x in titles), [x for x in titles if x.lower() not in t.lower()]
