"""Server-side price calculation. The only source of rupee amounts in the product."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from .catalogue import catalogue

TODAY = date(2026, 7, 15)  # fixed by data/README.md for all date-based checks
QUOTE_VALID_DAYS = 15


@dataclass(frozen=True)
class Line:
    product_id: str
    name: str
    qty: int
    unit: str
    unit_price: int
    monthly: int
    setup: int
    contract: int
    install_days: int


@dataclass(frozen=True)
class Quote:
    lines: tuple[Line, ...]
    monthly: int
    setup: int
    contract: int
    valid_until: date
    install_days: int


def first_payment(q: Quote) -> int:
    """First month plus one-time setup."""
    return q.monthly + q.setup


def contract_total(q: Quote) -> int:
    """Everything paid over the minimum contract, if the bundle stays as it is."""
    return q.monthly * q.contract + q.setup


def summary_text(q: Quote, descriptions: dict[str, str]) -> str:
    """Plain summary the owner can keep or share. Plain names and no product codes."""
    out = ["Accel Business quote", "", f"Rs {q.monthly:,} per month", f"One-time setup: Rs {q.setup:,}", f"Minimum contract: {q.contract} months",
           f"First payment (first month + setup): Rs {first_payment(q):,}", f"Total over {q.contract} months: Rs {contract_total(q):,}",
           f"Quote valid until: {q.valid_until:%d %b %Y}", f"Usual time to install: about {q.install_days} days (estimate; the real date appears in your tracker)", "", "What's included:"]
    for l in q.lines:
        out.append(f"- {l.name}" + (f" x {l.qty}" if l.qty > 1 else "") + f": Rs {l.monthly:,} per month. {descriptions.get(l.product_id, '')}")
    return "\n".join(out + ["", "Demo quote. All data is synthetic and Accel Telecom is fictional."]) + "\n"


def price(items: dict[str, int], today: date = TODAY) -> Quote:
    """items: product_id -> quantity. Unknown ids and non-positive quantities raise."""
    cat, lines = catalogue(), []
    for pid, qty in items.items():
        if pid not in cat:
            raise ValueError(f"unknown product {pid}")
        if not isinstance(qty, int) or qty < 1:
            raise ValueError(f"bad quantity for {pid}: {qty}")
        p = cat[pid]
        lines.append(Line(pid, p.name, qty, p.unit, p.monthly, p.monthly * qty, p.setup * qty, p.contract, p.install_days))
    return Quote(tuple(lines), sum(l.monthly for l in lines), sum(l.setup for l in lines),
                 max((l.contract for l in lines), default=0), today + timedelta(days=QUOTE_VALID_DAYS),
                 max((l.install_days for l in lines), default=0))
