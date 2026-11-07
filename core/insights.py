"""What smb_leads.csv says about businesses like this one: past activation times, what peers chose, churn drivers,
which sales channel pays off, and payback. Plain csv, so the web front end needs no pandas. Every figure carries the
number of past customers behind it, and none of it changes a plan or a price."""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from functools import lru_cache
from statistics import median, quantiles
from .catalogue import DATA

MICRO_SEG, PRO_SEG, MULTI_SEG, MFG_SEG = "Micro retail & services", "Professional offices", "Small multi-site businesses", "Small manufacturers"
MICRO_KINDS = {"kirana", "salon", "pharmacy", "retailer", "bakery", "shop", "restaurant"}
PRO_KINDS = {"clinic", "ca_firm", "coaching", "law", "office"}
MIN_GROUP = 30  # below this, a narrower group is too small to quote


@lru_cache(maxsize=1)
def leads() -> tuple[dict, ...]:
    with open(DATA / "smb_leads.csv", newline="", encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


def activated() -> list[dict]:
    return [r for r in leads() if r["outcome"] == "Activated"]


def segment_of(business_type: str | None, locations: int | None = 1) -> str | None:
    """Our advisor's business types, in the data's segments."""
    if (locations or 1) > 1: return MULTI_SEG
    if business_type == "manufacturer": return MFG_SEG
    if business_type in PRO_KINDS: return PRO_SEG
    if business_type in MICRO_KINDS: return MICRO_SEG
    return None


def _q(values: list[float]) -> tuple[int, int]:
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    return round(q1), round(q3)


def activation_days(segment: str | None, tier: int | None) -> dict | None:
    """The middle half of past lead-to-activation times for businesses like this one, narrowest group with enough data."""
    rows = activated()
    for group in ([r for r in rows if r["segment"] == segment and r["city_tier"] == str(tier)], [r for r in rows if r["segment"] == segment], [r for r in rows if r["city_tier"] == str(tier)]):
        if len(group) >= MIN_GROUP:
            low, high = _q([float(r["days_lead_to_activation"]) for r in group])
            return {"low": low, "high": high, "n": len(group)}
    return None


def peer_share(segment: str | None, product_id: str) -> dict | None:
    """How many activated businesses in this segment had this product. Only ever shown for products already in the plan."""
    group = [r for r in activated() if r["segment"] == segment]
    if len(group) < MIN_GROUP: return None
    has = sum(any(p.split("x")[0] == product_id for p in r["bundle_products"].split(";")) for r in group)
    return {"share": has / len(group), "n": len(group)}


# ---- Churn -------------------------------------------------------------------------------------------------------
def _calls_bucket(calls: int) -> str:
    return "0-1" if calls <= 1 else "2-3" if calls <= 3 else "4" if calls == 4 else "5+"


@lru_cache(maxsize=1)
def churn_table() -> dict:
    rows = activated()
    rate = lambda g: sum(r["churned_within_6_months"] == "Y" for r in g) / len(g) if g else 0.0
    by = lambda key: {k: (rate(g), len(g)) for k, g in _group(rows, key).items()}
    return {"base": (rate(rows), len(rows)), "segment": by(lambda r: r["segment"]), "calls": by(lambda r: _calls_bucket(int(r["customer_follow_up_calls"]))), "gstin": by(lambda r: r["has_gstin"])}


def _group(rows, key) -> dict:
    out = defaultdict(list)
    for r in rows: out[key(r)].append(r)
    return out


def churn_risk(segment: str | None, has_gstin: bool | None, chases: int) -> dict:
    """A rough 6-month churn risk: the segment's rate, scaled by how much the owner has had to chase us.
    The data's strongest driver is follow-up calls (5.9% at 0-1 calls, 27.9% at 5 or more); days to activate has no effect."""
    t = churn_table()
    base = t["base"][0]
    rate = t["segment"].get(segment, t["base"])[0]
    reasons = [f"{segment or 'All customers'}: {rate:.0%} of past customers left within 6 months"]
    bucket = _calls_bucket(chases)
    lift = t["calls"][bucket][0] / base
    if chases >= 2:
        reasons.append(f"Had to chase us {chases} times: customers with {bucket} follow-up calls left at {t['calls'][bucket][0]:.0%}")
    rate *= lift
    if has_gstin is False:
        g = t["gstin"]["N"]
        rate *= g[0] / base
        reasons.append(f"No GSTIN: {g[0]:.0%} left, but from only {g[1]} customers")
    rate = min(rate, 0.95)
    return {"rate": rate, "level": "high" if rate >= 0.25 else "medium" if rate >= 0.15 else "low", "reasons": reasons}


# ---- Channels and payback ------------------------------------------------------------------------------------------
SURVEY_REASONS = {"multi_site", "manufacturer_custom", "large_account", "needs_scoping"}


@lru_cache(maxsize=1)
def channel_costs() -> dict:
    """Spend per activation for each segment and lead source: average acquisition cost divided by activation rate."""
    out = {}
    for (seg, src), g in _group(leads(), lambda r: (r["segment"], r["lead_source"])).items():
        act = sum(r["outcome"] == "Activated" for r in g) / len(g)
        cac = sum(float(r["acquisition_cost_inr"]) for r in g) / len(g)
        out[(seg, src)] = {"per_activation": cac / act if act else None, "rate": act, "n": len(g)}
    return out


def route(segment: str | None, reason: str | None = None) -> dict:
    """Field visit or phone and app. A visit only where the case needs a site survey: elsewhere it costs several times as much per activation."""
    cc = channel_costs()
    field, remote = cc.get((segment, "Field sales"), {}).get("per_activation"), cc.get((segment, "Inbound call"), {}).get("per_activation")
    costs = f"₹{field:,.0f} per activation from field visits vs ₹{remote:,.0f} from calls" if field and remote else "no cost data for this segment"
    if reason in SURVEY_REASONS: return {"route": "Field visit", "why": f"Needs a site survey. ({costs})"}
    return {"route": "Phone and app", "why": costs}


@lru_cache(maxsize=1)
def payback_base() -> dict:
    """Per segment: total acquisition spend per activation, average monthly bundle value, and 6-month churn. The deck's
    "8 months to pay back a micro customer" is spend ÷ value here (₹20,007 ÷ ₹2,505)."""
    out = {}
    for seg, g in _group(leads(), lambda r: r["segment"]).items():
        act = [r for r in g if r["outcome"] == "Activated"]
        out[seg] = {"spend": sum(float(r["acquisition_cost_inr"]) for r in g) / len(act), "value": sum(float(r["monthly_bundle_value_inr"]) for r in act) / len(act),
                    "churn": sum(r["churned_within_6_months"] == "Y" for r in act) / len(act), "remote": channel_costs()[(seg, "Inbound call")]["per_activation"], "n": len(act)}
    return out


def what_if(segment: str, digital_share: float = 0.0, price_change: float = 0.0, churn_change: float = 0.0) -> dict:
    """Payback if a share of sales moves from today's mix to the phone-and-app cost, prices move, or churn moves.
    Assumptions, stated so they can be argued with: no change in demand from a price change, and a customer who leaves
    in the first 6 months leaves at month 3 on average."""
    b = payback_base()[segment]
    spend = (1 - digital_share) * b["spend"] + digital_share * b["remote"]
    value = b["value"] * (1 + price_change)
    churn = min(max(b["churn"] + churn_change, 0.0), 1.0)
    first_year = value * (12 - churn * 9)
    return {"spend": spend, "value": value, "churn": churn, "payback_months": spend / value, "first_year": first_year, "return": first_year / spend}


def peers_common(segment: str | None, top: int = 3) -> list[tuple[str, float]]:
    group = [r for r in activated() if r["segment"] == segment]
    if len(group) < MIN_GROUP: return []
    c = Counter(p.split("x")[0] for r in group for p in r["bundle_products"].split(";"))
    return [(pid, n / len(group)) for pid, n in c.most_common(top)]
