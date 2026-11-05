"""Eligibility, dependencies and recommendation. Decides every product; the LLM never does."""
from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from .catalogue import catalogue, Product
from .pricing import price, Quote

MICRO = {"kirana", "salon", "pharmacy", "retailer", "bakery", "shop"}
NEEDS = ["internet", "internet_for_upi_pos", "uptime", "failover", "customer_messaging", "sms", "cloud_email",
         "storage", "security", "firewall", "cctv", "wifi", "pos_billing", "website", "dedicated_bandwidth",
         "high_speed", "iot", "fleet", "telephony", "toll_free", "static_ip", "sdwan", "mobile_line", "mobile_premium"]
# Bought standalone: these carry their own connectivity or need none.
STANDALONE = {"mobile_premium", "mobile_line", "website", "fleet", "iot", "sms", "customer_messaging", "toll_free"}
EXISTING_LINK = {"business_broadband", "leased_line", "existing_link"}
LARGE_STAFF, LARGE_SITES = 1000, 100  # far beyond small business: a person should check these
NEED_PRODUCT = {"failover": "P09", "uptime": "P09", "customer_messaging": "P15", "sms": "P14", "cloud_email": "P16",
                "storage": "P17", "security": "P20", "firewall": "P21", "cctv": "P23", "wifi": "P22", "pos_billing": "P19",
                "website": "P18", "iot": "P24", "fleet": "P25", "telephony": "P12", "toll_free": "P13",
                "static_ip": "P11", "sdwan": "P10", "mobile_line": "P07", "mobile_premium": "P08"}
FIBRE_ONLY = {"P09", "P10", "P11", "P21"}  # their requires_one_of excludes AirFiber (P04)
PROFESSIONAL = {"clinic", "ca_firm", "coaching", "law", "office"}


class Profile(BaseModel):
    business_type: str | None = None
    employees: int | None = None
    locations: int | None = None
    city: str | None = None
    city_tier: int | None = None
    has_gstin: bool | None = None
    current_setup: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    language: str = "en"
    sim_lines: int = 1
    cameras: int = 1
    vehicles: int = 1
    devices_iot: int = 1


def _reason(p: Product, prof: Profile) -> tuple[str, dict] | None:
    if prof.city_tier not in p.tiers:
        return ("tier", {"tier": prof.city_tier, "tiers": p.tiers})
    if p.requires_gstin and prof.has_gstin is not True:
        return ("gstin", {})
    if (prof.employees or 0) < p.min_employees:
        return ("employees", {"min": p.min_employees})
    if (prof.locations or 1) < p.min_sites:
        return ("sites", {"min": p.min_sites})
    return None


def eligible(pid: str, prof: Profile) -> tuple[bool, tuple[str, dict] | None]:
    r = _reason(catalogue()[pid], prof)
    return r is None, r


REASON_TEXT = {
    "en": {"tier": "not available in Tier {tier} cities", "gstin": "needs a GSTIN",
           "employees": "needs at least {min} staff", "sites": "needs at least {min} locations"},
    "hi": {"tier": "टियर {tier} शहरों में उपलब्ध नहीं", "gstin": "इसके लिए GSTIN ज़रूरी है",
           "employees": "कम से कम {min} कर्मचारी चाहिए", "sites": "कम से कम {min} लोकेशन चाहिए"},
    "hinglish": {"tier": "Tier {tier} cities mein available nahi", "gstin": "iske liye GSTIN zaroori hai",
                 "employees": "kam se kam {min} staff chahiye", "sites": "kam se kam {min} locations chahiye"},
}


def reason_text(reason: tuple[str, dict], lang: str = "en") -> str:
    return REASON_TEXT.get(lang, REASON_TEXT["en"])[reason[0]].format(**reason[1])


@dataclass
class Recommendation:
    items: dict[str, int] = field(default_factory=dict)
    quote: Quote | None = None
    why: dict[str, str] = field(default_factory=dict)        # pid -> need that pulled it in
    auto_added: dict[str, str] = field(default_factory=dict) # dependency pid -> dependent pid
    excluded: list[tuple[str, tuple[str, dict]]] = field(default_factory=list)
    alternative: dict[str, int] | None = None
    alt_quote: Quote | None = None
    alt_kind: str | None = None
    handoff: str | None = None
    serviceable: bool = True


def _qty(pid: str, prof: Profile) -> int:
    sites, staff = max(prof.locations or 1, 1), max(prof.employees or 1, 1)
    p = catalogue()[pid]
    if pid in ("P07", "P08"): return max(prof.sim_lines, 1)
    if pid == "P23": return max(prof.cameras, 1) * sites
    if pid == "P25": return max(prof.vehicles, 1)
    if pid == "P24": return max(prof.devices_iot, 1)
    if pid in ("P16", "P20"): return staff
    return sites if p.unit == "per site" else 1


def _base_link(prof: Profile, needs: set[str]) -> tuple[str | None, list]:
    """Smallest eligible link for the stated needs. Returns (product, exclusions)."""
    exc = []
    def ok(pid):
        good, r = eligible(pid, prof)
        if not good: exc.append((pid, r))
        return good
    if "dedicated_bandwidth" in needs:
        if (prof.employees or 0) >= 25 and "high_speed" in needs and ok("P06"): return "P06", exc
        if ok("P05"): return "P05", exc
    if "high_speed" in needs and ok("P03"):
        return "P03", exc
    fibre_needed = bool({NEED_PRODUCT[n] for n in needs if n in NEED_PRODUCT} & FIBRE_ONLY)
    large = (prof.employees or 1) >= 10 or (prof.locations or 1) >= 3
    if large and ok("P02"): return "P02", exc
    if prof.business_type in MICRO and (prof.locations or 1) == 1 and not fibre_needed and ok("P04"):
        return "P04", exc  # cheapest eligible link for price-sensitive single-site micro businesses
    if ok("P01"): return "P01", exc
    return None, exc


