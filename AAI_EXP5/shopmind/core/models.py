"""Shared workflow state, product model, tracing and errors."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# ───────────────────────── errors ─────────────────────────
class SecurityError(Exception): ...
class PermissionDenied(SecurityError): ...
class ProviderUnavailable(Exception):
    """Permanent failure (no API key, HTTP 4xx, circuit open). Not retried."""
class RateLimited(Exception):
    """Recoverable failure."""

RECOVERABLE = (TimeoutError, ConnectionError, RateLimited)


# ───────────────────────── product ─────────────────────────
@dataclass
class Product:
    uid: str
    name: str
    brand: str
    domain: str
    price: float
    rating: Optional[float]
    num_reviews: int
    source: str
    image: str = ""
    url: str = ""
    available: bool = True
    description: str = ""
    tags: list = field(default_factory=list)
    specs: dict = field(default_factory=dict)
    rating_sources: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)

    def text(self) -> str:
        parts = [self.name, self.brand, self.description, " ".join(self.tags),
                 " ".join(str(v) for v in self.specs.values())]
        return " ".join(parts).lower().replace("-", " ")

    def to_dict(self) -> dict:
        return asdict(self)


# ───────────────────────── trace ─────────────────────────
@dataclass
class TraceEvent:
    agent: str
    task: str
    start: float
    end: float = 0.0
    status: str = "running"      # ok | failed | skipped | fallback | denied
    tool: str = ""
    retry: int = 0
    error: str = ""
    output: str = ""
    thread: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# ───────────────────────── shared state ─────────────────────────
class WorkflowState:
    """Single shared state object that every agent reads/writes.
    Requirements are guarded: only the planner (and the human) may change them,
    and a hash lets the validator detect tampering."""

    REQ_WRITERS = {"planner", "human"}

    def __init__(self, query: str, mode: str):
        self.workflow_id = f"WF-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.user_query = query
        self.mode = mode
        self.requirements: list[dict] = []
        self.req_hash = ""
        self.plan: dict = {}
        self.routing: dict = {}
        self.messages: list[dict] = []
        self.search_results: dict[str, list[Product]] = {}
        self.merged: dict[str, list[Product]] = {}
        self.conflicts: list[dict] = []
        self.filtered: dict[str, list[Product]] = {}
        self.rejected: dict[str, list[dict]] = {}
        self.comparison: dict = {}
        self.ranking: dict[str, list[dict]] = {}
        self.validation: list[dict] = []
        self.supervisor: dict = {}
        self.human_approval: dict = {"status": "pending", "note": ""}
        self.final_recommendation: dict = {}
        self.errors: list[dict] = []
        self.security_events: list[dict] = []
        self.trace: list[TraceEvent] = []
        self.metrics: dict[str, Any] = {k: 0 for k in
            ("agent_calls", "tool_calls", "live_api_calls", "cache_hits", "retries", "fallbacks")}
        self.status = "created"
        self.t0 = time.perf_counter()
        self._lock = threading.RLock()

    # time helper
    def now(self) -> float:
        return time.perf_counter() - self.t0

    def count(self, key: str, n: int = 1):
        with self._lock:
            self.metrics[key] = self.metrics.get(key, 0) + n

    # requirement guard
    @staticmethod
    def hash_requirements(reqs: list[dict]) -> str:
        return hashlib.sha256(json.dumps(reqs, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def set_requirements(self, actor: str, reqs: list[dict]):
        if actor not in self.REQ_WRITERS:
            self.security_event("requirement_manipulation", f"'{actor}' tried to modify requirements", blocked=True)
            raise PermissionDenied(f"Agent '{actor}' may not modify requirements")
        with self._lock:
            self.requirements = reqs
            self.req_hash = self.hash_requirements(reqs)

    def requirements_intact(self) -> bool:
        return self.hash_requirements(self.requirements) == self.req_hash

    # logging helpers
    def security_event(self, kind: str, detail: str, blocked: bool = True):
        with self._lock:
            self.security_events.append({"t": round(self.now(), 3), "kind": kind, "detail": detail, "blocked": blocked})

    def msg(self, sender: str, receiver: str, summary: str):
        with self._lock:
            self.messages.append({"t": round(self.now(), 3), "from": sender, "to": receiver, "payload": summary})

    def error(self, agent: str, detail: str):
        with self._lock:
            self.errors.append({"t": round(self.now(), 3), "agent": agent, "detail": detail})

    def event(self, agent: str, task: str, status: str, output: str = "", tool: str = ""):
        """Zero-duration trace marker (fallback activated, retry scheduled, ...)."""
        t = self.now()
        with self._lock:
            self.trace.append(TraceEvent(agent, task, t, t, status, tool=tool, output=output,
                                         thread=threading.current_thread().name))

    @contextmanager
    def span(self, agent: str, task: str, tool: str = "", retry: int = 0):
        ev = TraceEvent(agent, task, self.now(), tool=tool, retry=retry,
                        thread=threading.current_thread().name)
        try:
            yield ev
            if ev.status == "running":
                ev.status = "ok"
        except Exception as e:  # noqa: BLE001
            ev.status = "denied" if isinstance(e, PermissionDenied) else "failed"
            ev.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            ev.end = self.now()
            with self._lock:
                self.trace.append(ev)
                self.metrics["agent_calls"] += 1
