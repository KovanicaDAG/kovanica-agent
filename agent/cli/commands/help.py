"""
Help and fuzzy search commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult


class HelpCommand(BaseCommand):
    """Show help for commands."""
    
    name = "help"
    description = "Show help for commands or list all commands"
    aliases = ["h", "?"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("command", nargs="?", help="Command to show help for")
        parser.add_argument("--all", action="store_true", help="Show all commands with descriptions")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        parsed = self.parse_args(args)
        
        if parsed.command:
            # Show help for specific command
            cmd = self.cli.commands.get(parsed.command)
            if cmd:
                return CommandResult(success=True, output=cmd.format_help())
            else:
                # Try aliases
                for name, cmd in self.cli.commands.items():
                    if parsed.command in cmd.aliases:
                        return CommandResult(success=True, output=cmd.format_help())
                return CommandResult(success=False, error=f"Unknown command: {parsed.command}")
        
        if parsed.all:
            return self._show_all_commands()
        
        return self._show_summary()
    
    def _show_summary(self) -> CommandResult:
        lines = [
            "Kovanica CLI — Slash Commands",
            "",
            "Session Management:",
            "  /session list|resume|new|delete|export|import|info  Manage sessions",
            "  /new                                              Start new session",
            "  /resume [id] [--fork]                             Resume session",
            "",
            "Configuration:",
            "  /config get|set|list|reset|edit                   Manage config",
            "  /model [name] [--list]                            Switch model",
            "  /theme [name] [--list]                            Switch theme",
            "  /always-approve [on|off]                          Toggle auto-approve",
            "  /compact                                          Compress history",
            "",
            "Tools & Permissions:",
            "  /tools list|enable|disable|info                   Manage tools",
            "  /permissions list|add|remove                      Manage permissions",
            "  /hooks list|add|remove                            Manage hooks",
            "  /mcp list|add|remove|test                         Manage MCP servers",
            "",
            "Memory:",
            "  /memory pending|approve|reject|approval|list|providers|sync",
            "  /refine                                           Trigger background review",
            "",
            "Plugins & Skills:",
            "  /plugins list|install|uninstall|enable|disable|update|details",
            "  /skills list|enable|disable|info                  Manage skills",
            "",
            "Goals & Automation:",
            "  /goal set|subgoal|list|status|complete|cancel     Manage goals",
            "  /heartbeat set|list|stop                          Recurring prompts",
            "  /steer [guidance] [--clear]                       Inject guidance",
            "  /queue add|list|clear                             Queue prompts",
            "  /prompt [/compose]                                Multi-line prompt in $EDITOR",
            "",
            "Other:",
            "  /help [command] [--all]                           Show help",
            "  /history [--limit N]                              Show conversation history",
            "  /jump <turn>                                      Jump to conversation turn",
            "  /timeline                                         Visual timeline",
            "  /timestamps [on|off]                              Toggle timestamps",
            "  /clear                                            Clear screen",
            "  /stop                                             Stop current operation",
            "  /quit [/exit]                                     Exit REPL",
            "",
            "Tip: Use Tab for fuzzy command completion. Type /help <command> for details.",
        ]
        return CommandResult(success=True, output="\n".join(lines))
    
    def _show_all_commands(self) -> CommandResult:
        lines = ["All Commands:"]
        for name, cmd in sorted(self.cli.commands.items()):
            aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  /{name}{aliases}")
            lines.append(f"    {cmd.description}")
        return CommandResult(success=True, output="\n".join(lines))


class HistoryCommand(BaseCommand):
    """Show conversation history."""
    
    name = "history"
    description = "Show conversation history"
    aliases = ["hist"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("--limit", type=int, default=50, help="Max turns to show")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        parsed = self.parse_args(args)
        
        history = self.cli.session.get_history(limit=parsed.limit)
        
        if parsed.json:
            import json
            return CommandResult(success=True, output=json.dumps(history, indent=2))
        
        if not history:
            return CommandResult(success=True, output="No history.")
        
        lines = ["Conversation History:"]
        for i, turn in enumerate(history):
            role = turn.get("role", "unknown")
            content = turn.get("content", "")[:100]
            lines.append(f"  {i+1}. [{role}] {content}...")
        
        return CommandResult(success=True, output="\n".join(lines))


class JumpCommand(BaseCommand):
    """Jump to a previous conversation turn."""
    
    name = "jump"
    description = "Jump to a previous conversation turn"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("turn", type=int, help="Turn number to jump to")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        # Placeholder - would implement history navigation
        return CommandResult(success=True, output=f"Jumped to turn {parsed.turn} (placeholder)")


class TimelineCommand(BaseCommand):
    """Show visual conversation timeline."""
    
    name = "timeline"
    description = "Show visual conversation timeline"
    aliases = ["tl"]
    
    def execute(self, args: list[str]) -> CommandResult:
        # Placeholder
        return CommandResult(success=True, output="Timeline view (placeholder)")


class TimestampsCommand(BaseCommand):
    """Toggle timestamps in conversation."""
    
    name = "timestamps"
    description = "Toggle timestamps display"
    aliases = ["ts"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("value", nargs="?", choices=["on", "off", "true", "false", "1", "0"], help="Enable/disable")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if not parsed.value:
            current = self.cli.config.get("show_timestamps", False)
            return CommandResult(success=True, output=f"Timestamps: {'on' if current else 'off'}")
        
        value = parsed.value.lower() in ("on", "true", "1")
        config_cmd = self.cli.commands.get("config")
        if config_cmd:
            return config_cmd.execute(["set", "show_timestamps", str(value).lower()])
        
        return CommandResult(success=True, output=f"Timestamps: {'on' if value else 'off'}")


class ClearCommand(BaseCommand):
    """Clear the screen."""
    
    name = "clear"
    description = "Clear the terminal screen"
    aliases = ["cls"]
    
    def execute(self, args: list[str]) -> CommandResult:
        import os
        os.system("clear" if os.name != "nt" else "cls")
        return CommandResult(success=True, output="")


class StopCommand(BaseCommand):
    """Stop current operation."""
    
    name = "stop"
    description = "Stop the current operation"
    aliases = []
    
    def execute(self, args: list[str]) -> CommandResult:
        self.cli.session.request_stop()
        return CommandResult(success=True, output="Stop requested")


class QuitCommand(BaseCommand):
    """Exit the REPL."""
    
    name = "quit"
    description = "Exit the REPL"
    aliases = ["exit", "q"]
    
    def execute(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, output="Goodbye!", should_exit=True)