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
from core.kyc.pipeline import load_specimen, look_up_gstin, look_up_udyam, open_upload, verify_files, verify_images, FILES
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

@pytest.mark.parametrize("data", [b"hello", b"", b"%PDF-1.4 not really a pdf"])
def test_bad_files_get_a_reason_not_a_crash(data):
    assert open_upload(io.BytesIO(data)) == ([], "bad_file")

def test_cut_off_and_huge_files_get_a_reason_not_a_crash():
    png = (pathlib.Path(__file__).parents[1] / "data/kyc_documents/K03_gst_certificate.png").read_bytes()
    assert open_upload(io.BytesIO(png[:5000]))[1] == "bad_file"
    b = io.BytesIO(); Image.new("L", (7000, 7000)).save(b, "PNG"); b.seek(0)
    assert open_upload(b) == ([], "too_big")
    class Big(io.BytesIO): size = 11 * 1024 * 1024
    assert open_upload(Big(png)) == ([], "too_big")
    pages, why = open_upload(io.BytesIO(png)); assert len(pages) == 1 and why is None

# --- Files in any order, and PDFs ---
def _pdf(*images):
    b = io.BytesIO(); first = images[0].convert("RGB")
    first.save(b, "PDF", resolution=150, save_all=True, append_images=[i.convert("RGB") for i in images[1:]]); b.seek(0); return b

def _shuffled(k):
    d = load_specimen(k); return [d[x] for x in reversed(list(d))]

@pytest.mark.parametrize("k", list(EXPECTED))
def test_files_in_any_order_get_the_same_verdict_and_reason_as_named_slots(k, results):
    r = verify_files(_shuffled(k))
    assert r.verdict == results[k].verdict and _codes(r) == {i.code for i in results[k].issues} and r.unused == 0

def test_blurred_page_is_placed_by_elimination_and_named_correctly():
    r = verify_files(_shuffled("K04")); assert "blurry_gst" in _codes(r)

def test_two_unrecognised_files_are_not_guessed():
    s = load_specimen("K03"); blank = Image.new("RGB", (1240, 1754), "white")
    r = verify_files([s["id"], s["bill"], blank, blank.copy()])
    assert r.verdict == "needs_review" and {"missing_gst", "missing_udyam"} <= _codes(r) and r.unused == 2

def test_extra_junk_file_is_reported_but_not_held_against_a_clean_applicant():
    r = verify_files(_shuffled("K03") + [Image.new("RGB", (800, 800), "white")])
    assert r.verdict == "verified" and r.unused == 1

def test_the_same_file_twice_is_fine_but_two_different_documents_go_to_a_person():
    s = load_specimen("K03")
    assert verify_files(_shuffled("K03") + [s["bill"]]).verdict == "verified"
    r = verify_files(_shuffled("K03") + [load_specimen("K08")["bill"]])
    assert r.verdict == "needs_review" and "duplicate_bill" in _codes(r)
    r = verify_files([load_specimen("K08")["gst"]] + _shuffled("K03"))
    assert r.verdict != "verified" and "duplicate_gst" in _codes(r)

def test_nothing_recognised_never_verifies():
    r = verify_files([Image.new("RGB", (800, 800), "white")])
    assert r.verdict == "needs_review" and len([c for c in _codes(r) if c.startswith("missing_")]) >= 3

def test_a_pdf_for_each_document_and_one_pdf_of_everything_both_work():
    s = load_specimen("K03")
    pages = [p for d in s.values() for p in open_upload(_pdf(d))[0]]
    assert len(pages) == 4 and verify_files(pages).verdict == "verified"
    together, why = open_upload(_pdf(*s.values()))
    assert why is None and len(together) == 4 and verify_files(together).verdict == "verified"

@pytest.mark.parametrize("k,want", [("K01", "rejected"), ("K06", "rejected"), ("K11", "needs_review"), ("K05", "needs_review")])
def test_problems_are_still_caught_through_a_pdf(k, want):
    assert verify_files(open_upload(_pdf(*load_specimen(k).values()))[0]).verdict == want

def test_too_many_pdf_pages_are_refused():
    assert open_upload(_pdf(*[Image.new("RGB", (200, 200), "white")] * 9)) == ([], "too_many")

