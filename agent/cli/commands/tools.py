"""
Tool management commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult


class ToolsCommand(BaseCommand):
    """Manage available tools."""
    
    name = "tools"
    description = "List, enable, or disable tools"
    aliases = ["tool"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List all tools")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        list_parser.add_argument("--enabled-only", action="store_true", help="Show only enabled tools")
        list_parser.add_argument("--disabled-only", action="store_true", help="Show only disabled tools")
        
        # enable
        enable_parser = subparsers.add_parser("enable", help="Enable a tool")
        enable_parser.add_argument("tool_name", help="Tool name to enable")
        
        # disable
        disable_parser = subparsers.add_parser("disable", help="Disable a tool")
        disable_parser.add_argument("tool_name", help="Tool name to disable")
        
        # info
        info_parser = subparsers.add_parser("info", help="Show tool details")
        info_parser.add_argument("tool_name", help="Tool name")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_tools(parsed)
        elif parsed.subcommand == "enable":
            return self._enable_tool(parsed)
        elif parsed.subcommand == "disable":
            return self._disable_tool(parsed)
        elif parsed.subcommand == "info":
            return self._tool_info(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_tools(self) -> dict:
        """Get available tools from CLI context."""
        # This would be populated from the actual tool registry
        return {
            "search_codebase": {
                "description": "Semantic + keyword search over the indexed codebase",
                "enabled": True,
                "category": "search",
            },
            "search_kovanica_docs": {
                "description": "Semantic search over Kovanica protocol reference docs",
                "enabled": True,
                "category": "search",
            },
            "read_file": {
                "description": "Read a file from the repository",
                "enabled": True,
                "category": "filesystem",
            },
            "run_cargo_command": {
                "description": "Run whitelisted cargo commands (check, test, clippy, build)",
                "enabled": True,
                "category": "build",
            },
            "git_diff_suggest": {
                "description": "Propose a patch for human review (does not apply)",
                "enabled": True,
                "category": "code",
            },
            "query_node_api": {
                "description": "Query read-only Kovanica node RPC endpoints",
                "enabled": True,
                "category": "network",
            },
            "explain_concept": {
                "description": "Explain a protocol term from codebase and docs",
                "enabled": True,
                "category": "knowledge",
            },
            "run_kovanica_cli": {
                "description": "Run the kovanica-cli binary (explorer + wallet)",
                "enabled": True,
                "category": "cli",
            },
        }
    
    def _list_tools(self, parsed) -> CommandResult:
        tools = self._get_tools()
        
        filtered = tools
        if parsed.enabled_only:
            filtered = {k: v for k, v in tools.items() if v["enabled"]}
        elif parsed.disabled_only:
            filtered = {k: v for k, v in tools.items() if not v["enabled"]}
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(filtered, indent=2))
        
        lines = ["Available Tools:"]
        for name, info in sorted(filtered.items()):
            status = "[green]enabled[/green]" if info["enabled"] else "[red]disabled[/red]"
            lines.append(f"  {name}  ({info['category']})  {status}")
            lines.append(f"    {info['description']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _enable_tool(self, parsed) -> CommandResult:
        tools = self._get_tools()
        if parsed.tool_name not in tools:
            return CommandResult(success=False, error=f"Unknown tool: {parsed.tool_name}")
        
        # In a real implementation, this would update the tool registry
        # For now, just simulate
        return CommandResult(success=True, output=f"Enabled tool: {parsed.tool_name}")
    
    def _disable_tool(self, parsed) -> CommandResult:
        tools = self._get_tools()
        if parsed.tool_name not in tools:
            return CommandResult(success=False, error=f"Unknown tool: {parsed.tool_name}")
        
        # In a real implementation, this would update the tool registry
        return CommandResult(success=True, output=f"Disabled tool: {parsed.tool_name}")
    
    def _tool_info(self, parsed) -> CommandResult:
        tools = self._get_tools()
        if parsed.tool_name not in tools:
            return CommandResult(success=False, error=f"Unknown tool: {parsed.tool_name}")
        
        info = tools[parsed.tool_name]
        lines = [
            f"Tool: {parsed.tool_name}",
            f"Category: {info['category']}",
            f"Status: {'Enabled' if info['enabled'] else 'Disabled'}",
            f"Description: {info['description']}",
        ]
        return CommandResult(success=True, output="\n".join(lines))


class PermissionsCommand(BaseCommand):
    """Manage tool permissions."""
    
    name = "permissions"
    description = "Manage tool permission rules"
    aliases = ["perms"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List permission rules")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # add
        add_parser = subparsers.add_parser("add", help="Add a permission rule")
        add_parser.add_argument("tool", help="Tool name or pattern")
        add_parser.add_argument("action", choices=["allow", "deny", "ask"], help="Permission action")
        add_parser.add_argument("--scope", choices=["session", "project", "user"], default="session", help="Rule scope")
        
        # remove
        remove_parser = subparsers.add_parser("remove", help="Remove a permission rule")
        remove_parser.add_argument("rule_id", help="Rule ID to remove")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_permissions(parsed)
        elif parsed.subcommand == "add":
            return self._add_permission(parsed)
        elif parsed.subcommand == "remove":
            return self._remove_permission(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _list_permissions(self, parsed) -> CommandResult:
        # Placeholder - would read from permission store
        rules = [
            {"id": "1", "tool": "run_cargo_command", "action": "allow", "scope": "session"},
            {"id": "2", "tool": "git_diff_suggest", "action": "ask", "scope": "session"},
            {"id": "3", "tool": "*", "action": "ask", "scope": "user"},
        ]
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(rules, indent=2))
        
        lines = ["Permission Rules:"]
        for rule in rules:
            lines.append(f"  [{rule['id']}] {rule['tool']} -> {rule['action']} ({rule['scope']})")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _add_permission(self, parsed) -> CommandResult:
        # Placeholder
        return CommandResult(success=True, output=f"Added rule: {parsed.tool} -> {parsed.action} ({parsed.scope})")
    
    def _remove_permission(self, parsed) -> CommandResult:
        # Placeholder
        return CommandResult(success=True, output=f"Removed rule: {parsed.rule_id}")


class HooksCommand(BaseCommand):
    """Manage hooks."""
    
    name = "hooks"
    description = "Manage event hooks (PreToolUse, PostToolUse, Stop, SessionStart)"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List hooks")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # add
        add_parser = subparsers.add_parser("add", help="Add a hook")
        add_parser.add_argument("event", choices=["PreToolUse", "PostToolUse", "Stop", "SessionStart"], help="Hook event")
        add_parser.add_argument("matcher", help="Tool name pattern to match")
        add_parser.add_argument("command", help="Command to execute")
        
        # remove
        remove_parser = subparsers.add_parser("remove", help="Remove a hook")
        remove_parser.add_argument("hook_id", help="Hook ID to remove")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_hooks(parsed)
        elif parsed.subcommand == "add":
            return self._add_hook(parsed)
        elif parsed.subcommand == "remove":
            return self._remove_hook(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _list_hooks(self, parsed) -> CommandResult:
        # Placeholder
        hooks = [
            {"id": "1", "event": "PreToolUse", "matcher": "Write|Edit", "command": "bash scan-secrets.sh"},
            {"id": "2", "event": "SessionStart", "matcher": ".*", "command": "bash load-context.sh"},
        ]
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(hooks, indent=2))
        
        lines = ["Hooks:"]
        for hook in hooks:
            lines.append(f"  [{hook['id']}] {hook['event']} | {hook['matcher']} -> {hook['command']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _add_hook(self, parsed) -> CommandResult:
        return CommandResult(success=True, output=f"Added hook: {parsed.event} | {parsed.matcher} -> {parsed.command}")
    
    def _remove_hook(self, parsed) -> CommandResult:
        return CommandResult(success=True, output=f"Removed hook: {parsed.hook_id}")


class MCPCommand(BaseCommand):
    """Manage MCP servers."""
    
    name = "mcp"
    description = "Manage Model Context Protocol servers"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List MCP servers")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # add
        add_parser = subparsers.add_parser("add", help="Add an MCP server")
        add_parser.add_argument("name", help="Server name")
        add_parser.add_argument("command", help="Command to start server")
        add_parser.add_argument("args", nargs="*", help="Server arguments")
        add_parser.add_argument("--env", action="append", help="Environment variables (KEY=VALUE)")
        
        # remove
        remove_parser = subparsers.add_parser("remove", help="Remove an MCP server")
        remove_parser.add_argument("name", help="Server name")
        
        # test
        test_parser = subparsers.add_parser("test", help="Test MCP server connection")
        test_parser.add_argument("name", help="Server name")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_mcp(parsed)
        elif parsed.subcommand == "add":
            return self._add_mcp(parsed)
        elif parsed.subcommand == "remove":
            return self._remove_mcp(parsed)
        elif parsed.subcommand == "test":
            return self._test_mcp(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _list_mcp(self, parsed) -> CommandResult:
        # Placeholder
        servers = [
            {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"], "status": "connected"},
            {"name": "github", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "status": "disconnected"},
        ]
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(servers, indent=2))
        
        lines = ["MCP Servers:"]
        for s in servers:
            status = "[green]connected[/green]" if s["status"] == "connected" else "[red]disconnected[/red]"
            lines.append(f"  {s['name']}  {status}")
            lines.append(f"    {s['command']} {' '.join(s['args'])}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _add_mcp(self, parsed) -> CommandResult:
        env_str = ""
        if parsed.env:
            env_str = " " + " ".join(parsed.env)
        return CommandResult(success=True, output=f"Added MCP server: {parsed.name} -> {parsed.command} {' '.join(parsed.args)}{env_str}")
    
    def _remove_mcp(self, parsed) -> CommandResult:
        return CommandResult(success=True, output=f"Removed MCP server: {parsed.name}")
    
    def _test_mcp(self, parsed) -> CommandResult:
        return CommandResult(success=True, output=f"Testing MCP server {parsed.name}... (placeholder)")