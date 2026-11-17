"""Agents + workflow engine (supervisor-driven).  Sequential vs parallel search execution."""
from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor

import config
from core import providers
from core.models import RECOVERABLE, PermissionDenied, WorkflowState
from core.tools import RunConfig, ToolRegistry, build_registry

REGISTRY: ToolRegistry = build_registry()
SEARCH_TOOL = {"bestbuy": "search_bestbuy", "dummyjson": "search_dummyjson", "demo": "search_demo"}


# ───────────────────────── retry helper ─────────────────────────
def call_with_retry(state, ctx, role, tool, agent, label, **kw):
    for attempt in range(ctx.max_retries + 1):
        try:
            with state.span(agent, label, tool=tool, retry=attempt) as ev:
                res = REGISTRY.call(role, tool, ctx, state, **kw)
                ev.output = f"{len(res)} products" if isinstance(res, list) else "ok"
                return res
        except RECOVERABLE as e:
            if attempt >= ctx.max_retries:
                raise
            state.count("retries")
            state.error(agent, f"{label}: {type(e).__name__} – retry {attempt + 1}/{ctx.max_retries}")
            time.sleep(0.25 * (2 ** attempt) * max(ctx.latency_scale, 0.1))


# ───────────────────────── agents ─────────────────────────
def planner_agent(state, ctx):
    with state.span("planner", "decompose query") as ev:
        plan = REGISTRY.call("planner", "parse_query", ctx, state, query=state.user_query)
        for e in plan["security_events"]:
            state.security_event(e["kind"], e["detail"], e["blocked"])
        state.plan = plan
        state.set_requirements("planner", plan["tasks"])
        state.msg("planner", "router", f"{len(plan['tasks'])} structured task(s)")
        ev.output = f"{len(plan['tasks'])} task(s)"
        if not plan["tasks"]:
            raise ValueError("No product requests could be understood in the query")


def router_agent(state, ctx):
    with state.span("router", "route tasks") as ev:
        state.routing = REGISTRY.call("router", "route_tasks", ctx, state, tasks=state.requirements)
        n = len(state.routing["subtasks"])
        state.msg("router", "search agents", f"{n} independent search sub-tasks (parallel group)")
        ev.output = f"{n} sub-tasks"


def search_agent(state, ctx, sub):
    """Runs one search sub-task. Never raises: failures are recorded and the supervisor-style fallback chain is used."""
    task = next(t for t in state.requirements if t["id"] == sub["task_id"])
    products, label = [], sub["label"]
    if sub["kind"] in ("catalog", "reviews"):
        tool = "search_demo" if sub["kind"] == "catalog" else "search_reviews"
        try:
            products = call_with_retry(state, ctx, "search", tool, "search", label, task=task)
        except Exception as e:  # noqa: BLE001
            state.error("search", f"{label}: {e}")
    else:
        for i, prov in enumerate(sub["chain"]):
            try:
                products = call_with_retry(state, ctx, "search", SEARCH_TOOL[prov], "search", f"{label} [{prov}]", task=task)
                if i:
                    state.msg("supervisor", "search", f"fallback → {prov} succeeded for {label}")
                break
            except Exception as e:  # noqa: BLE001
                state.error("search", f"{label} [{prov}]: {type(e).__name__}: {e}")
                if i + 1 < len(sub["chain"]):
                    state.count("fallbacks")
                    state.event("supervisor", label, "fallback", f"{prov} failed → trying {sub['chain'][i + 1]}")
    with state._lock:
        state.search_results[sub["id"]] = products
    state.msg("search", "synchronizer", f"{label}: {len(products)} products")
    return products


def run_search_stage(state, ctx):
    subs = state.routing["subtasks"]
    t = time.perf_counter()
    if ctx.mode == "parallel":
        with ThreadPoolExecutor(max_workers=min(8, len(subs)), thread_name_prefix="search") as ex:
            list(ex.map(lambda s: search_agent(state, ctx, s), subs))
    else:
        for s in subs:
            search_agent(state, ctx, s)
    state.metrics["search_stage_time"] = round(time.perf_counter() - t, 3)