def test_type_comes_from_the_content_not_the_name():
    class Named(io.BytesIO): name = "gst.png"
    assert len(open_upload(Named(_pdf(load_specimen("K03")["gst"]).getvalue()))[0]) == 1

def test_a_pdf_hidden_text_layer_is_ignored():
    # A page that draws one GSTIN in white-on-white text and nothing visible must read as blank: only what's drawn counts.
    stream = b"BT /F1 12 Tf 1 1 1 rg 72 700 Td (GSTIN 27XUIXG0767D1ZP Legal name Ganesh Woodcraft Trade name Ganesh Woodcraft) Tj ET"
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>", b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            b"<</Length %d>>stream\n%s\nendstream" % (len(stream), stream), b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    pdf = b"%PDF-1.4\n"; at = []
    for i, o in enumerate(objs, 1): at.append(len(pdf)); pdf += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    x = len(pdf); pdf += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % a for a in at) + b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % x
    pages, why = open_upload(io.BytesIO(pdf)); assert why is None and len(pages) == 1
    assert extract(pages[0]).doc is None

# --- Instant number lookup ---
def test_gstin_lookup_states_and_only_a_masked_status_comes_back():
    active = next(g for g, r in registry._gst().items() if r["status"] == "Active")
    cancelled = next(g for g, r in registry._gst().items() if r["status"] == "Cancelled")
    suspended = next(g for g, r in registry._gst().items() if r["status"] == "Suspended")
    r = look_up_gstin(active); assert r == {"state": "active", "masked": mask(active)} and active not in str(r)
    assert look_up_gstin(cancelled)["state"] == "cancelled" and look_up_gstin(suspended)["state"] == "suspended"
    assert look_up_gstin(f"  {active[:5].lower()} {active[5:]} ")["state"] == "active"  # spaces and case are a typist's noise
    for bad in ("", "ABC", "1234 5678 9012", "ABCDE1234F"): assert look_up_gstin(bad) == {"state": "bad_format"}
    assert set(look_up_gstin(active)) == {"state", "masked"}

def test_gstin_lookup_is_never_corrected():
    g = "08YKZXS5189L1ZO"; assert look_up_gstin(g)["state"] == "active"
    assert look_up_gstin(g.replace("L1ZO", "L1Z0"))["state"] != "active"  # O typed as 0 is not this number
    assert look_up_gstin("08YKZXS8189L1ZO")["state"] != "active"  # K06's altered number

def test_udyam_lookup():
    u = next(iter(registry.all_udyam()))
    assert look_up_udyam(u) == {"state": "found", "masked": mask(u)}
    assert look_up_udyam("UDYAM-MH-00-0000000")["state"] == "not_found" and look_up_udyam("12345")["state"] == "bad_format"

def test_typed_gstin_is_compared_with_the_certificate():
    r = verify_files(_shuffled("K03"), "24XORXG9365M1Z3"); assert r.verdict == "needs_review" and "entered_mismatch" in _codes(r)
    assert verify_files(_shuffled("K03"), K03_GSTIN).verdict == "verified"

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


def test_k05_stays_with_a_person_but_tells_them_the_registry_can_settle_it(results):
    r = results["K05"]
    assert r.verdict == "needs_review" and "udyam_on_file" in {c for c, _ in r.checks} and "UDYAM-" not in str(r.fields)
    assert "udyam_on_file" not in {c for k, x in results.items() if k != "K05" for c, _ in x.checks}


# --- From Team RNG's other build ---
def test_a_small_change_to_a_proprietor_cannot_hide_in_a_long_legal_name():
    from core.kyc.checks import legal_names_match
    good = "Joseph Singh (Prop. Ganesh Woodcraft)"
    assert legal_names_match("Joseph Singh (Prop. Ganesh Woodcraft)", good) and legal_names_match("Joseph Singh (Prop. Ganesh Woodcrafl)", good)
    assert not legal_names_match("Joseph Sinha (Prop. Ganesh Woodcraft)", good)
    assert not legal_names_match("Jose Singh (Prop. Ganesh Woodcraft)", good)
    assert _with("gst", legal_name="Joseph Sinha (Prop. Ganesh Woodcraft)").verdict == "needs_review"


def test_company_suffixes_and_ampersands_are_the_same_name():
    assert names_match("Trinity Bake House Pvt Ltd", "Trinity Bake House Private Limited") and names_match("Vindhya Tours & Travels", "Vindhya Tours and Travels") and not names_match("Trinity Bake House", "Trinity Cake House Stores")


