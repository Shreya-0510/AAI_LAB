from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

def run_independent_tasks(tasks: dict[str, Callable[[], object]], max_workers: int = 3) -> dict[str, object]:
    """Run independent read-only analysis tasks concurrently; preserve per-task errors."""
    results: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks) or 1))) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try: results[name] = future.result()
            except Exception as exc: results[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return results
