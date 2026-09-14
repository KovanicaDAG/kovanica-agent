from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

# Add agent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .config import ConfigManager
from .session import SessionManager
from .theme import ThemeManager
from .output import OutputFormatter, OutputFormat, CommandResult
from .completer import CompletionEngine
from .commands.base import BaseCommand, CLIContext
from .commands.session import SessionCommand, NewCommand, ResumeCommand
from .commands.config import ConfigCommand, ModelCommand, ThemeCommand, AlwaysApproveCommand, CompactCommand
from .commands.tools import ToolsCommand, PermissionsCommand, HooksCommand, MCPCommand
from .commands.memory import MemoryCommand, RefineCommand
from .commands.plugins import PluginsCommand, SkillsCommand
from .commands.goal import GoalCommand, HeartbeatCommand, SteerCommand, QueueCommand, PromptCommand
from .commands.help import HelpCommand, HistoryCommand, JumpCommand, TimelineCommand, TimestampsCommand, ClearCommand, StopCommand, QuitCommand


class KovanicaCLI:
    """Main Kovanica CLI application."""
    
    def __init__(self):
        self.config = ConfigManager()
        self.session = SessionManager(self.config)
        self.theme = ThemeManager(self.config)
        self.output = OutputFormatter(
            OutputFormat(self.config.get("output_format", "text"))
        )
        self.console = Console()
        
        # CLI context for commands (needed before registering commands)
        self.cli_context = CLIContext(self)
        
        # Initialize commands
        self.commands: Dict[str, BaseCommand] = {}
        self._register_commands()
        
        # Initialize completer after commands are registered
        self.completer = CompletionEngine(self)
    
    def _register_commands(self) -> None:
        """Register all slash commands."""
        command_classes = [
            # Session
            SessionCommand,
            NewCommand,
            ResumeCommand,
            # Config
            ConfigCommand,
            ModelCommand,
            ThemeCommand,
            AlwaysApproveCommand,
            CompactCommand,
            # Tools
            ToolsCommand,
            PermissionsCommand,
            HooksCommand,
            MCPCommand,
            # Memory
            MemoryCommand,
            RefineCommand,
            # Plugins
            PluginsCommand,
            SkillsCommand,
            # Goals
            GoalCommand,
            HeartbeatCommand,
            SteerCommand,
            QueueCommand,
            PromptCommand,
            # Help
            HelpCommand,
            HistoryCommand,
            JumpCommand,
            TimelineCommand,
            TimestampsCommand,
            ClearCommand,
            StopCommand,
            QuitCommand,
        ]
        
        for cmd_class in command_classes:
            cmd = cmd_class(self.cli_context)
            self.commands[cmd.name] = cmd
            for alias in cmd.aliases:
                self.commands[alias] = cmd
    
    def run(self, args: List[str] = None) -> int:
        """Run the CLI with given arguments."""
        if args is None:
            args = sys.argv[1:]
        
        parser = argparse.ArgumentParser(
            prog="kovanica",
            description="Kovanica — Kovanica engineering agent CLI",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self._get_epilog(),
        )
        
        # Global options
        parser.add_argument(
            "--output-format",
            choices=["text", "json", "stream-json"],
            default=self.config.get("output_format", "text"),
            help="Output format",
        )
        parser.add_argument(
            "--session",
            help="Session ID to use/resume",
        )
        parser.add_argument(
            "--resume",
            help="Resume session by ID or 'latest'",
        )
        parser.add_argument(
            "--continue",
            dest="continue_session",
            action="store_true",
            help="Continue most recent session",
        )
        parser.add_argument(
            "--fork",
            action="store_true",
            help="Fork session (new ID, keeps history)",
        )
        parser.add_argument(
            "--worktree",
            help="Worktree name or path for session filtering",
        )
        parser.add_argument(
            "--all-worktrees",
            action="store_true",
            help="Show sessions from all worktrees",
        )
        parser.add_argument(
            "--model",
            help="LLM model to use",
        )
        parser.add_argument(
            "--theme",
            help="UI theme",
        )
        parser.add_argument(
            "--api-url",
            help="Agent API URL",
        )
        parser.add_argument(
            "--api-token",
            help="Agent API token",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Verbose output",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="Disable colored output",
        )
        parser.add_argument(
            "--completion",
            choices=["bash", "zsh", "fish"],
            help="Generate shell completion script",
        )
        
        # Subcommands (legacy style)
        subparsers = parser.add_subparsers(dest="command", help="Commands")
        
        # Legacy commands for backward compatibility
        self._add_legacy_commands(subparsers)
        
        parsed = parser.parse_args(args)
        
        # Handle completion generation
        if parsed.completion:
            self._print_completion(parsed.completion)
            return 0
        
        # Apply global options
        if parsed.output_format:
            self.output.set_format(OutputFormat(parsed.output_format))
            self.config.set("output_format", parsed.output_format)
        
        if parsed.model:
            self.config.set("model", parsed.model)
        
        if parsed.theme:
            self.theme.load_theme(parsed.theme)
        
        if parsed.api_url:
            self.config.set("api_url", parsed.api_url)
        
        if parsed.api_token:
            self.config.set("api_token", parsed.api_token)
        
        if parsed.verbose:
            self.config.set("verbose", True)
        
        # Handle session resume/continue
        if parsed.resume:
            session_cmd = self.commands.get("session")
            if session_cmd:
                fork = parsed.fork
                worktree = parsed.worktree
                args = ["resume", parsed.resume]
                if fork:
                    args.append("--fork")
                if worktree:
                    args.extend(["--worktree", worktree])
                result = session_cmd.execute(args)
                self.output.print_result(result)
                if not result.success:
                    return 1
        
        elif parsed.continue_session:
            session_cmd = self.commands.get("session")
            if session_cmd:
                worktree = parsed.worktree
                args = ["resume", "latest"]
                if worktree:
                    args.extend(["--worktree", worktree])
                result = session_cmd.execute(args)
                self.output.print_result(result)
                if not result.success:
                    return 1
        
        # Handle legacy subcommands
        if parsed.command:
            return self._handle_legacy_command(parsed)
        
        # No command - start REPL
        return self._run_repl()
    
    def _add_legacy_commands(self, subparsers) -> None:
        """Add legacy subcommands for backward compatibility."""
        # chat
        p_chat = subparsers.add_parser("chat", help="Send a message and get the agent's response")
        p_chat.add_argument("message", nargs="+", help="Message to the agent")
        p_chat.add_argument("--session", default="cli-default", help="Session ID")
        p_chat.add_argument("--role", choices=["dev", "user"], default="dev", help="Role")
        p_chat.add_argument("--api", action="store_true", help="Delegate to agent-api server")
        
        # explain
        p_explain = subparsers.add_parser("explain", help="Explain a protocol term")
        p_explain.add_argument("term", help="Term to explain")
        p_explain.add_argument("--api", action="store_true", help="Delegate to agent-api server")
        
        # search
        p_search = subparsers.add_parser("search", help="Search the codebase")
        p_search.add_argument("query", help="Search query")
        p_search.add_argument("--api", action="store_true", help="Delegate to agent-api server")
        
        # read
        p_read = subparsers.add_parser("read", help="Read a file from the repo")
        p_read.add_argument("path", help="Path relative to repo root")
        p_read.add_argument("start", nargs="?", type=int, default=1, help="Start line")
        p_read.add_argument("end", nargs="?", type=int, default=None, help="End line")
        
        # cargo
        p_cargo = subparsers.add_parser("cargo", help="Run a whitelisted cargo command")
        p_cargo.add_argument("command", choices=["check", "test", "clippy", "build"], help="Cargo subcommand")
        p_cargo.add_argument("args", nargs=argparse.REMAINDER, help="Additional args")
        
        # kovanica
        p_kovanica = subparsers.add_parser("kovanica", help="Run the kovanica-cli binary")
        p_kovanica.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to kovanica")
        
        # diff
        p_diff = subparsers.add_parser("diff", help="Propose a patch")
        p_diff.add_argument("path", help="File path relative to repo root")
        p_diff.add_argument("explanation", help="Why this change is needed")
        p_diff.add_argument("patch", help="Unified diff text")
        
        # node
        p_node = subparsers.add_parser("node", help="Query the read-only node RPC")
        p_node.add_argument("endpoint", help="API endpoint")
        
        # health
        p_health = subparsers.add_parser("health", help="Check agent-api /healthz")
        p_health.add_argument("--api", action="store_true", help="Query agent-api server")
        
        # ready
        p_ready = subparsers.add_parser("ready", help="Check agent-api /readyz")
        p_ready.add_argument("--api", action="store_true", help="Query agent-api server")
        
        # confirm
        p_confirm = subparsers.add_parser("confirm", help="Approve/reject a pending diff")
        p_confirm.add_argument("session_id", help="Session ID")
        p_confirm.add_argument("--approve", action="store_true", default=True, help="Approve")
        p_confirm.add_argument("--reject", action="store_true", default=False, help="Reject")
        p_confirm.add_argument("--api", action="store_true", help="Use agent-api server")
        
        # repl
        p_repl = subparsers.add_parser("repl", help="Start interactive REPL")
        p_repl.add_argument("--session", help="Session ID")
    
    def _handle_legacy_command(self, parsed) -> int:
        """Handle legacy subcommand."""
        # This would delegate to the original kovanica CLI logic
        # For now, just print a message
        self.output.print(f"Legacy command: {parsed.command} (not yet implemented in enhanced CLI)")
        return 0
    
    def _run_repl(self) -> int:
        """Run the interactive REPL."""
        self._print_banner()
        
        # Load or create session
        if not self.session.current_id:
            self.session.create_session()
        
        try:
            while True:
                try:
                    # Process queued prompts first
                    if self.session.queue:
                        prompt = self.session.queue.pop(0)
                        self.output.print(f"[Queued] {prompt}")
                    else:
                        # Get prompt
                        prompt = self._get_prompt()
                    
                    if not prompt:
                        continue
                    
                    # Handle slash commands
                    if prompt.startswith("/"):
                        result = self._handle_slash_command(prompt[1:])
                        self.output.print_result(result)
                        if result.should_exit:
                            break
                        continue
                    
                    # Handle ! shell commands
                    if prompt.startswith("!"):
                        result = self._handle_shell_command(prompt[1:])
                        self.output.print_result(result)
                        continue
                    
                    # Regular chat message
                    result = self._handle_chat(prompt)
                    self.output.print_result(result)
                    
                    # Check for auto-continue
                    if self.session.is_auto_continue_active():
                        goal_id = self.session.get_auto_continue_goal()
                        if goal_id:
                            # Auto-continue: send a continuation prompt
                            continue_prompt = f"Continue working on goal {goal_id}. What's the next step?"
                            self.output.print(f"[Auto-continue] {continue_prompt}")
                            result = self._handle_chat(continue_prompt)
                            self.output.print_result(result)
                    
                except KeyboardInterrupt:
                    print("\nInterrupted")
                    self.session.clear_stop()
                except EOFError:
                    break
        
        finally:
            # Stop all background tasks on exit
            self.session.stop_all_background_tasks()
            self.output.print_end()
        
        return 0
    
    def _print_banner(self) -> None:
        """Print startup banner."""
        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║  Kovanica — Kovanica Engineering Agent CLI v0.2.0           ║
