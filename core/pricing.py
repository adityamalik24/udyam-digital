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
