# Kovanica MCP Servers — Configuration

> MCP servers that Kovanica can connect to for external tool integration.
> Mirrors Claude Code's MCP support.

## Registering an MCP server

```bash
# HTTP transport
kovanica mcp register my-server --transport http --url https://mcp.example.com

# Stdio transport (local process)
kovanica mcp register my-local --transport stdio --command "python -m mcp_server"
```

## Built-in MCP servers (optional)

### kovanica-node-mcp

Exposes Kovanica node RPC as MCP tools.

```json
{
  "name": "kovanica-node-mcp",
  "transport": "http",
  "url": "http://localhost:8080/mcp",
  "tools": [
    {"name": "get_head", "description": "Get current chain head"},
    {"name": "get_balance", "description": "Get address balance"},
    {"name": "get_blocks", "description": "List blocks"},
  ]
}
```

### kovanica-explorer-mcp

Exposes explorer.kovanica.online as MCP tools.

```json
{
  "name": "kovanica-explorer-mcp",
  "transport": "http",
  "url": "https://explorer.kovanica.online/mcp",
  "tools": [
    {"name": "get_head", "description": "Get current chain head"},
    {"name": "get_block", "description": "Get block by hash/height"},
    {"name": "get_transaction", "description": "Get transaction by hash"},
  ]
}
```

## MCP tool usage in agent loop

When an MCP server is registered, its tools are surfaced to the agent as additional tool choices. The agent can call them like any other tool.

```python
# In agent loop:
mcp_tools = mcp.list_mcp_tools()
for server, tools in mcp_tools.items():
    for tool in tools:
        # tool is an MCPTool with name, description, input_schema
        # Add to available tools for the LLM
```

## MCP in skills

Skills can declare MCP server dependencies:

```yaml
---
name: kovanica-query
description: Query the Kovanica node via MCP
mcp_servers:
  - kovanica-node-mcp
---

Use the `kovanica-node-mcp` MCP server to query the node.
Available tools: get_head, get_balance, get_blocks.
```

## MCP transport types

| Transport | Description | Use case |
|-----------|-------------|----------|
| `stdio` | Local process, stdin/stdout JSON-RPC | Local MCP servers |
| `http` | HTTP POST to MCP endpoint | Remote MCP servers |

## MCP security

- MCP servers run with the same permissions as the agent
- MCP servers can execute arbitrary code on the host
- Only register trusted MCP servers
- MCP servers from plugins are loaded with the plugin's permission level
