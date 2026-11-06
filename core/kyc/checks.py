"""Cross-document checks producing one verdict. Unsure means needs_review; rejected needs hard evidence."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from ..pricing import TODAY
from . import messages as M, registry
from .ocr import Extracted
from .validators import gstin_problem, valid_udyam, mask

NAME_MIN = 92     # K07 ("Shri" for "Neelgiri") scores below this; OCR noise like "Denta!" stays above
NAME_MAX_EDITS = 2  # correct names read within 1 edit on every specimen; a long name can hide a real change from the ratio
ADDRESS_MIN = 90
ADDRESS_MAX_EDITS = 4
BILL_MAX_AGE_DAYS = 90  # data/README.md
BLUR_MIN = 150    # sharpness: clean specimens 470+, blurred K04 43
MIN_READS = 3     # a mismatch must persist across this many independent reads of the GSTIN line
MAX_READ_EDITS = 3  # further from the record than this, a read is noise and proves nothing


@dataclass
class Issue:
    severity: str  # reject | review
    code: str
    message: str
    params: dict = field(default_factory=dict)


@dataclass
class Result:
    verdict: str
    reason: str
    issues: list[Issue] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)  # minimised and masked; safe to store
    checks: list[tuple[str, dict]] = field(default_factory=list)  # passed checks as (code, params), for any language
    read: dict = field(default_factory=dict)  # what was read per document, IDs masked; shown on screen, never stored
    unused: int = 0  # files we couldn't recognise and so didn't use

    def reason_in(self, lang: str) -> str:
        if self.verdict == "verified": return M.VERIFIED_HI if lang == "hi" else M.VERIFIED_EN
        shown = [i for i in self.issues if i.severity == "reject"] or self.issues
        return " ".join(M.issue_text(i.code, i.params, lang) for i in shown)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def name_score(a, b) -> float:
    return fuzz.ratio(_norm(a), _norm(b))


def names_match(a, b) -> bool:
    x, y = _norm(a), _norm(b)
    return bool(x and y) and fuzz.ratio(x, y) >= NAME_MIN and Levenshtein.distance(x, y) <= NAME_MAX_EDITS


def _addr_ok(a: str, b: str) -> bool:
    """Words may carry OCR noise, but every digit (unit number, PIN) must agree exactly."""
    x, y = _norm(a), _norm(b)
    digits = lambda t: re.sub(r"\D", "", t)
    return bool(digits(x)) and digits(x) == digits(y) and fuzz.ratio(x, y) >= ADDRESS_MIN and Levenshtein.distance(x, y) <= ADDRESS_MAX_EDITS


def _date(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def gstin_reading(reads: list[str], target: str, reliable: bool = True) -> str:
    """How the reads of a printed GSTIN compare with the registry record. Reads are compared, never corrected.
    match: the record's characters were read, allowing for look-alikes. unread: no reads.
    differs: the same non-look-alike substitution persists in every read of a good-quality image, the only hard
    evidence of alteration (data/README.md). unclear: anything else, which is grounds for a person, never a rejection."""
    if not reads: return "unread"
    want, usable, wrong, seen = registry.canon(target), 0, {}, set()
    for r in reads:
        read = registry.canon(r)
        ops = Levenshtein.editops(read, want)
        if len(ops) > MAX_READ_EDITS: continue  # too garbled to say anything
        usable += 1
        for block in Levenshtein.opcodes(read, want):
            for n in range(block.dest_end - block.dest_start):
                pos = block.dest_start + n
                # Only a read of full length can confirm a character: a dropped one shifts everything after it into false agreement.
                if block.tag == "equal" and len(read) == len(want) and r[block.src_start + n] == target[pos]: seen.add(pos)
                if block.tag == "replace": wrong.setdefault(pos, []).append(read[block.src_start + n])
    if not usable: return "unclear"
    for pos, got in wrong.items():
        if reliable and len(got) * 2 > usable:  # one lucky read can't outvote the rest on a good image
            persists = usable == len(reads) >= MIN_READS and len(got) == usable and len(set(got)) == 1
            return "differs" if persists else "unclear"
    # A tilted or small image garbles reads, so one read seeing the printed character is enough; it can still never reject.
    if any(pos not in seen and len(got) * 2 >= usable for pos, got in wrong.items()): return "unclear"
    return "match"


def link_gstin(reads: list[str], trade: str, address: str, reliable: bool = True):
    """Find the registry record, tolerating OCR noise. Returns (record, how the printed number compares)."""
    record = None
    for r in reads:
        rec, _ = registry.lookup_gstin(r)
        if rec: record = rec; break
    if record is None:
        rec, score = registry.find_gst_by_trade(trade or "", address or "")
        if rec and score >= 90: record = rec
    if record is None:
        return None, "unread"
    return record, gstin_reading(reads, record["gstin"], reliable)


def _shown(doc: str, f: dict) -> dict:
    """What we read, for the owner to check. ID-like values are masked; none of this is stored."""
    keep = {"gst": ("legal_name", "trade_name", "constitution", "address"), "udyam": ("name", "city", "state"),
            "id": ("name", "designation", "business", "valid_till"), "bill": ("billed_to", "address", "date")}[doc]
    out = {k: f[k] for k in keep if f.get(k)}
    for k in ("gstin", "udyam", "id_no"):
        if f.get(k): out[k] = mask(f[k])
    return out


def check_applicant(docs: dict[str, Extracted], entered_gstin: str | None = None, today: date = TODAY, duplicates: tuple = ()) -> Result:
    issues, checks = [], []
    def add(sev, code, **params):
        issues.append(Issue(sev, code, M.issue_text(code, params), params))
    def ok(code, **params): checks.append((code, params))
    for key in ("gst", "udyam", "id", "bill"):
        if key not in docs: add("review", f"missing_{key}")
    for key in duplicates: add("review", f"duplicate_{key}")  # never quietly pick one of two conflicting documents
    unreadable = set()
    for key, e in docs.items():
        if e.sharpness < BLUR_MIN and e.text.strip():  # a blank page is soft too, but "blurred" would be the wrong thing to tell the owner
            unreadable.add(key); add("review", f"blurry_{key}")
        elif len(e.fields) < 3:
            unreadable.add(key)
            if e.looks_like and e.looks_like != key:
                add("review", f"wrong_{key}", other_en=M.DOC_NAME[e.looks_like]["en"], other_hi=M.DOC_NAME[e.looks_like]["hi"])
            else:
                add("review", f"unreadable_{key}")
    g, u, i, b = docs.get("gst"), docs.get("udyam"), docs.get("id"), docs.get("bill")
    record, out = None, {}
    if g and "gst" not in unreadable:
        f = g.fields
        reads = [x for x in f.get("gstin_reads", f.get("gstin", "")).split(",") if x]
        record, printed = link_gstin(reads, f.get("trade_name"), f.get("address"), g.reliable)
        if record is None:
            add("review", "gst_not_found")
        else:
            ok("gst_lookup")
            out["gstin_masked"] = mask(record["gstin"]); out["registry_status"] = record["status"]
            if printed == "differs": add("reject", "gst_number_mismatch")
            elif printed == "unclear": add("review", "gstin_unclear")
            elif printed == "unread": add("review", "gstin_unread")
            else: ok("gstin_match")
            if record["status"] != "Active":
                en, hi = M.STATUS.get(record["status"], (record["status"].lower(), record["status"]))
                add("reject", "gst_inactive", status_en=en, status_hi=hi)
            else:
                ok("gst_active")
            if names_match(f.get("legal_name"), record["legal_name"]): ok("legal_name")
            else: add("review", "legal_name_mismatch")
            before = len(issues)
            if not names_match(f.get("trade_name"), record["trade_name"]): add("review", "trade_name_mismatch")
            if not _addr_ok(f.get("address"), record["principal_place_of_business"]): add("review", "gst_address_mismatch")
            if not names_match(f.get("constitution"), record["constitution"]): add("review", "constitution_mismatch")
            if _date(f.get("liability_date")) != _date(record["registration_date"]): add("review", "liability_date_mismatch")
            if len(issues) == before: ok("gst_details")
            if entered_gstin and registry.canon(entered_gstin.upper()) != registry.canon(record["gstin"]):
                add("review", "entered_mismatch")
            if gstin_problem(record["gstin"]):
                add("review", "gst_format")
    trade = record["trade_name"] if record else (g.fields.get("trade_name") if g else None)
    if u and "udyam" not in unreadable:
        num = u.fields.get("udyam", "")
        if not num:
            add("review", "udyam_blank")
        elif not valid_udyam(num):
            add("review", "udyam_format")
        else:
            rec = registry.lookup_udyam(num)
            if not rec:
                add("review", "udyam_not_found")
            else:
                if names_match(rec["enterprise_name"], u.fields.get("name")): ok("udyam_match")
                else: add("review", "udyam_name_mismatch")
                # Udyam date and activity disagree with the registry even for clean applicants (data/README.md), so only the place is compared.
                if names_match(rec["city"], u.fields.get("city")) and names_match(rec["state"], u.fields.get("state")): ok("udyam_place")
                else: add("review", "udyam_place_mismatch")
        if trade:
            if names_match(u.fields.get("name"), trade): ok("udyam_gst")
            else: add("review", "udyam_vs_gst")
    if b and "bill" not in unreadable:
        d = _date(b.fields.get("date"))
        if d is None:
            add("review", "bill_date")
        elif d > today:
            add("review", "bill_future", date=str(d))
        elif (today - d).days > BILL_MAX_AGE_DAYS:
            add("review", "bill_stale", date=str(d), days=(today - d).days, max=BILL_MAX_AGE_DAYS)
        else:
            ok("bill_recent", max=BILL_MAX_AGE_DAYS)
        if record:
            if _addr_ok(b.fields.get("address"), record["principal_place_of_business"]): ok("bill_address")
            else: add("review", "address_mismatch")
            if names_match(b.fields.get("billed_to"), record["trade_name"]): ok("bill_billed_to")
            else: add("review", "bill_name")
    if i and "id" not in unreadable:
        if i.fields.get("id_no"): out["id_masked"] = mask(i.fields["id_no"])
        else: add("review", "id_number_blank")
        d = _date(i.fields.get("valid_till"))
        if d is None:
            add("review", "id_date")
        elif d < today:
            add("review", "id_expired", date=str(d))
        else:
            ok("id_valid")
        if trade:
            if names_match(i.fields.get("business"), trade): ok("id_for_business")
            else: add("review", "id_business")
        prop = re.match(r"(.+?)\s*\(Prop", (record or {}).get("legal_name", ""))
        contact = registry.lead_contact(record["gstin"]) if record else None
        if prop:
            if names_match(prop.group(1), i.fields.get("name")): ok("signatory_prop")
            else: add("review", "signatory_mismatch")
        elif contact:
            if names_match(contact, i.fields.get("name")): ok("signatory_lead")
            else: add("review", "signatory_vs_lead")
        elif record:  # nothing to compare the name with, so don't vouch for it
            add("review", "signatory_unchecked")
    out["issues"] = [x.code for x in issues]  # codes only, so a reviewer's queue needs no names or numbers
    res = dict(issues=issues, passed=[M.passed_text(c, p) for c, p in checks], fields=out, checks=checks,
               read={k: _shown(k, e.fields) for k, e in docs.items() if k not in unreadable})
    rej = [x for x in issues if x.severity == "reject"]
    if rej:
        return Result("rejected", " ".join(x.message for x in rej), **res)
    if issues:
        return Result("needs_review", " ".join(x.message for x in issues), **res)
    return Result("verified", M.VERIFIED_EN, **res)
