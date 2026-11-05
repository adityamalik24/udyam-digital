import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from datetime import date
import pytest
from core.pricing import price

def test_bundle():
    q = price({"P01": 1, "P16": 6, "P20": 6})
    assert q.monthly == 1099 + 6*138 + 6*124 and q.setup == 0 and q.contract == 12
    assert q.valid_until == date(2026, 7, 30)

def test_setup_and_contract_take_max():
    q = price({"P05": 1, "P24": 2})
    assert q.setup == 10000 + 6000 and q.contract == 24 and q.install_days == 21

@pytest.mark.parametrize("bad", [{"P99": 1}, {"P01": 0}, {"P01": -2}])
def test_rejects_bad(bad):
    with pytest.raises(ValueError): price(bad)


def test_first_payment_total_and_summary():
    from core.pricing import first_payment, contract_total, summary_text
    q = price({"P23": 2, "P01": 1})
    assert first_payment(q) == q.monthly + q.setup == 1597 + 3600
    assert contract_total(q) == q.monthly * 12 + q.setup
    text = summary_text(q, {"P01": "fibre"})
    assert "Rs 1,597 per month" in text and "P01" not in text and "P23" not in text
