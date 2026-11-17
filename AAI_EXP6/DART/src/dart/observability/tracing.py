from __future__ import annotations
from datetime import datetime, timezone
import time
import uuid

class TraceRecorder:
    def __init__(self) -> None:
        self.records: list[dict] = []
    async def call(self, tool_name: str, fn, *args, **kwargs):
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            result = await fn(*args, **kwargs)
            self.records.append({"trace_id": str(uuid.uuid4())[:12], "tool_name": tool_name, "started_at": timestamp, "duration_seconds": round(time.perf_counter() - started, 4), "status": "success", "detail": "MCP invocation completed"})
            return result
        except Exception as exc:
            self.records.append({"trace_id": str(uuid.uuid4())[:12], "tool_name": tool_name, "started_at": timestamp, "duration_seconds": round(time.perf_counter() - started, 4), "status": "error", "detail": f"{type(exc).__name__}: {exc}"})
            raise
