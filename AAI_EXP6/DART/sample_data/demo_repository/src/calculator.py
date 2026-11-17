def add(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b

def subtract(a: float, b: float) -> float:
    """Return the difference between two numbers."""
    return a - b

def percentage(value: float, total: float) -> float:
    """Return value as a percentage of total."""
    if total == 0:
        raise ValueError("total must not be zero")
    return value / total * 100
