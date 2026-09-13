"""
Base command class for Kovanica slash commands.
"""
from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CommandResult:
    """Result of a slash command execution."""
    success: bool
    output: str = ""
    error: str = ""
    data: Any = None
    should_exit: bool = False


class BaseCommand(ABC):
    """Base class for all slash commands."""
    
    name: str = ""
    description: str = ""
    aliases: list[str] = []
    
    def __init__(self, cli_context: "CLIContext"):
        self.cli = cli_context
    
    @abstractmethod
    def execute(self, args: list[str]) -> CommandResult:
        """Execute the command with parsed arguments."""
        pass
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser for this command."""
        parser = argparse.ArgumentParser(
            prog=f"/{self.name}",
            description=self.description,
            add_help=False,
        )
        parser.add_argument("-h", "--help", action="store_true", help="Show help")
        return parser
    
    def parse_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments, handling help flag."""
        parser = self.create_parser()
        try:
            return parser.parse_args(args)
        except SystemExit as e:
            # argparse calls sys.exit on error/help, catch it
            # Return a namespace with error info
            if e.code == 0:
                # Help was requested
                raise
            # For other errors, we'll handle them in execute
            raise
    
    def format_help(self) -> str:
        """Format help text for this command."""
        parser = self.create_parser()
        return parser.format_help()


class CLIContext:
    """Context passed to all commands - provides access to CLI state."""
    
    def __init__(self, cli: "KovanicaCLI"):
        self.cli = cli
        self.session = cli.session
        self.config = cli.config
        self.console = cli.console
        self.theme = cli.theme
    
    def print(self, *args, **kwargs):
        """Print to console."""
        self.console.print(*args, **kwargs)
    
    def print_error(self, msg: str):
        """Print error message."""
        self.console.print(f"[red]Error:[/red] {msg}")
    
    def print_success(self, msg: str):
        """Print success message."""
        self.console.print(f"[green]{msg}[/green]")
    
    def print_warning(self, msg: str):
        """Print warning message."""
        self.console.print(f"[yellow]Warning:[/yellow] {msg}")