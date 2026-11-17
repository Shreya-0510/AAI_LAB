import pytest
from src.receipt import subtotal, tax_amount, tax_share_of_total

def test_subtotal(): assert subtotal([2.0, 3.0]) == 5.0
def test_tax_amount(): assert tax_amount([10.0], 10) == 1.0
def test_tax_share_is_below_tax_rate(): assert 0 < tax_share_of_total([100.0], 10) < 10

def test_zero_tax_rate(): assert tax_amount([10.0], 0) == 0
