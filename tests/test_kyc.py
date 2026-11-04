import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import pytest
from core.kyc import registry
from core.kyc.pipeline import verify_specimen
from core.kyc.validators import gstin_problem, gstin_checksum, valid_udyam, mask

# Expected from our own manual review of the images against the registries, NOT the judges' key.
EXPECTED = {"K01": ("rejected", "gst_inactive"), "K02": ("verified", None), "K03": ("verified", None),
            "K04": ("needs_review", "blurry_gst"), "K05": ("needs_review", "missing_udyam"),
            "K06": ("rejected", "gst_number_mismatch"), "K07": ("needs_review", "legal_name_mismatch"),
            "K08": ("verified", None), "K09": ("verified", None), "K10": ("needs_review", "signatory_vs_lead"),
            "K11": ("needs_review", "bill_stale"), "K12": ("verified", None)}

@pytest.fixture(scope="module")
def results():
    out = {k: verify_specimen(k) for k in EXPECTED}
    print(f"\n{'app':4} {'expected':13} {'got':13} reason")
    for k, r in out.items():
        print(f"{k:4} {EXPECTED[k][0]:13} {r.verdict:13} {r.reason[:110]}")
    return out

@pytest.mark.parametrize("k", list(EXPECTED))
def test_applicant(results, k):
    want, code = EXPECTED[k]
    r = results[k]
    assert r.verdict == want, r.reason
    if code: assert code in {i.code for i in r.issues}

def test_checksum_all_registry():
    assert all(gstin_problem(g) is None for g in registry.all_gstins())

def test_checksum_detects_change():
    assert gstin_problem("08YKZXS8189L1ZO") == "fails the GSTIN checksum"
    assert gstin_checksum("08YKZXS5189L1Z") == "O"

def test_formats():
    assert all(valid_udyam(u) for u in registry.all_udyam())
    assert not valid_udyam("UDYAM-MH-00-123") and gstin_problem("ABC")

def test_mask(): assert mask("SYN-ID-346190") == "•" * 9 + "6190"
