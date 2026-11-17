"""MCP-style tool registry (registration, discovery, least-privilege authorisation) + tool implementations."""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import config
from core import nlp, providers, security
from core.models import PermissionDenied, Product


# ───────────────────────── run context ─────────────────────────
@dataclass
class RunConfig:
    mode: str = "parallel"            # parallel | sequential
    use_cache: bool = True
    latency_scale: float = 1.0        # scales simulated latency of the offline catalog
    faults: dict = field(default_factory=dict)   # {"bestbuy": "timeout" | "rate_limit" | "down"}
    max_retries: int = 2
    weights: dict = field(default_factory=lambda: dict(config.DEFAULT_WEIGHTS))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    stats: Counter = field(default_factory=Counter, repr=False)

    def bump(self, key: str, n: int = 1):
        with self._lock:
            self.stats[key] += n


# ───────────────────────── registry ─────────────────────────
@dataclass
class Tool:
    name: str
    fn: Callable
    description: str
    roles: set
    live: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name, fn, description, roles, live=False):
        self._tools[name] = Tool(name, fn, description, set(roles), live)

    def discover(self, role: str | None = None) -> list[dict]:
        return [{"tool": t.name, "description": t.description, "allowed_roles": sorted(t.roles), "live_api": t.live}
                for t in self._tools.values() if role is None or role in t.roles]

    def call(self, role: str, name: str, ctx: RunConfig, state, **kw):
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool {name}")
        if role not in tool.roles:
            state.security_event("unauthorized_tool_access", f"{role} → {name}", blocked=True)
            raise PermissionDenied(f"Role '{role}' is not authorised to call '{name}'")
        state.count("tool_calls")
        return tool.fn(ctx=ctx, state=state, **kw)


# ───────────────────────── tool implementations ─────────────────────────
def t_parse_query(ctx, state, query):
    return nlp.parse_query(query)


def t_route(ctx, state, tasks):
    """Dependency-aware routing: searches are independent (parallel group); everything after is sequential."""
    subs = []
    for t in tasks:
        chain = config.DOMAIN_PROVIDERS[t["domain"]]
        subs += [
            {"id": f"{t['id']}:live", "task_id": t["id"], "kind": "live", "chain": chain, "label": f"{t['label']} · live API"},
            {"id": f"{t['id']}:catalog", "task_id": t["id"], "kind": "catalog", "chain": ["demo"], "label": f"{t['label']} · catalog"},
            {"id": f"{t['id']}:reviews", "task_id": t["id"], "kind": "reviews", "chain": ["demo"], "label": f"{t['label']} · reviews"},
        ]
    return {"parallel_group": [s["id"] for s in subs], "subtasks": subs,
            "sequence": ["synchronizer", "filter", "comparison", "ranking", "validator", "supervisor", "human"],
            "dependencies": {"synchronizer": [s["id"] for s in subs], "filter": ["synchronizer"],
                             "comparison": ["filter"], "ranking": ["comparison"], "validator": ["ranking"]}}


def _search(provider_fn):
    def run(ctx, state, task):
        return provider_fn(ctx, task)
    return run


def _sanitize_product(p: Product, state) -> Product:
    if security.is_suspicious_product_text(p.description + " " + p.name):
        p.flags.append("injection")
        state.security_event("indirect_prompt_injection", f"Product '{p.name}' contains instruction-like text", blocked=True)
    return p


def t_merge(ctx, state, results: dict, tasks: list):
    """Synchronise parallel search outputs: dedupe, resolve rating conflicts by source trust."""
    merged, conflicts = {}, []
    for t in tasks:
        by_uid: dict[str, list[Product]] = {}
        for sub_id, prods in results.items():
            if sub_id.startswith(t["id"] + ":"):
                for p in prods:
                    by_uid.setdefault(p.uid, []).append(p)
        rows, seen_names = [], set()
        for uid, versions in by_uid.items():
            versions.sort(key=lambda p: -config.SOURCE_TRUST.get(p.source, 0))
            base = versions[0]
            ratings = {v.source: v.rating for v in versions if v.rating is not None}
            base.rating_sources = ratings
            if len(set(ratings.values())) > 1 and max(ratings.values()) - min(ratings.values()) > 0.2:
                conflicts.append({"task": t["id"], "product": base.name, "values": ratings, "resolved_rating": base.rating,
                                  "winner": base.source, "rule": "trusted-source priority",
                                  "needs_human": max(ratings.values()) - min(ratings.values()) >= 0.5})
            for v in versions[1:]:
                base.num_reviews = max(base.num_reviews, v.num_reviews) if v.source == "demo_reviews" else base.num_reviews
            key = (re.sub(r"\W+", "", base.name.lower()), base.brand.lower())
            if key in seen_names:
                continue
            seen_names.add(key)
            rows.append(_sanitize_product(base, state))
        merged[t["id"]] = rows
    return merged, conflicts


