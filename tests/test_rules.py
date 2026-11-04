import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import pytest
from core.catalogue import catalogue
from core.rules import Profile, recommend, eligible, enforce_dependencies, apply_addons

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