def synchronizer_agent(state, ctx):
    with state.span("synchronizer", "merge + dedupe + resolve conflicts") as ev:
        state.merged, state.conflicts = REGISTRY.call("synchronizer", "merge_results", ctx, state,
                                                      results=state.search_results, tasks=state.requirements)
        total = sum(len(v) for v in state.merged.values())
        state.msg("synchronizer", "filter", f"{total} unique candidates, {len(state.conflicts)} conflict(s) resolved")
        ev.output = f"{total} candidates · {len(state.conflicts)} conflicts"


def downstream(state, ctx):
    """filter → compare → rank (dependent stages, always sequential) with validator checkpoints."""
    with state.span("validator", "checkpoint: plan") as ev:
        state.validation += REGISTRY.call("validator", "validate_results", ctx, state, checkpoint="plan", tasks=state.requirements)
        ev.output = "plan validated"
    with state.span("filter", "apply hard constraints") as ev:
        for t in state.requirements:
            kept, rej = REGISTRY.call("filter", "apply_filters", ctx, state, task=t, products=state.merged.get(t["id"], []))
            state.filtered[t["id"]], state.rejected[t["id"]] = kept, rej
        ev.output = " · ".join(f"{t['label']}: {len(state.filtered[t['id']])} kept" for t in state.requirements)
        state.msg("filter", "comparison", ev.output)
    with state.span("validator", "checkpoint: filter") as ev:
        state.validation += REGISTRY.call("validator", "validate_results", ctx, state, checkpoint="filter",
                                          tasks=state.requirements, filtered=state.filtered)
    with state.span("comparison", "compare candidates") as ev:
        state.comparison = {t["id"]: REGISTRY.call("comparison", "compare_products", ctx, state, task=t,
                                                   products=state.filtered[t["id"]]) for t in state.requirements}
        state.msg("comparison", "ranking", "comparison tables built")
    with state.span("ranking", "score + sort") as ev:
        for t in state.requirements:
            state.ranking[t["id"]] = REGISTRY.call("ranking", "score_products", ctx, state, task=t,
                                                   products=state.filtered[t["id"]], weights=ctx.weights)
        state.msg("ranking", "validator", "ranked lists produced")
    with state.span("validator", "checkpoint: ranking + final") as ev:
        for cp in ("ranking", "final"):
            state.validation += REGISTRY.call("validator", "validate_results", ctx, state, checkpoint=cp,
                                              tasks=state.requirements, filtered=state.filtered, ranking=state.ranking)
        failed = sum(1 for v in state.validation if not v["passed"])
        ev.output = f"{len(state.validation) - failed} passed · {failed} failed"


def supervisor_agent(state, ctx):
    with state.span("supervisor", "review + escalate to human") as ev:
        empty = [t["label"] for t in state.requirements if not state.ranking.get(t["id"])]
        state.supervisor = REGISTRY.call("supervisor", "workflow_control", ctx, state, validation=state.validation,
                                         conflicts=state.conflicts, errors=state.errors, empty_tasks=empty)
        state.msg("supervisor", "human", f"risk={state.supervisor['risk']}: " + "; ".join(state.supervisor["reasons"]))
        ev.output = f"risk {state.supervisor['risk']}"


# ───────────────────────── workflow ─────────────────────────
def run_workflow(query: str, ctx: RunConfig) -> WorkflowState:
    state = WorkflowState(query, ctx.mode)
    state.status = "running"
    try:
        planner_agent(state, ctx)
        router_agent(state, ctx)
        run_search_stage(state, ctx)
        synchronizer_agent(state, ctx)
        downstream(state, ctx)
        supervisor_agent(state, ctx)
        state.status = "awaiting_approval"
    except Exception as e:  # noqa: BLE001
        state.status = "failed"
        state.error("supervisor", f"workflow aborted: {type(e).__name__}: {e}")
    finalize_metrics(state, ctx)
    return state