def violations(p: Product, c: dict) -> tuple[list[str], list[str]]:
    """Returns (hard_violations, unverified_notes) for one product vs one task's constraints."""
    bad, unk = [], []
    if "injection" in p.flags: bad.append("contains prompt-injection text")
    if not p.available: bad.append("unavailable")
    if c.get("max_price") and p.price > c["max_price"]: bad.append(f"over budget (${p.price:.0f} > ${c['max_price']:.0f})")
    if c.get("min_rating"):
        if p.rating is None: unk.append("rating-unverified")
        elif p.rating < c["min_rating"]: bad.append(f"rating {p.rating} < {c['min_rating']}")
    for key, label in (("min_ram", "ram"), ("min_storage", "storage")):
        if c.get(key):
            v = p.specs.get(label)
            if v is None: unk.append(f"{label}-unverified")
            elif v < c[key]: bad.append(f"{label} {v} < {c[key]}")
    if any(b in p.brand.lower() or b in p.name.lower() for b in c.get("exclude_brands", [])): bad.append("excluded brand")
    text = p.text()
    for f in c.get("required_flags", []):
        if f.replace("-", " ") not in text: bad.append(f"not {f}")
    for m in c.get("must_contain", []):
        if m not in text: bad.append(f"missing {m}")
    return bad, unk


def t_filter(ctx, state, task, products):
    kept, rejected = [], []
    for p in products:
        bad, unk = violations(p, task["constraints"])
        if bad: rejected.append({"product": p.name, "brand": p.brand, "price": p.price, "reasons": "; ".join(bad)})
        else:
            p.flags += [u for u in unk if u not in p.flags]
            kept.append(p)
    return kept, rejected


def t_compare(ctx, state, task, products):
    if not products:
        return {"rows": [], "best": {}}
    rows = []
    for p in products:
        rows.append({"uid": p.uid, "name": p.name, "brand": p.brand, "price": p.price, "rating": p.rating,
                     "reviews": p.num_reviews, "ram": p.specs.get("ram"), "storage": p.specs.get("storage"),
                     "gpu": p.specs.get("gpu"), "value_index": round((p.rating or 3) / max(p.price, 1) * 100, 2), "source": p.source})
    best = {"cheapest": min(rows, key=lambda r: r["price"])["uid"],
            "top_rated": max(rows, key=lambda r: r["rating"] or 0)["uid"],
            "best_value": max(rows, key=lambda r: r["value_index"])["uid"]}
    cheapest = min(r["price"] for r in rows)
    for r in rows:
        r["price_vs_cheapest"] = round(r["price"] - cheapest, 2)
    return {"rows": rows, "best": best}


COMPONENTS = ["price", "rating", "specs", "reviews", "preferences", "confidence"]


