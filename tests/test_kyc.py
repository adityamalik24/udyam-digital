import io, json, re, sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import pytest
from core.kyc import registry
from core.kyc.pipeline import verify_specimen, SPECIMEN_REVIEW as EXPECTED
from core.kyc.validators import gstin_problem, gstin_checksum, valid_udyam, mask

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


# --- What the mutation and stress runs taught us: each of these once went wrong. ---
from PIL import Image
from core.kyc.checks import check_applicant, gstin_reading, names_match, _addr_ok
from core.kyc.ocr import Extracted, prepare, clean_up, sharpness, extract
from core.kyc.pipeline import load_specimen, open_upload, verify_images, FILES
from core.kyc import messages as M

K03_GSTIN = "27XUIXG0767D1ZP"

def _clean_docs():
    """K03 as OCR reads it, so a check can be tried one changed field at a time without OCR."""
    d = lambda doc, **f: Extracted(doc=doc, fields=f, sharpness=500.0, reliable=True)
    return {"gst": d("gst", gstin=K03_GSTIN, gstin_reads=",".join([K03_GSTIN] * 5), legal_name="Joseph Singh (Prop. Ganesh Woodcraft)", trade_name="Ganesh Woodcraft", constitution="Proprietorship",
                     address="Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231", liability_date="2020-02-10"),
            "udyam": d("udyam", udyam="UDYAM-MH-00-9516696", name="Ganesh Woodcraft", activity="Manufacturing", city="Nagpur", state="Maharashtra", reg_date="2024-11-21"),
            "id": d("id", name="Joseph Singh", designation="Owner", business="Ganesh Woodcraft", id_no="SYN-ID-447889", valid_till="2028-07-04"),
            "bill": d("bill", consumer="3438517928", billed_to="Ganesh Woodcraft", address="Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231", date="2026-05-30")}

def _with(doc, **change):
    docs = _clean_docs(); docs[doc].fields.update(change); return check_applicant(docs)

def _codes(r): return {i.code for i in r.issues}

def test_the_clean_baseline_verifies(): assert check_applicant(_clean_docs()).verdict == "verified"

@pytest.mark.parametrize("doc,change,code", [
    ("gst", {"gstin": "", "gstin_reads": ""}, "gstin_unread"),
    ("gst", {"trade_name": "Ganesh Woodcraft Works"}, "trade_name_mismatch"),
    ("gst", {"address": "Shop/Unit 81, Civil Lines, Nagpur, Maharashtra - 411231"}, "gst_address_mismatch"),
    ("gst", {"address": "Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411232"}, "gst_address_mismatch"),
    ("gst", {"constitution": "Partnership"}, "constitution_mismatch"),
    ("gst", {"liability_date": "2021-02-10"}, "liability_date_mismatch"),
    ("gst", {"legal_name": "Joseph Singh (Prop. Ganesh Woodcrxyz)"}, "legal_name_mismatch"),
    ("udyam", {"city": "Pune"}, "udyam_place_mismatch"),
    ("udyam", {"state": "Gujarat"}, "udyam_place_mismatch"),
    ("udyam", {"udyam": ""}, "udyam_blank"),
    ("udyam", {"udyam": "UDYAM-MH-00-1234567"}, "udyam_not_found"),
    ("bill", {"date": "2026-07-16"}, "bill_future"),
    ("bill", {"date": "2026-04-15"}, "bill_stale"),
    ("bill", {"date": "soon"}, "bill_date"),
    ("bill", {"billed_to": "Someone Else"}, "bill_name"),
    ("bill", {"address": "Shop/Unit 8, Civil Lines, Nagpur, Maharashtra - 411231"}, "address_mismatch"),
    ("id", {"id_no": ""}, "id_number_blank"),
    ("id", {"valid_till": "2026-07-14"}, "id_expired"),
    ("id", {"valid_till": "unknown"}, "id_date"),
    ("id", {"business": "Other Traders"}, "id_business"),
    ("id", {"name": "Joseph Sinha"}, "signatory_mismatch"),
])
def test_each_changed_field_goes_to_a_person_and_never_verifies(doc, change, code):
    r = _with(doc, **change)
    assert r.verdict == "needs_review" and code in _codes(r)

def test_date_boundaries():
    assert _with("bill", date="2026-04-16").verdict == "verified"  # exactly 90 days is still accepted
    assert _with("bill", date="2026-07-15").verdict == "verified"
    assert _with("id", valid_till="2026-07-15").verdict == "verified"  # valid through today