def finalize_metrics(state, ctx):
    m = state.metrics
    m["total_time"] = round(state.now(), 3)
    m["live_api_calls"], m["cache_hits"] = ctx.stats["live_api_calls"], ctx.stats["cache_hits"]
    m["search_task_time_sum"] = round(sum(e.duration for e in state.trace if e.agent == "search" and e.tool), 3)
    m["cost_units"] = round(m["agent_calls"] * config.COST["agent_call"] + m["tool_calls"] * config.COST["tool_call"]
                            + m["live_api_calls"] * config.COST["live_api_call"] + m["retries"] * config.COST["retry"], 2)


def whatif(state: WorkflowState, ctx: RunConfig, weights: dict, budget_scale: float = 1.0) -> WorkflowState:
    """Re-run filter → compare → rank on already-fetched data with new weights / budget (human-authorised change)."""
    new = WorkflowState(state.user_query, "what-if")
    new.workflow_id = state.workflow_id + "-WI"
    new.merged, new.conflicts = state.merged, state.conflicts
    reqs = copy.deepcopy(state.requirements)
    for t in reqs:
        if t["constraints"].get("max_price"):
            t["constraints"]["max_price"] = round(t["constraints"]["max_price"] * budget_scale, 2)
    new.set_requirements("human", reqs)
    c2 = copy.copy(ctx); c2.weights = weights
    downstream(new, c2)
    new.status = "what-if"
    finalize_metrics(new, c2)
    return new


def build_final(state: WorkflowState) -> dict:
    picks, total = [], 0.0
    for t in state.requirements:
        r = state.ranking.get(t["id"], [])
        if r:
            p = r[0]["product"]; total += p.price
            picks.append({"task": t["label"], "domain": t["domain"], "product": p.name, "brand": p.brand, "price": p.price,
                          "rating": p.rating, "score": r[0]["score"], "why": r[0]["reasons"], "url": p.url})
    return {"workflow_id": state.workflow_id, "picks": picks, "basket_total": round(total, 2),
            "validated": all(v["passed"] for v in state.validation), "approved_by": "human"}


def save_history(state: WorkflowState):
    config.RUNS_DIR.mkdir(exist_ok=True)
    f = config.RUNS_DIR / "history.json"
    hist = json.loads(f.read_text()) if f.exists() else []
    hist.insert(0, {"id": state.workflow_id, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "query": state.user_query,
                    "status": state.human_approval["status"], "mode": state.mode, "time": state.metrics.get("total_time"),
                    "cost": state.metrics.get("cost_units"), "picks": state.final_recommendation.get("picks", [])})
    f.write_text(json.dumps(hist[:50], indent=2, default=str))


def benchmark(query: str, base: RunConfig) -> dict:
    """Run the identical query sequentially and in parallel (cache disabled) and compare."""
    out = {}
    for mode in ("sequential", "parallel"):
        c = RunConfig(mode=mode, use_cache=False, latency_scale=base.latency_scale, faults=dict(base.faults),
                      max_retries=base.max_retries, weights=dict(base.weights))
        s = run_workflow(query, c)
        out[mode] = {"total_time": s.metrics["total_time"], "search_stage_time": s.metrics["search_stage_time"],
                     "agent_calls": s.metrics["agent_calls"], "tool_calls": s.metrics["tool_calls"],
                     "retries": s.metrics["retries"], "cost_units": s.metrics["cost_units"],
                     "per_agent": _per_agent(s)}
    sp = out["sequential"]["search_stage_time"] / max(out["parallel"]["search_stage_time"], 1e-6)
    out["speedup_search"] = round(sp, 2)
    out["speedup_total"] = round(out["sequential"]["total_time"] / max(out["parallel"]["total_time"], 1e-6), 2)
    return out


def _per_agent(s: WorkflowState) -> dict:
    d: dict[str, float] = {}
    for e in s.trace:
        d[e.agent] = round(d.get(e.agent, 0) + e.duration, 3)
    return d
