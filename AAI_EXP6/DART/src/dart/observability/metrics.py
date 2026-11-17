from __future__ import annotations
import time
from contextlib import contextmanager

@contextmanager
def timed():
    start = time.perf_counter()
    result = {"duration_seconds": 0.0}
    try: yield result
    finally: result["duration_seconds"] = round(time.perf_counter() - start, 6)
