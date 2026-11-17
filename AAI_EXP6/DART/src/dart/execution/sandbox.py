"""Execution policy helpers. This module is not a hardened sandbox."""
from pathlib import Path

def repository_is_under_allowed_root(repository: str, allowed_roots: list[str]) -> bool:
    target = Path(repository).expanduser().resolve()
    for root in allowed_roots:
        try: target.relative_to(Path(root).expanduser().resolve()); return True
        except ValueError: continue
    return False
