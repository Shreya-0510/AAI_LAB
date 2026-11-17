from src.calculator import percentage

def subtotal(prices: list[float]) -> float:
    return sum(prices)

def tax_amount(prices: list[float], tax_rate: float) -> float:
    return subtotal(prices) * tax_rate / 100

def tax_share_of_total(prices: list[float], tax_rate: float) -> float:
    total = subtotal(prices) + tax_amount(prices, tax_rate)
    return percentage(tax_amount(prices, tax_rate), total)
