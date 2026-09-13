"""
Kovanica MCP client bridge — connect to MCP servers for external tool integration.

Mirrors Claude Code's MCP support:
- Connect to MCP servers via stdio or HTTP transport
- List available tools from the server
- Call tools via the server
- Tools are surfaced to the agent as additional tool choices
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# MCP tool descriptor
# ---------------------------------------------------------------------------

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict | None = None   # JSON Schema for the tool's arguments


# ---------------------------------------------------------------------------
# MCP client (transport abstraction)
# ---------------------------------------------------------------------------

class MCPClient:
    """Connects to one MCP server. Supports stdio and HTTP transports."""

    def __init__(self, name: str, transport: str = "stdio", command: list[str] | None = None, url: str | None = None):
        self.name = name
        self.transport = transport                    # "stdio" or "http"
        self.command = command or []
        self.url = url or ""
        self._tools: list[MCPTool] = []
        self._list_lock = threading.Lock()
        self._call_lock = threading.Lock()

    def list_tools(self) -> list[MCPTool]:
        """Fetch the tool list from the server. Cached per session."""
        with self._list_lock:
            if self._tools:
                return list(self._tools)
            try:
                if self.transport == "http":
                    self._tools = self._list_http()
                elif self.transport == "stdio":
                    self._tools = self._list_stdio()
                else:
                    return []
            except Exception as e:
                print(f"[mcp] {self.name}: list_tools failed: {e}", file=os.sys.stderr)
                return []
            return list(self._tools)

    def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool on the server. Returns the server's response."""
        with self._call_lock:
            try:
                if self.transport == "http":
                    return self._call_http(tool_name, arguments)
                elif self.transport == "stdio":
                    return self._call_stdio(tool_name, arguments)
                else:
                    return {"error": f"unknown transport {self.transport!r}"}
            except Exception as e:
                return {"error": f"mcp call failed: {e}"}

    # ---- HTTP transport ---------------------------------------------------

    def _list_http(self) -> list[MCPTool]:
        import requests
        resp = requests.post(
            f"{self.url.rstrip('/')}/tools/list",
            json={},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        tools = body.get("tools", [])
        return [MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema"))
                for t in tools]

    def _call_http(self, tool_name: str, arguments: dict) -> Any:
        import requests
        resp = requests.post(
            f"{self.url.rstrip('/')}/tools/call",
            json={"name": tool_name, "arguments": arguments},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ---- stdio transport --------------------------------------------------

    def _list_stdio(self) -> list[MCPTool]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        raw = self._stdio_request(payload)
        resp = json.loads(raw)
        tools = resp.get("result", {}).get("tools", [])
        return [MCPTool(name=t["name"], description=t.get("description", ""), input_schema=t.get("inputSchema"))
                for t in tools]

    def _call_stdio(self, tool_name: str, arguments: dict) -> Any:
        payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}
        raw = self._stdio_request(payload)
        resp = json.loads(raw)
        return resp.get("result", {})

    def _stdio_request(self, payload: dict) -> str:
        proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("mcp stdio: no response from server")
            return line
        finally:
            proc.stdin.close()
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Global MCP registry
# ---------------------------------------------------------------------------

_MCP_SERVERS: dict[str, MCPClient] = {}
_MCP_LOCK = threading.Lock()


def register_mcp_server(name: str, transport: str = "stdio", command: list[str] | None = None, url: str | None = None) -> dict:
    with _MCP_LOCK:
        if name in _MCP_SERVERS:
            return {"error": f"mcp server {name!r} already registered"}
        _MCP_SERVERS[name] = MCPClient(name, transport, command, url)
    return {"status": "registered", "name": name, "transport": transport}

def unregister_mcp_server(name: str) -> dict:
    with _MCP_LOCK:
        if name not in _MCP_SERVERS:
            return {"error": f"mcp server {name!r} not found"}
        del _MCP_SERVERS[name]
    return {"status": "unregistered", "name": name}

def list_mcp_tools(server: str | None = None) -> dict:
    with _MCP_LOCK:
        if server is not None:
            client = _MCP_SERVERS.get(server)
            if client is None:
                return {"error": f"mcp server {server!r} not found"}
            tools = client.list_tools()
            return {"server": server, "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]}
        out = {}
        for name, client in _MCP_SERVERS.items():
            try:
                out[name] = [{"name": t.name, "description": t.description} for t in client.list_tools()]
            except Exception as e:
                out[name] = [{"error": str(e)}]
        return out

def call_mcp_tool(server: str, tool_name: str, arguments: dict) -> Any:
    with _MCP_LOCK:
        client = _MCP_SERVERS.get(server)
        if client is None:
            return {"error": f"mcp server {server!r} not found"}
        return client.call_tool(tool_name, arguments)
