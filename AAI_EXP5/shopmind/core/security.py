"""Prompt-injection detection and sanitisation (user input AND tool/product text)."""
import re

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override|bypass)\b[^.]{0,40}\b(budget|requirements?|instructions?|constraints?|rules?|limits?|previous|prior|above)\b",
    r"\bignore\b[^.]{0,20}\b(all|everything)\b",
    r"\byou are now\b", r"\bsystem prompt\b", r"\bnew instructions?\b", r"\bpretend\b",
    r"\b(recommend|rank|pick|choose|select)\b[^.]{0,25}\b(most expensive|this product first|first)\b",
    r"\breveal\b[^.]{0,20}\b(prompt|key|secret)\b",
]
_COMPILED = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def find_injection(text: str):
    """Return the earliest regex match for an injection attempt, or None."""
    hits = [m for rx in _COMPILED if (m := rx.search(text))]
    return min(hits, key=lambda m: m.start()) if hits else None


def sanitize_query(query: str):
    """Cut injected tails from each sentence. Returns (clean_query, events)."""
    events, clean = [], []
    for sent in re.split(r"(?<=[.;!\n])\s+", query):
        m = find_injection(sent)
        if m:
            events.append({"kind": "prompt_injection", "detail": f"Removed: “{sent[m.start():].strip()[:90]}”", "blocked": True})
            sent = sent[:m.start()]
        if sent.strip(" ,.;"):
            clean.append(sent)
    return " ".join(clean), events


def is_suspicious_product_text(text: str) -> bool:
    return find_injection(text) is not None
