import pytest
from src.calculator import add, subtract, percentage

def test_add_positive_numbers(): assert add(2, 3) == 5
def test_subtract_numbers(): assert subtract(8, 3) == 5
def test_percentage(): assert percentage(25, 100) == 25

def test_percentage_zero_total_raises():
    with pytest.raises(ValueError): percentage(10, 0)
