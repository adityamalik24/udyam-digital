"""Cross-document checks producing one verdict. Unsure means needs_review; rejected needs hard evidence."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from ..pricing import TODAY
from . import registry
from .ocr import Extracted
from .validators import gstin_problem, valid_udyam, mask

NAME_MIN = 92     # K07 ("Shri" for "Neelgiri") scores below this; OCR noise like "Denta!" stays above
ADDRESS_MIN = 90
BILL_MAX_AGE_DAYS = 90  # data/README.md
BLUR_MIN = 150    # sharpness: clean specimens 470+, blurred K04 43


@dataclass
class Issue:
    severity: str  # reject | review
    code: str
    message: str


@dataclass
class Result:
    verdict: str
    reason: str
    issues: list[Issue] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)  # minimised and masked; safe to store


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def name_score(a, b) -> float:
    return fuzz.ratio(_norm(a), _norm(b))


def _addr_ok(a: str, b: str) -> bool:
    pin = lambda s: re.findall(r"\d{6}", re.sub(r"(?<=\d)\s+(?=\d)", "", s or ""))
    return bool(pin(a)) and pin(a) == pin(b) and fuzz.ratio(_norm(a), _norm(b)) >= ADDRESS_MIN


def _date(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def link_gstin(reads: list[str], trade: str, address: str):
    """Find the registry record, tolerating OCR noise. Returns (record, printed_differs)."""
    record = None
    for r in reads:
        rec, _ = registry.lookup_gstin(r)
        if rec: record = rec; break
    if record is None:
        rec, score = registry.find_gst_by_trade(trade or "", address or "")
        if rec and score >= 90: record = rec
    if record is None:
        return None, False
    target = registry.canon(record["gstin"])
    # A read with no substitution against the record agrees; inserts and drops are segmentation noise.
    differs = all(any(op.tag == "replace" for op in Levenshtein.editops(registry.canon(r), target)) for r in reads) if reads else False
    return record, differs


def check_applicant(docs: dict[str, Extracted], entered_gstin: str | None = None, today: date = TODAY) -> Result:
    issues, ok = [], []
    def add(sev, code, msg): issues.append(Issue(sev, code, msg))
    for key, label in (("gst", "GST certificate"), ("udyam", "Udyam certificate"), ("id", "signatory ID"), ("bill", "address proof")):
        if key not in docs:
            add("review", f"missing_{key}", f"The {label} was not provided.")
    unreadable = set()
    for key, e in docs.items():
        if e.sharpness < BLUR_MIN or len(e.fields) < 3:
            unreadable.add(key)
            add("review", f"blurry_{key}", f"The {key.upper()} document is too blurred to read reliably; please upload a clearer copy.")
    g, u, i, b = docs.get("gst"), docs.get("udyam"), docs.get("id"), docs.get("bill")
    record, out = None, {}
    if g and "gst" not in unreadable:
        f = g.fields
        reads = [x for x in f.get("gstin_reads", f.get("gstin", "")).split(",") if x]
        record, differs = link_gstin(reads, f.get("trade_name"), f.get("address"))
        out["gstin_printed_masked"] = mask(f.get("gstin"))
        if record is None:
            add("review", "gst_not_found", "We could not find this GSTIN in the registry.")
        else:
            out["gstin_masked"] = mask(record["gstin"]); out["registry_status"] = record["status"]
            if differs:
                add("reject", "gst_number_mismatch",
                    "The GSTIN printed on the certificate has a character that differs from the registry record for this business, so it may have been altered.")
            else:
                ok.append("GSTIN on certificate matches registry")
            if record["status"] != "Active":
                add("reject", "gst_inactive", f"This GSTIN is {record['status'].lower()} in the registry, so we can't activate on it.")
            else:
                ok.append("GST registration is active")
            s = name_score(f.get("legal_name"), record["legal_name"])
            if s < NAME_MIN:
                add("review", "legal_name_mismatch", f"The legal name on the certificate (\"{f.get('legal_name')}\") differs from the registry (\"{record['legal_name']}\").")
            else:
                ok.append("Legal name matches registry")
            if entered_gstin and registry.canon(entered_gstin.upper()) != registry.canon(record["gstin"]):
                add("review", "entered_mismatch", "The GSTIN you typed differs from the one on the certificate.")
            if gstin_problem(record["gstin"]):
                add("review", "gst_format", "The registry GSTIN failed the format check.")
    trade = record["trade_name"] if record else (g.fields.get("trade_name") if g else None)
    if u and "udyam" not in unreadable:
        num = u.fields.get("udyam", "")
        if not num:
            add("review", "udyam_blank", "The Udyam number is missing from the Udyam certificate.")
        elif not valid_udyam(num):
            add("review", "udyam_format", "The Udyam number on the certificate isn't in the UDYAM-XX-00-0000000 format.")
        else:
            rec = registry.lookup_udyam(num)
            if not rec:
                add("review", "udyam_not_found", "This Udyam number isn't in the registry.")
            elif name_score(rec["enterprise_name"], u.fields.get("name")) < NAME_MIN:
                add("review", "udyam_name_mismatch", "The name on the Udyam certificate differs from the Udyam registry.")
            else:
                ok.append("Udyam number and name match registry")
        if trade and name_score(u.fields.get("name"), trade) < NAME_MIN:
            add("review", "udyam_vs_gst", "The enterprise name on the Udyam certificate differs from the GST trade name.")
    if b and "bill" not in unreadable:
        d = _date(b.fields.get("date"))
        if d is None:
            add("review", "bill_date", "We couldn't read the date on the address proof.")
        elif (today - d).days > BILL_MAX_AGE_DAYS:
            add("review", "bill_stale", f"The address proof is dated {d} ({(today - d).days} days old); we accept up to {BILL_MAX_AGE_DAYS} days. Please upload a recent bill.")
        else:
            ok.append(f"Address proof is recent (within {BILL_MAX_AGE_DAYS} days)")
        if record:
            if _addr_ok(b.fields.get("address"), record["principal_place_of_business"]):
                ok.append("Bill address matches registry")
            else:
                add("review", "address_mismatch", "The address on the bill doesn't match the registered business address.")
            if name_score(b.fields.get("billed_to"), record["trade_name"]) < NAME_MIN:
                add("review", "bill_name", "The bill is in a different business name.")
    if i and "id" not in unreadable:
        out["id_masked"] = mask(i.fields.get("id_no"))
        d = _date(i.fields.get("valid_till"))
        if d is None:
            add("review", "id_date", "We couldn't read the expiry date on the signatory ID.")
        elif d < today:
            add("review", "id_expired", f"The signatory ID expired on {d}. Please upload a valid ID.")
        else:
            ok.append("Signatory ID is valid")
        if trade and name_score(i.fields.get("business"), trade) < NAME_MIN:
            add("review", "id_business", "The signatory ID is for a different business.")
        prop = re.match(r"(.+?)\s*\(Prop", (record or {}).get("legal_name", ""))
        if prop:
            if name_score(prop.group(1), i.fields.get("name")) < NAME_MIN:
                add("review", "signatory_mismatch", "The name on the signatory ID differs from the proprietor on the GST record.")
            else:
                ok.append("Signatory matches proprietor")
        contact = registry.lead_contact(record["gstin"]) if record else None
        if contact and not prop:
            if name_score(contact, i.fields.get("name")) < NAME_MIN:
                add("review", "signatory_vs_lead", "The name on the signatory ID differs from the contact person on this business's application.")
            else:
                ok.append("Signatory matches the contact on the application")
    rej = [x for x in issues if x.severity == "reject"]
    if rej:
        return Result("rejected", " ".join(x.message for x in rej), issues, ok, out)
    if issues:
        return Result("needs_review", " ".join(x.message for x in issues), issues, ok, out)
    return Result("verified", "All documents are consistent and the business is active in the registry.", issues, ok, out)
