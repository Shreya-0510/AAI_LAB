from __future__ import annotations
from dart.mcp_client.connection import call_mcp_tool

async def execute_tests(repository: str, tests: list[str], timeout_seconds: int, approved: bool) -> dict:
    return await call_mcp_tool("run_selected_tests", {"repository": repository, "selected_tests": tests, "timeout_seconds": timeout_seconds, "approved": approved})
