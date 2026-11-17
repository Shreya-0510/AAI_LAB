from __future__ import annotations
from dart.mcp_client.connection import list_mcp_tools

async def discover_tool_catalog() -> list[dict]:
    """Discover tools and their schemas from the live MCP server."""
    return await list_mcp_tools()