║  Type /help for commands, /quit to exit                     ║
╚══════════════════════════════════════════════════════════════╝
"""
        self.output.print(banner)
    
    def _get_prompt(self) -> str:
        """Get user input with prompt."""
        session_info = ""
        if self.session.current_id:
            session_info = f" [{self.session.current_id[:8]}]"
        
        goal_info = ""
        if self.session.current_goal:
            goal_info = f" 🎯{self.session.current_goal[:8]}"
        
        prompt_str = f"kovanica{session_info}{goal_info} > "
        
        try:
            return input(prompt_str).strip()
        except EOFError:
            raise
    
    def _handle_slash_command(self, command_line: str) -> CommandResult:
        """Handle a slash command."""
        import shlex
        parts = shlex.split(command_line)
        if not parts:
            return CommandResult(success=True, output="")
        
        cmd_name = parts[0]
        args = parts[1:]
        
        # Find command
        cmd = self.commands.get(cmd_name)
        if not cmd:
            # Try fuzzy match
            if hasattr(self.completer, 'process') and self.completer.process:
                from rapidfuzz import process, fuzz
                all_cmds = list(self.commands.keys())
                matches = process.extract(cmd_name, all_cmds, scorer=fuzz.WRatio, limit=3)
                suggestions = [m[0] for m in matches if m[1] > 60]
                if suggestions:
                    return CommandResult(
                        success=False,
                        error=f"Unknown command: /{cmd_name}. Did you mean: {', '.join('/' + s for s in suggestions)}?"
                    )
            return CommandResult(success=False, error=f"Unknown command: /{cmd_name}. Type /help for list.")
        
        # Execute command
        return cmd.execute(args)
    
    def _handle_shell_command(self, command: str) -> CommandResult:
        """Handle a ! shell command."""
        import subprocess
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return CommandResult(success=True, output=output.strip())
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, error="Command timed out after 60s")
        except Exception as e:
            return CommandResult(success=False, error=str(e))
    
    def _handle_chat(self, message: str) -> CommandResult:
        """Handle a chat message."""
        # Save user message
        self.session.save_turn("user", message)
        
        # Include steer guidance if present
        steer_guidance = self.session.get_steer_guidance()
        if steer_guidance:
            message = f"{message}\n\n[Steer guidance: {steer_guidance}]"
            # Clear steer guidance after use (one-shot)
            self.session.set_steer_guidance(None)
        
        # This would call the actual agent
        # For now, return a placeholder
        reply = f"[Agent would respond to: {message}]"
        
        # Save assistant message
        self.session.save_turn("assistant", reply)
        
        return CommandResult(success=True, output=reply)
    
    def _print_completion(self, shell: str) -> None:
        """Print shell completion script."""
        if shell == "bash":
            print(self.completer.generate_bash_completion())
        elif shell == "zsh":
            print(self.completer.generate_zsh_completion())
        elif shell == "fish":
            print(self.completer.generate_fish_completion())
    
    def _get_epilog(self) -> str:
        return """
examples:
  kovanica chat "how is selected_parent computed"
  kovanica explain mergeset
  kovanica search "coinbase maturity"
  kovanica read crates/kovanica-state/src/ledger.rs 100 120
  kovanica cargo test -p kovanica-dag
  kovanica kovanica head
  kovanica kovanica balance kvnc1q...dag
  kovanica cargo clippy --all-targets
  kovanica diff crates/kovanica-node/src/node.rs "fix maturity" '--- a/path ...'
  kovanica node /api/head
  kovanica --resume latest
  kovanica --output-format json chat "hello"
  kovanica --completion bash > ~/.bash_completion.d/kovanica

REPL mode (no subcommand):
  kovanica
  Then use /commands, !shell, or chat naturally
"""


def main():
    """Main entry point."""
    cli = KovanicaCLI()
    sys.exit(cli.run())


if __name__ == "__main__":
    main()