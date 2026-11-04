"""Typed access to product_catalogue.csv. Column names per data/README.md."""
from __future__ import annotations
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Product:
    id: str
    category: str
    name: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup: int
    contract: int
    tiers: tuple[int, ...]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: tuple[str, ...]
    install_days: int

    @property
    def monthly(self) -> int:
        """Single list price: range midpoint. Activated leads in smb_leads.csv sit
        at 0.48 of the range on average, with no difference by tier or segment."""
        return int((self.price_min + self.price_max) / 2 + 0.5)


@lru_cache
def catalogue() -> dict[str, Product]:
    out = {}
    with open(DATA / "product_catalogue.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["product_id"]] = Product(
                id=r["product_id"], category=r["category"], name=r["product_name"],
                description=r["description"], unit=r["unit"],
                price_min=int(r["price_min_inr_per_month"]), price_max=int(r["price_max_inr_per_month"]),
                setup=int(r["one_time_setup_inr"]), contract=int(r["min_contract_months"]),
                tiers=tuple(int(t) for t in r["available_city_tiers"].split(";")),
                min_employees=int(r["min_employees"]), min_sites=int(r["min_sites"]),
                requires_gstin=r["requires_gstin"] == "Y",
                requires_one_of=tuple(x for x in r["requires_one_of"].split("|") if x),
                install_days=int(r["typical_install_days"]),
            )
    return out