def test_fields_the_generator_scrambles_are_never_held_against_anyone():
    assert _with("udyam", activity="Trading", reg_date="1999-01-01").verdict == "verified"  # data/README.md

def test_suspended_gstin_is_rejected():
    rec = next(g for g in registry._gst().values() if g["status"] == "Suspended")
    docs = _clean_docs()
    docs["gst"].fields.update(gstin=rec["gstin"], gstin_reads=",".join([rec["gstin"]] * 5), legal_name=rec["legal_name"], trade_name=rec["trade_name"], constitution=rec["constitution"], address=rec["principal_place_of_business"], liability_date=rec["registration_date"])
    r = check_applicant(docs)
    assert r.verdict == "rejected" and "suspended" in r.reason and "निलंबित" in r.reason_in("hi")

def test_company_with_no_named_person_on_record_goes_to_a_person(monkeypatch):
    rec = next(g for g in registry._gst().values() if "(Prop" not in g["legal_name"] and g["status"] == "Active")
    monkeypatch.setattr(registry, "lead_contact", lambda g: None)
    docs = _clean_docs()
    docs["gst"].fields.update(gstin=rec["gstin"], gstin_reads=",".join([rec["gstin"]] * 5), legal_name=rec["legal_name"], trade_name=rec["trade_name"], constitution=rec["constitution"], address=rec["principal_place_of_business"], liability_date=rec["registration_date"])
    docs["id"].fields.update(business=rec["trade_name"]); docs["bill"].fields.update(billed_to=rec["trade_name"], address=rec["principal_place_of_business"]); docs.pop("udyam")
    r = check_applicant(docs)
    assert "signatory_unchecked" in _codes(r) and r.verdict == "needs_review"

# Real reads from the specimens: K02 is clean but tilted, K06 has a planted 5->8, K03 only has look-alikes and dropped characters.
K02_READS = ["19EOGXH4115Y1ZL", "LSEOGXH4LI5Y1ZL", "LSEOGAH4LISYIZL", "LSEOGXH4LISYIZL", "ISEOGAH4LTISY1ZL"]
K06_READS = ["O08YKZXS8189L1Z0", "O8YKZXS8189L120", "O8YKZXS8189L120", "OSYKZXS8189L120", "O8YKZXS8189L120"]
K03_READS = ["27XUIXGO0767D1ZP", "27XUIXGO0767D1ZP", "2XUIXGO767D12ZP", "2XUIXGO767D12ZP", "2XUIXGO767D12ZP"]

def test_gstin_reading_on_real_reads():
    assert gstin_reading(K02_READS, "19EOGXH4115Y1ZL", reliable=False) == "match"  # tilted, so one full read clears it
    assert gstin_reading(K02_READS, "19EOGXH4115Y1ZL", reliable=True) == "unclear"  # the same reads on a straight page need a person
    assert gstin_reading(K03_READS, K03_GSTIN) == "match"
    assert gstin_reading(K06_READS, "08YKZXS5189L1ZO") == "differs"

def test_rejecting_needs_every_read_to_agree_on_a_good_image():
    want, forged = K03_GSTIN, "27XUIXG0767D2ZP"
    assert gstin_reading([forged] * 5, want) == "differs"
    assert gstin_reading([forged] * 5, want, reliable=False) == "unclear"  # tilted or small: a person decides
    assert gstin_reading([forged] * 2, want) == "unclear"                  # too few reads
    assert gstin_reading(["27XUIXG0767D7ZP"] * 2 + [forged] * 3, want) == "unclear"  # reads disagree on what it is
    assert gstin_reading(["QQQQQQQQQQQQQQQ"] * 5, want) == "unclear"      # garbage proves nothing
    assert gstin_reading([], want) == "unread"

def test_a_lucky_lookalike_read_cannot_hide_an_altered_digit():
    # Heavy JPEG on K06 once read the planted 8 as S, which looks like the record's 5, and passed as a match.
    assert gstin_reading(["08YKZXS8189L1ZO", "08YKZXS8189L1ZO", "08YKZXS8189L1ZO", "08YKZXSS189L1ZO"], "08YKZXS5189L1ZO") == "unclear"

def test_a_read_with_a_dropped_character_cannot_confirm_a_digit():
    # A tilted forgery: nearly every read saw the 7, and one that dropped it lined up the next 1 with the record's 1.
    reads = ["37NBLXS7145E1ZU"] * 4 + ["37NBLXS145E12U"]
    assert gstin_reading(reads, "37NBLXS1145E1ZU", reliable=False) == "unclear"