def t_rank(ctx, state, task, products, weights):
    c = task["constraints"]
    if not products:
        return []
    prices = [p.price for p in products]; pmin, pmax = min(prices), max(prices)
    ram_max = max([p.specs.get("ram", 0) for p in products] + [1]); sto_max = max([p.specs.get("storage", 0) for p in products] + [1])
    out = []
    for p in products:
        s = {}
        s["price"] = 1 - 0.7 * (p.price / c["max_price"]) if c.get("max_price") else 1 - 0.7 * ((p.price - pmin) / (pmax - pmin + 1e-9))
        s["rating"] = min(1, max(0, ((p.rating or 3.0) - 3) / 2))
        s["reviews"] = min(1, math.log10(p.num_reviews + 1) / 4)
        spec_vals = [p.specs[k] / m for k, m in (("ram", ram_max), ("storage", sto_max)) if k in p.specs]
        s["specs"] = sum(spec_vals) / len(spec_vals) if spec_vals else 0.5
        soft = c.get("soft_keywords", [])
        txt = p.text()
        s["preferences"] = sum(1 for k in soft if k.replace("-", " ") in txt) / len(soft) if soft else 0.5
        s["confidence"] = max(0, 1 - 0.25 * len([f for f in p.flags if f.endswith("unverified")]))
        s = {k: max(0.0, min(1.0, v)) for k, v in s.items()}
        wsum = sum(weights.values()) or 1
        contrib = {k: round(100 * weights.get(k, 0) * s[k] / wsum, 2) for k in COMPONENTS}
        score = round(sum(contrib.values()), 2)
        reasons = []
        if c.get("max_price"): reasons.append(f"${p.price:.0f} fits the ${c['max_price']:.0f} budget")
        if p.rating: reasons.append(f"rated {p.rating}★ by {p.num_reviews:,} reviewers")
        for key, lab in (("min_ram", "ram"), ("min_storage", "storage")):
            if c.get(key) and p.specs.get(lab): reasons.append(f"{p.specs[lab]} GB {lab} ≥ {c[key]} GB required")
        hit = [k for k in soft if k.replace("-", " ") in txt]
        if hit: reasons.append("matches preferences: " + ", ".join(hit))
        if p.flags and any(f.endswith("unverified") for f in p.flags): reasons.append("⚠ some specs could not be verified")
        out.append({"product": p, "score": score, "breakdown": contrib, "reasons": reasons})
    out.sort(key=lambda r: -r["score"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def t_validate(ctx, state, checkpoint, tasks, filtered=None, ranking=None, merged=None):
    checks = []
    def add(name, ok, detail=""): checks.append({"checkpoint": checkpoint, "check": name, "passed": bool(ok), "detail": detail})
    if checkpoint == "plan":
        add("at least one task extracted", bool(tasks), f"{len(tasks)} task(s)")
        add("budgets are positive", all((t["constraints"].get("max_price") or 1) > 0 for t in tasks))
        add("requirements not tampered (hash)", state.requirements_intact(), state.req_hash)
    elif checkpoint == "filter":
        for t in tasks:
            bad = [p.name for p in filtered.get(t["id"], []) if violations(p, t["constraints"])[0]]
            add(f"{t['label']}: all survivors satisfy hard constraints", not bad, ", ".join(bad[:3]))
    elif checkpoint == "ranking":
        for t in tasks:
            r = ranking.get(t["id"], [])
            scores = [x["score"] for x in r]
            add(f"{t['label']}: ranking sorted & scores in 0–100", scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores))
            add(f"{t['label']}: no duplicate products", len({x["product"].uid for x in r}) == len(r))
            add(f"{t['label']}: ranked items come from filtered set",
                {x["product"].uid for x in r} <= {p.uid for p in filtered.get(t["id"], [])})
    elif checkpoint == "final":
        add("requirements unchanged since planning", state.requirements_intact())
        for t in tasks:
            r = ranking.get(t["id"], [])
            if not r:
                add(f"{t['label']}: a recommendation exists", False, "no product satisfied every hard constraint"); continue
            top = r[0]["product"]
            mp = t["constraints"].get("max_price")
            add(f"{t['label']}: top pick within budget", mp is None or top.price <= mp, f"${top.price:.0f}")
            add(f"{t['label']}: top pick has complete data", bool(top.name and top.price > 0 and top.rating is not None))
    return checks


def t_supervise(ctx, state, validation, conflicts, errors, empty_tasks):
    failed = [v for v in validation if not v["passed"]]
    reasons = []
    if failed: reasons.append(f"{len(failed)} validation check(s) failed")
    if empty_tasks: reasons.append("no results for: " + ", ".join(empty_tasks))
    if any(c["needs_human"] for c in conflicts): reasons.append("large rating conflict between sources")
    if errors: reasons.append(f"{len(errors)} recoverable error(s) logged")
    risk = "high" if failed or empty_tasks else "medium" if reasons else "low"
    return {"decision": "escalate_to_human", "risk": risk, "reasons": reasons or ["all checkpoints passed"]}


def build_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register("parse_query", t_parse_query, "Decompose a natural-language query into structured tasks", {"planner"})
    r.register("route_tasks", t_route, "Create dependency-aware execution plan", {"router"})
    r.register("search_bestbuy", _search(providers.bestbuy_search), "Best Buy Products API (live, key)", {"search"}, live=True)
    r.register("search_dummyjson", _search(providers.dummyjson_search), "DummyJSON products API (live, no key)", {"search"}, live=True)
    r.register("search_demo", _search(providers.demo_catalog_search), "Offline demo catalog", {"search"})
    r.register("search_reviews", _search(providers.demo_reviews_search), "Offline review-aggregator feed", {"search"})
    r.register("merge_results", t_merge, "Synchronise, dedupe and resolve conflicts", {"synchronizer"})
    r.register("apply_filters", t_filter, "Apply hard constraints", {"filter"})
    r.register("compare_products", t_compare, "Build comparison table", {"comparison"})
    r.register("score_products", t_rank, "Requirement-aware transparent scoring", {"ranking"})
    r.register("validate_results", t_validate, "Checkpoint validation", {"validator"})
    r.register("workflow_control", t_supervise, "Supervisor decision / escalation", {"supervisor"})
    return r