def recommend(prof: Profile) -> Recommendation:
    rec, cat = Recommendation(), catalogue()
    needs = set(prof.needs)
    if prof.city_tier is not None and all(prof.city_tier not in p.tiers for p in cat.values()):
        rec.serviceable, rec.handoff = False, "tier_not_served"
        rec.excluded = [(p, ("tier", {"tier": prof.city_tier, "tiers": cat[p].tiers})) for p in ("P01", "P04", "P07")]
        return rec
    # Clinics and offices hold client data: email on a professional office includes endpoint security.
    if "cloud_email" in needs and prof.business_type in PROFESSIONAL:
        needs.add("security")
    items: dict[str, int] = {}
    wanted = [n for n in prof.needs if n in NEED_PRODUCT] + [n for n in needs - set(prof.needs) if n in NEED_PRODUCT]
    for n in wanted:
        pid = NEED_PRODUCT[n]
        good, r = eligible(pid, prof)
        if good:
            items[pid] = _qty(pid, prof); rec.why.setdefault(pid, n)
        else:
            rec.excluded.append((pid, r))
    has_link = bool(EXISTING_LINK & set(prof.current_setup))
    wants_link = needs & {"internet", "internet_for_upi_pos", "uptime", "failover", "dedicated_bandwidth", "high_speed", "sdwan"}
    implied = (needs - STANDALONE - wants_link) and not has_link
    deps = [p for p in items if cat[p].requires_one_of]
    if wants_link or implied or deps:
        link, exc = _base_link(prof, needs)
        rec.excluded += [e for e in exc if e[0] not in {x[0] for x in rec.excluded}]
        if link:
            items = {link: _qty(link, prof), **items}
            rec.why[link] = next((n for n in ("dedicated_bandwidth", "high_speed", "internet_for_upi_pos") if n in needs), "internet")
            if not wants_link and deps:
                rec.auto_added[link] = deps[0]
    rec.items = enforce_dependencies(items, prof)[0]
    if not rec.items and needs:
        rec.handoff = "no_eligible"
    if rec.items:
        rec.quote = price(rec.items)
        _alternative(rec, prof, needs)
    if (prof.employees or 0) >= LARGE_STAFF or (prof.locations or 0) >= LARGE_SITES:
        rec.handoff = rec.handoff or "large_account"
    if (prof.locations or 1) >= 2:
        rec.handoff = rec.handoff or "multi_site"
    unmet = {x[0] for x in rec.excluded} & {"P05", "P06", "P24", "P10"}
    if prof.business_type == "manufacturer" and unmet:
        rec.handoff = rec.handoff or "manufacturer_custom"
    if "dedicated_bandwidth" in needs and not ({"P05", "P06"} & set(rec.items)):
        rec.handoff = rec.handoff or "manufacturer_custom"
    return rec


def enforce_dependencies(items: dict[str, int], prof: Profile) -> tuple[dict[str, int], dict[str, str]]:
    """Add the cheapest eligible product satisfying each requires_one_of. Returns (items, added -> dependent)."""
    cat, out, added = catalogue(), dict(items), {}
    for pid in list(out):
        req = cat[pid].requires_one_of
        if req and not set(req) & set(out):
            options = sorted((r for r in req if eligible(r, prof)[0]), key=lambda r: cat[r].monthly)
            if options:
                out[options[0]] = _qty(options[0], prof); added[options[0]] = pid
            else:
                del out[pid]
    return out, added


def _alternative(rec: Recommendation, prof: Profile, needs: set[str]) -> None:
    cat, base = catalogue(), rec.items
    swap = {"P02": "P01", "P01": "P04", "P03": "P02", "P06": "P05"}
    for old, new in swap.items():
        if old in base and eligible(new, prof)[0]:
            alt = {(new if k == old else k): v for k, v in base.items()}
            if all(not cat[k].requires_one_of or set(cat[k].requires_one_of) & set(alt) for k in alt):
                rec.alternative, rec.alt_quote, rec.alt_kind = alt, price(alt), "smaller_link"
                return
    if set(base) == {"P04"} and base["P04"] == 1:
        alt = {"P07": 1}
        rec.alternative, rec.alt_quote, rec.alt_kind = alt, price(alt), "mobile_only"
    elif set(base) == {"P08"}:
        rec.alternative, rec.alt_quote, rec.alt_kind = {"P07": base["P08"]}, price({"P07": base["P08"]}), "smaller_link"


def apply_addons(prof: Profile, base: dict[str, int], selected: set[str]) -> dict:
    """Toggle add-ons on the quote screen. Returns final items, dependency notes, blocked reasons."""
    cat, items, blocked = catalogue(), dict(base), {}
    for pid in selected:
        good, r = eligible(pid, prof)
        if good: items.setdefault(pid, _qty(pid, prof))
        else: blocked[pid] = r
    items, added = enforce_dependencies(items, prof)
    # A fibre-only add-on replaces AirFiber instead of billing two connections for one site.
    if "P04" in items and set(added) & {"P01", "P02", "P03", "P05", "P06"}:
        del items["P04"]
    return {"items": items, "added": added, "blocked": blocked}
