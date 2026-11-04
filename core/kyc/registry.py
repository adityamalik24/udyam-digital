"""Mock GSTIN and Udyam lookups over the provided CSVs."""
import csv
from functools import lru_cache
from ..catalogue import DATA

# Characters Tesseract confuses on this certificate font (O/0, I/J/1, Z/2 ...). Used only to
# link a raw read to a registry record; the raw read itself is stored unchanged.
_CONF = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "J": "1", "T": "1", "Z": "2", "S": "5", "B": "8", "G": "6"})


def canon(s: str) -> str:
    return s.translate(_CONF)


@lru_cache
def _gst():
    with open(DATA / "mock_gstin_registry.csv", newline="", encoding="utf-8") as f:
        return {r["gstin"]: r for r in csv.DictReader(f)}


@lru_cache
def _gst_canon():
    out = {}
    for k, v in _gst().items():
        out.setdefault(canon(k), []).append(v)
    return out


@lru_cache
def _udyam():
    with open(DATA / "mock_udyam_registry.csv", newline="", encoding="utf-8") as f:
        return {r["udyam_number"]: r for r in csv.DictReader(f)}


def lookup_gstin(g: str):
    """(record, exact). exact=False: the read differs only in look-alike characters."""
    if g in _gst(): return _gst()[g], True
    hits = _gst_canon().get(canon(g), [])
    return (hits[0], False) if len(hits) == 1 else (None, False)


def lookup_udyam(u: str):
    return _udyam().get(u)


def find_gst_by_trade(trade: str, address: str):
    from rapidfuzz import fuzz
    best, score = None, 0
    for r in _gst().values():
        s = fuzz.token_set_ratio(r["trade_name"], trade) * 0.5 + fuzz.ratio(r["principal_place_of_business"], address) * 0.5
        if s > score: best, score = r, s
    return best, score


def all_gstins():
    return list(_gst())


def all_udyam():
    return list(_udyam())


@lru_cache(maxsize=1)
def _lead_contacts() -> dict:
    import csv
    with open(DATA / "smb_leads.csv", encoding="utf-8") as f:
        return {r["gstin"]: r["contact_name"] for r in csv.DictReader(f) if r["gstin"]}


def lead_contact(gstin: str) -> str | None:
    """Person named on the sales lead for this GSTIN. The only name to compare against for companies and LLPs."""
    return _lead_contacts().get(gstin)
