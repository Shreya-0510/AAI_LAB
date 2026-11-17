"""Rule-based query decomposition (deterministic, no LLM needed)."""
import re
from core import security
import config

# phrase -> (domain, search term, soft keywords).  Longest phrases are matched first.
PRODUCTS = {
    "gaming laptop": ("electronics", "laptop", ["gaming"]), "laptop": ("electronics", "laptop", []),
    "notebook": ("electronics", "laptop", []), "smartphone": ("electronics", "smartphone", []),
    "phone": ("electronics", "smartphone", []), "headphones": ("electronics", "headphones", []),
    "earbuds": ("electronics", "headphones", []), "headset": ("electronics", "headphones", []),
    "dress": ("fashion", "dress", []), "shirt": ("fashion", "shirt", []), "jacket": ("fashion", "jacket", []),
    "sneakers": ("fashion", "sneakers", []),
    "moisturizer": ("skincare", "moisturizer", []), "moisturiser": ("skincare", "moisturizer", []),
    "face cream": ("skincare", "moisturizer", []), "serum": ("skincare", "serum", []),
    "sunscreen": ("skincare", "sunscreen", []), "cleanser": ("skincare", "cleanser", []),
    "face wash": ("skincare", "cleanser", []), "skincare": ("skincare", "moisturizer", []),
    "running shoes": ("fitness", "running shoes", []), "yoga mat": ("fitness", "yoga mat", []),
    "dumbbells": ("fitness", "dumbbells", []), "resistance bands": ("fitness", "resistance bands", []),
    "fitness tracker": ("fitness", "fitness tracker", []),
    "carry-on suitcase": ("travel", "carry-on suitcase", []), "carry on": ("travel", "carry-on suitcase", []),
    "suitcase": ("travel", "carry-on suitcase", []), "luggage": ("travel", "carry-on suitcase", []),
    "backpack": ("travel", "backpack", []), "travel pillow": ("travel", "travel pillow", []),
    "packing cubes": ("travel", "packing cubes", []), "duffel bag": ("travel", "duffel bag", []),
}
KNOWN_BRANDS = ["lenovo", "asus", "acer", "hp", "dell", "msi", "apple", "sony", "bose", "jbl", "sennheiser", "anker",
                "samsung", "google", "oneplus", "motorola", "zara", "h&m", "uniqlo", "mango", "levis", "nike",
                "cerave", "neutrogena", "the ordinary", "la roche-posay", "cetaphil", "olay", "adidas", "decathlon",
                "puma", "fitbit", "asics", "samsonite", "american tourister", "away", "wildcraft", "osprey", "tumi"]
FREE_FLAGS = ["fragrance", "paraben", "sulfate", "alcohol", "silicone"]
INGREDIENTS = ["niacinamide", "hyaluronic acid", "ceramides", "retinol", "salicylic acid", "vitamin c"]
SOFT_WORDS = ["wireless", "noise cancelling", "waterproof", "lightweight", "formal", "semi-formal", "casual", "gaming",
              "black", "white", "navy", "red", "beige", "cotton", "linen", "wool", "hardshell", "durable", "breathable"]
NEG = r"(?:no|not|without|avoid|exclude|except|don'?t want|do not want|dont want|never)"


def _num(s: str, suffix: str = "") -> float:
    v = float(s)
    return v * 1000 if suffix == "k" else v * 100000 if suffix == "lakh" else v