def test_one_full_read_can_still_clear_a_tilted_clean_document():
    assert gstin_reading(["1SEOGXH4115Y1ZL"] * 8 + ["19EOGXH4115Y1ZL"], "19EOGXH4115Y1ZL", reliable=False) == "match"

def test_tilted_garbled_gstin_is_reviewed_not_rejected():
    docs = _clean_docs(); docs["gst"].reliable = False
    docs["gst"].fields["gstin_reads"] = ",".join(["27XUIXG0767D2ZP"] * 5)
    r = check_applicant(docs)
    assert r.verdict == "needs_review" and "gstin_unclear" in _codes(r)

def test_names_tolerate_ocr_noise_but_not_real_changes():
    assert names_match("Harmony Denta! Care", "Harmony Dental Care") and names_match("GANESH  woodcraft", "Ganesh Woodcraft")
    assert not names_match("Neha Banerjee (Prop. Shri Physio Clinic)", "Neha Banerjee (Prop. Neelgiri Physio Clinic)")
    assert not names_match("", "") and not names_match(None, "x")
    assert _addr_ok("Shop/Unit 199, Station Road, Kolkata, West Bengat - 347550", "Shop/Unit 199, Station Road, Kolkata, West Bengal - 347550")
    assert not _addr_ok("Shop/Unit 198, Station Road, Kolkata, West Bengal - 347550", "Shop/Unit 199, Station Road, Kolkata, West Bengal - 347550")
    assert not _addr_ok("", "")

def test_another_business_on_a_document_never_verifies():
    for doc, field in (("bill", "billed_to"), ("id", "business"), ("udyam", "name")):
        for other in ("Green Leaf Legal Associates", "Kaveri Insurance Advisors"):
            assert _with(doc, **{field: other}).verdict != "verified"

# --- Real files, as owners and judges actually send them. Clean must never be rejected; a problem must never verify. ---
def _jpeg(im, q=70):
    b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=q); b.seek(0); return Image.open(b).copy()

