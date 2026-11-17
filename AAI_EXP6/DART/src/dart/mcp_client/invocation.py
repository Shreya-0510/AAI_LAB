from __future__ import annotations
from typing import Any
from dart.mcp_client.connection import call_mcp_tool

async def invoke_discovered_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Invoke a tool after the client verifies that the server advertises its name."""
    return await call_mcp_tool(name, arguments)
