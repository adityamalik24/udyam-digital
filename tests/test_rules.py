import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import pytest
from core.catalogue import catalogue
from core.rules import Profile, recommend, eligible, enforce_dependencies, apply_addons, NEEDS

def P(**k):
    d = dict(business_type="kirana", employees=2, locations=1, city="Patna", city_tier=2, has_gstin=False, needs=["internet_for_upi_pos"])
    d.update(k); return Profile(**d)

def test_catalogue_25(): assert len(catalogue()) == 25

def test_kirana_no_gstin_cheapest_and_alternative():
    r = recommend(P())
    assert set(r.items) == {"P04"} and r.alternative == {"P07": 1}

def test_tier3_is_unserviceable():
    r = recommend(P(city_tier=3))
    assert not r.serviceable and not r.items and r.handoff == "tier_not_served"

def test_gstin_products_excluded_with_reason():
    r = recommend(P(needs=["internet_for_upi_pos", "customer_messaging"]))
    assert "P15" not in r.items and ("P15", ("gstin", {})) in r.excluded

def test_clinic_email():
    r = recommend(P(business_type="clinic", employees=6, city_tier=1, has_gstin=True, needs=["cloud_email"]))
    assert r.items == {"P01": 1, "P16": 6, "P20": 6}

def test_one_sim_no_upsell():
    assert recommend(P(needs=["mobile_line"])).items == {"P07": 1}

def test_cctv_adds_link():
    assert {"P23"} < set(recommend(P(needs=["cctv"])).items) and len(recommend(P(needs=["cctv"])).items) == 2

def test_failover_cannot_sit_on_airfiber():
    r = recommend(P(needs=["internet", "failover"]))
    assert "P09" in r.items and "P04" not in r.items and "P01" in r.items

def test_multi_site_qty_and_handoff():
    r = recommend(P(business_type="restaurant", employees=30, locations=4, has_gstin=True, needs=["internet", "sdwan", "cctv"]))
    assert r.items["P02"] == 4 and r.items["P10"] == 4 and r.items["P23"] == 4 and r.handoff == "multi_site"

def test_sdwan_blocked_small():
    r = recommend(P(employees=12, locations=2, has_gstin=True, needs=["sdwan"]))
    assert "P10" not in r.items and any(e[0] == "P10" and e[1][0] == "sites" for e in r.excluded)

def test_textile_leased_iot():
    r = recommend(P(business_type="manufacturer", employees=40, has_gstin=True, needs=["dedicated_bandwidth", "iot"]))
    assert set(r.items) == {"P05", "P24"}

def test_textile_too_small_hands_off():
    r = recommend(P(business_type="manufacturer", employees=5, has_gstin=True, needs=["dedicated_bandwidth", "iot"]))
    assert "P05" not in r.items and "P24" not in r.items and r.handoff

def test_1g_tier2_blocked():
    r = recommend(P(business_type="office", employees=20, has_gstin=True, needs=["high_speed"]))
    assert "P03" not in r.items and any(e[0] == "P03" for e in r.excluded)

def test_addon_dep_and_block():
    base = {"P07": 1}
    o = apply_addons(P(), base, {"P23", "P15"})
    assert "P23" in o["items"] and o["added"] and o["blocked"]["P15"][0] == "gstin"

@pytest.mark.parametrize("pid", list(catalogue()))
def test_every_recommendation_respects_rules(pid):
    for prof in [P(), P(employees=30, locations=4, has_gstin=True, city_tier=1), P(employees=1, has_gstin=True)]:
        items, _ = enforce_dependencies({pid: 1} if eligible(pid, prof)[0] else {}, prof)
        cat = catalogue()
        for k in items:
            assert eligible(k, prof)[0]
            assert not cat[k].requires_one_of or set(cat[k].requires_one_of) & set(items)


def _audit_profiles():
    import itertools
    needs = [[n] for n in NEEDS] + [["internet", n] for n in NEEDS] + [["cctv", "customer_messaging"], ["cloud_email", "security", "failover"], ["dedicated_bandwidth", "iot"]]
    for bt, tier, staff, sites, gst, need in itertools.product(["kirana", "clinic", "restaurant", "manufacturer"], [1, 2], [1, 3, 5, 10, 25, 40], [1, 2, 3, 5], [True, False], needs):
        yield Profile(business_type=bt, city="X", city_tier=tier, employees=staff, locations=sites, has_gstin=gst, needs=need)


def test_every_bundle_obeys_the_catalogue():
    from core.catalogue import catalogue
    from core.pricing import price
    cat = catalogue()
    for prof in _audit_profiles():
        r = recommend(prof)
        for pid in r.items:
            assert eligible(pid, prof)[0], (prof, pid)
            req = cat[pid].requires_one_of
            assert not req or set(req) & set(r.items), (prof, pid)
        if r.items:
            assert r.quote.monthly == sum(cat[p].monthly * q for p, q in r.items.items())
        if r.alternative:
            assert r.alt_quote.monthly < r.quote.monthly, (prof, r.items, r.alternative)
            for pid in r.alternative:
                assert eligible(pid, prof)[0]


def test_every_template_reply_passes_the_guardrail():
    from core.advisor import State, render_rec
    from core.guardrails import check_reply
    for prof in _audit_profiles():
        for lang in ("en", "hi", "hinglish"):
            prof.language = lang
            r = recommend(prof)
            if not r.quote: continue
            s = State(profile=prof, rec=r)
            assert not check_reply(render_rec(s), r.quote, r.alt_quote, {e[0] for e in r.excluded}), (prof, r.items)


def test_fibre_only_addon_replaces_airfiber():
    prof = Profile(business_type="kirana", city_tier=1, employees=3, locations=1, has_gstin=False, needs=["internet"])
    res = apply_addons(prof, {"P04": 1}, {"P09"})
    assert "P04" not in res["items"] and {"P01", "P09"} <= set(res["items"])
    assert apply_addons(prof, {"P04": 1}, {"P23"})["items"].keys() == {"P04", "P23"}


def test_every_business_type_in_the_data_is_recognised():
    import pandas as pd
    from core.advisor import extract_profile
    from core.catalogue import DATA
    d = pd.read_csv(DATA / "smb_leads.csv")[["business_type", "segment"]].drop_duplicates()
    for bt, seg in d.itertuples(index=False):
        got = extract_profile(f"I run a {bt}", Profile()).get("business_type")
        assert got, bt
        assert (got == "manufacturer") == (seg == "Small manufacturers"), (bt, got)


def test_skipped_questions_really_do_not_change_the_plan():
    from core.rules import question_matters, QUESTION_VALUES
    for need in NEEDS:
        base = Profile(business_type="clinic", city="X", city_tier=1, needs=[need])
        for f in QUESTION_VALUES:
            if not question_matters(f, base):
                others = {g: None for g in QUESTION_VALUES if g != f}
                got = {tuple(sorted(recommend(base.model_copy(update={**others, f: v})).items.items())) for v in QUESTION_VALUES[f]}
                assert len(got) == 1, (need, f, got)


def test_questions_asked_for_the_right_needs():
    from core.rules import question_matters as m
    p = lambda *n: Profile(business_type="clinic", city="X", city_tier=1, needs=list(n))
    assert not m("has_gstin", p("internet")) and m("has_gstin", p("customer_messaging"))
    assert not m("employees", p("website")) and not m("locations", p("website"))
    assert m("employees", p("cloud_email")) and m("locations", p("internet"))