@pytest.mark.parametrize("k", ["K02", "K03"])
def test_clean_applicant_as_jpeg_or_small_is_never_rejected(k):
    docs = load_specimen(k)
    assert verify_images({d: _jpeg(i) for d, i in docs.items()}).verdict != "rejected"
    assert verify_images({d: i.resize((i.width // 2, i.height // 2)) for d, i in docs.items()}).verdict != "rejected"

def _cut_and_paste(img, line, p, q):
    """Copy one printed character of the GSTIN line over another, as a forger would. line = (left, right, top, bottom)."""
    x0, x1, y0, y1 = line; pitch = (x1 - x0 + 1) / 15; x = img.convert("RGB").copy()
    box = lambda n: (round(x0 + n * pitch), y0, round(x0 + (n + 1) * pitch), y1)
    x.paste(x.crop(box(q)).resize((box(p)[2] - box(p)[0], y1 - y0)), box(p)[:2]); return x

K12_LINE = (522, 752, 243, 291)  # where K12's GSTIN is printed

@pytest.mark.parametrize("p,q", [(7, 1), (8, 3), (10, 1), (12, 9)])  # each copies a different character, so the number really changes
def test_cut_and_paste_forgery_never_verifies_straight_dim_or_tilted(p, q):
    from PIL import ImageEnhance
    s = load_specimen("K12"); forged = _cut_and_paste(s["gst"], K12_LINE, p, q)
    for form in (forged, ImageEnhance.Brightness(forged).enhance(.5), forged.rotate(3, expand=True, fillcolor="white", resample=Image.BICUBIC)):
        assert verify_images({**s, "gst": form}).verdict != "verified"

def test_altered_gstin_never_verifies_as_jpeg():
    for q in (70, 30):
        assert verify_images({d: _jpeg(i, q) for d, i in load_specimen("K06").items()}).verdict != "verified"

def test_sideways_page_and_exif_rotation_still_read():
    gst = load_specimen("K03")["gst"]
    assert extract(gst.rotate(90, expand=True), "gst").fields.get("trade_name") == "Ganesh Woodcraft"
    sideways = gst.convert("RGB").rotate(90, expand=True); exif = Image.Exif(); exif[0x0112] = 6
    b = io.BytesIO(); sideways.save(b, "JPEG", quality=92, exif=exif); b.seek(0)
    assert extract(Image.open(b), "gst").fields.get("trade_name") == "Ganesh Woodcraft"

def test_transparent_png_is_read_on_white():
    gst = load_specimen("K03")["gst"].convert("RGBA")
    assert prepare(gst).mode == "RGB" and extract(gst, "gst").fields.get("trade_name") == "Ganesh Woodcraft"

def test_clean_up_leaves_every_clean_specimen_untouched():
    import glob, numpy as np
    for f in glob.glob(str(pathlib.Path(__file__).parents[1] / "data/kyc_documents/*.png")):
        if "K04_gst" in f: continue  # the blurred one
        img = prepare(Image.open(f)); after = clean_up(img, sharpness(img))
        assert after.size == img.size and not (np.asarray(after) != np.asarray(img)).any(), f

def test_dim_photo_is_still_read():
    from PIL import ImageEnhance
    assert extract(ImageEnhance.Brightness(load_specimen("K03")["gst"].convert("RGB")).enhance(.5), "gst").fields.get("trade_name") == "Ganesh Woodcraft"

def test_wrong_document_and_blank_page_say_so_instead_of_blurred():
    s = load_specimen("K03")
    r = verify_images({"gst": s["bill"], "udyam": s["udyam"], "id": s["id"], "bill": s["gst"]})
    assert r.verdict == "needs_review" and {"wrong_gst", "wrong_bill"} <= _codes(r) and "Address proof" in r.reason and "blurred" not in r.reason
    blank = Image.new("RGB", (1240, 1754), "white")
    r = verify_images({k: blank for k in FILES})
    assert r.verdict == "needs_review" and "blurred" not in r.reason_in("en")

@pytest.mark.parametrize("data,why", [(b"hello", "bad_file"), (b"", "bad_file")])
def test_bad_files_get_a_reason_not_a_crash(data, why):
    assert open_upload(io.BytesIO(data)) == (None, why)

def test_cut_off_and_huge_files_get_a_reason_not_a_crash():
    png = (pathlib.Path(__file__).parents[1] / "data/kyc_documents/K03_gst_certificate.png").read_bytes()
    assert open_upload(io.BytesIO(png[:5000]))[1] == "bad_file"
    b = io.BytesIO(); Image.new("L", (7000, 7000)).save(b, "PNG"); b.seek(0)
    assert open_upload(b) == (None, "too_big")
    class Big(io.BytesIO): size = 11 * 1024 * 1024
    assert open_upload(Big(png)) == (None, "too_big")
    assert open_upload(io.BytesIO(png))[0] is not None

# --- Words and privacy ---
def test_every_message_exists_in_both_languages_and_fills_in():
    params = dict(other_en="Address proof", other_hi="पते का प्रमाण", status_en="cancelled", status_hi="रद्द", date="2025-10-31", days=257, max=90)
    for code, (doc, en, hi) in M.ISSUE.items():
        assert doc in M.DOC_NAME and M.issue_text(code, params, "en") and any("ऀ" <= ch <= "ॿ" for ch in M.issue_text(code, params, "hi")), code
    for code, (doc, en, hi) in M.PASSED.items():
        assert doc in M.DOC_NAME and any("ऀ" <= ch <= "ॿ" for ch in M.passed_text(code, params, "hi")), code

def test_every_issue_code_raised_has_a_message():
    src = (pathlib.Path(__file__).parents[1] / "core/kyc/checks.py").read_text(encoding="utf-8")
    import re
    for code in re.findall(r'add\("(?:review|reject)", "(\w+)"', src): assert code in M.ISSUE, code
    for code in re.findall(r'\bok\("(\w+)"', src): assert code in M.PASSED, code

def test_results_never_reveal_a_registry_value_or_a_full_id(results):
    k07 = results["K07"]
    assert "Neelgiri" not in k07.reason and "Banerjee" not in k07.reason  # no hint of what a forged document should say
    for k, r in results.items():
        blob = json.dumps(r.fields) + r.reason + json.dumps(r.read)
        assert "SYN-ID" not in blob
        assert not re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]{3}\b", blob)
        assert not re.search(r"UDYAM-[A-Z]{2}-00-\d{7}", blob)

def test_kyc_code_never_touches_the_llm():
    for f in (pathlib.Path(__file__).parents[1] / "core/kyc").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "llm" not in text.lower() or f.name == "pipeline.py" and "go to an LLM" in text, f.name
        assert "genai" not in text

def test_the_stated_upload_limit_is_the_real_one():
    from core.kyc.pipeline import MAX_UPLOAD_MB
    assert f"maxUploadSize = {MAX_UPLOAD_MB}" in (pathlib.Path(__file__).parents[1] / ".streamlit/config.toml").read_text()
