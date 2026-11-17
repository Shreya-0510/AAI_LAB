from __future__ import annotations
import asyncio
from pathlib import Path
import sys
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVER_FILE = PROJECT_ROOT / "src" / "dart" / "mcp_server" / "server.py"

def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(SERVER_FILE)], env=None)

async def list_mcp_tools() -> list[dict[str, Any]]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [{"name": tool.name, "description": tool.description or "", "input_schema": tool.inputSchema} for tool in result.tools]

async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> Any:
    async def invoke() -> Any:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                known = {tool.name for tool in tools_result.tools}
                if name not in known:
                    raise ValueError(f"MCP tool '{name}' not found. Available tools: {sorted(known)}")
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError(f"MCP tool {name} failed: {result.content}")
                structured = getattr(result, "structuredContent", None)
                if structured is not None:
                    return structured
                pieces = []
                for item in result.content:
                    if getattr(item, "text", None):
                        try:
                            import json
                            pieces.append(json.loads(item.text))
                        except Exception:
                            pieces.append(item.text)
                if len(pieces) == 1:
                    return pieces[0]
                return pieces

    try:
        return await asyncio.wait_for(invoke(), timeout=20)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"MCP tool '{name}' timed out after 20 seconds.") from exc
