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