def parse_clause(clause: str, inr: bool) -> dict:
    t = clause.lower()
    c = {}
    m = re.search(r"(?:under|below|less than|within|upto|up to|max(?:imum)?|budget(?: of)?|<=?|around|about)\s*"
                  r"(?:rs\.?|inr|₹|\$|usd)?\s*([\d.]+)\s*(k|lakh)?\b", t) \
        or re.search(r"(?:₹|rs\.?\s*|\$)\s*([\d.]+)\s*(k|lakh)?", t)
    if m:
        try:
            val = _num(m.group(1).rstrip("."), m.group(2) or "")
            if val >= 5:
                c["max_price"] = round(val / config.INR_PER_USD, 2) if inr else val
                c["budget_display"] = f"{'₹' if inr else '$'}{val:,.0f}"
        except ValueError:
            pass
    m = re.search(r"(?:rating|rated|stars?)\s*(?:of\s*)?(?:above|over|at least|>=?|≥|min(?:imum)?)?\s*(\d(?:\.\d)?)", t) \
        or re.search(r"(?:above|over|at least|>=?|≥)\s*(\d(?:\.\d)?)\s*(?:\+\s*)?(?:stars?|rating)", t) \
        or re.search(r"(\d(?:\.\d)?)\s*\+?\s*(?:stars?|rating)", t)
    if m and 1 <= float(m.group(1)) <= 5:
        c["min_rating"] = float(m.group(1))
    m = re.search(r"(\d+)\s*gb\s*(?:of\s*)?(?:ram|memory)", t) or re.search(r"(?:ram|memory)\s*(?:of\s*)?(\d+)\s*gb", t)
    if m: c["min_ram"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(gb|tb)\s*(?:ssd|storage|hdd|nvme)", t) or re.search(r"(?:storage|ssd)\s*(?:of\s*)?(\d+)\s*(gb|tb)", t)
    if m: c["min_storage"] = int(m.group(1)) * (1024 if m.group(2) == "tb" else 1)
    flags, soft, must = [], [], []
    for f in FREE_FLAGS:
        if re.search(rf"{f}s?[\s-]*free|{NEG}\s+(?:\w+\s+)?{f}s?\b", t):
            flags.append(f"{f}-free")
    for ing in INGREDIENTS:
        if ing in t and not re.search(rf"{NEG}\s+(?:\w+\s+)?{ing}", t):
            must.append(ing)
    soft += [w for w in SOFT_WORDS if w.replace("-", " ") in t.replace("-", " ")]
    if re.search(r"\b(ml|machine learning|deep learning|ai|data science)\b", t): soft += ["nvidia", "ml"]
    if re.search(r"nvidia|rtx|gtx", t): soft.append("nvidia")
    if "battery" in t: soft.append("battery")
    excl = []
    for m in re.finditer(NEG + r"\s+([\w&\- ]{2,40})", t):
        for b in KNOWN_BRANDS:
            if re.search(rf"\b{re.escape(b)}\b", m.group(1)):
                excl.append(b)
    c["required_flags"], c["must_contain"] = sorted(set(flags)), sorted(set(must))
    c["soft_keywords"], c["exclude_brands"] = sorted(set(soft)), sorted(set(excl))
    return c


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, list):
            out[k] = sorted(set(out.get(k, []) + v))
        else:
            out.setdefault(k, v)
    return out


def parse_query(query: str) -> dict:
    clean, events = security.sanitize_query(query)
    clean = re.sub(r"(?<=\d),(?=\d)", "", clean)
    inr = bool(re.search(r"₹|\brs\b\.?|\binr\b|rupee|lakh", clean, re.I))
    clauses = [c.strip() for c in re.split(r"[;\n]|,|\.\s|\band\b|\bplus\b|\+", clean) if c.strip()]
    phrases = sorted(PRODUCTS, key=len, reverse=True)
    tasks = []
    for cl in clauses:
        low = cl.lower().replace("’", "'")
        hit = next((p for p in phrases if re.search(rf"\b{re.escape(p)}s?\b", low)), None)
        c = parse_clause(cl, inr)
        if hit:
            domain, term, soft = PRODUCTS[hit]
            c["soft_keywords"] = sorted(set(c.get("soft_keywords", []) + soft))
            tasks.append({"id": f"T{len(tasks) + 1}", "domain": domain, "term": term, "label": term.title(),
                          "constraints": c, "source_text": cl})
        elif tasks:     # constraint-only clause -> attach to previous task
            tasks[-1]["constraints"] = _merge(tasks[-1]["constraints"], c)
            tasks[-1]["source_text"] += " + " + cl
    return {"tasks": tasks, "security_events": events, "currency": "INR" if inr else "USD", "clean_query": clean}