def test_a_slightly_misread_label_is_still_found():
    from core.kyc.ocr import parse
    f = parse("GSTIN 27XUIXG0767D1ZP\nLegai narne Joseph Singh\nTrade nane Ganesh Woodcraft\nDate of liabilty 2020-02-10", "gst")
    assert f["legal_name"] == "Joseph Singh" and f["trade_name"] == "Ganesh Woodcraft" and f["liability_date"] == "2020-02-10"
    assert "billed_to" not in parse("Billing cycle is monthly\nBuilt by us", "bill")


def test_a_plan_without_gstin_asks_only_for_id_and_address_proof():
    s = load_specimen("K03")
    full = verify_files([s["id"], s["bill"]], gst_optional=True)
    assert full.verdict == "verified" and not [c for c in _codes(full) if c in ("missing_gst", "missing_udyam")]
    assert verify_files([s["id"], s["bill"]]).verdict == "needs_review"  # a plan that needs one still asks
    assert verify_files([s["id"], load_specimen("K08")["bill"]], gst_optional=True).verdict == "needs_review"  # the ID and bill must agree
    assert verify_files([s["id"]], gst_optional=True).verdict == "needs_review"


def test_a_supplied_gst_certificate_is_always_checked_even_when_optional():
    k = load_specimen("K01"); assert verify_files(list(k.values()), gst_optional=True).verdict == "rejected"


def test_a_supplied_udyam_alone_keeps_the_gst_question_open():
    s = load_specimen("K03"); r = verify_files([s["id"], s["bill"], s["udyam"]], gst_optional=True); assert "missing_gst" in _codes(r)


def test_ocr_outage_is_a_clear_error_not_a_verdict(monkeypatch):
    import pytesseract
    from core.kyc.ocr import OcrUnavailable
    def gone(*a, **k): raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "image_to_string", gone)
    with pytest.raises(OcrUnavailable): verify_images(load_specimen("K03"))


def test_a_pdf_that_hangs_or_crashes_the_worker_only_fails_that_file(monkeypatch):
    import subprocess as sp
    from core.kyc import pipeline
    def hang(*a, **k): raise sp.TimeoutExpired("x", 1)
    monkeypatch.setattr(pipeline.subprocess, "run", hang)
    assert open_upload(io.BytesIO(b"%PDF-1.4 anything")) == ([], "bad_file")
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, -9, b"", b""))
    assert open_upload(io.BytesIO(b"%PDF-1.4 anything")) == ([], "bad_file")


def test_phone_sized_photos_of_a_clean_applicant_still_verify():
    """A large phone JPEG must not read as blurry just because each pixel is soft (it did at a 3000-pixel cap)."""
    import io
    from PIL import Image
    from core.kyc.pipeline import load_specimen, verify_images
    big = {}
    for d, im in load_specimen("K03").items():
        im = im.convert("RGB").resize((round(im.width * 2.3), round(im.height * 2.3)), Image.LANCZOS)
        b = io.BytesIO(); im.save(b, "JPEG", quality=88); big[d] = Image.open(io.BytesIO(b.getvalue()))
    assert verify_images(big).verdict == "verified"


def test_huge_photos_open_small_and_huge_pngs_are_refused():
    import io
    from PIL import Image
    from core.kyc import ocr
    from core.kyc.pipeline import open_image, open_upload
    big = Image.new("RGB", (5300, 7500), "white"); b = io.BytesIO(); big.save(b, "JPEG", quality=70)
    opened = open_image(b.getvalue()); opened.load()
    assert min(opened.size) >= ocr.MAX_SIDE // 2 and max(opened.size) >= ocr.MAX_SIDE and opened.size != (5300, 7500)
    small = Image.new("RGB", (3000, 4000), "white"); b2 = io.BytesIO(); small.save(b2, "JPEG")
    assert open_image(b2.getvalue()).size == (3000, 4000)  # a normal phone photo is decoded as it is
    png = Image.new("L", (5000, 6000), 255); b3 = io.BytesIO(); png.save(b3, "PNG")
    class F(io.BytesIO):
        size = 0
    assert open_upload(F(b3.getvalue())) == ([], "too_big")
