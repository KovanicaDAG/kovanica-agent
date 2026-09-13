"""
Configuration commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult


class ConfigCommand(BaseCommand):
    """Manage Kovanica configuration."""
    
    name = "config"
    description = "View and modify Kovanica configuration"
    aliases = ["cfg"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # get
        get_parser = subparsers.add_parser("get", help="Get a config value")
        get_parser.add_argument("key", help="Config key (e.g. model, theme, api_url)")
        get_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # set
        set_parser = subparsers.add_parser("set", help="Set a config value")
        set_parser.add_argument("key", help="Config key")
        set_parser.add_argument("value", help="Config value")
        set_parser.add_argument("--scope", choices=["user", "project"], default="user", help="Config scope")
        
        # list
        list_parser = subparsers.add_parser("list", help="List all config values")
        list_parser.add_argument("--scope", choices=["user", "project", "all"], default="all", help="Config scope")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # reset
        reset_parser = subparsers.add_parser("reset", help="Reset config to defaults")
        reset_parser.add_argument("key", nargs="?", help="Specific key to reset (default: all)")
        reset_parser.add_argument("--scope", choices=["user", "project"], default="user", help="Config scope")
        reset_parser.add_argument("--force", action="store_true", help="Skip confirmation")
        
        # edit
        edit_parser = subparsers.add_parser("edit", help="Open config in $EDITOR")
        edit_parser.add_argument("--scope", choices=["user", "project"], default="user", help="Config scope")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "get":
            return self._get_config(parsed)
        elif parsed.subcommand == "set":
            return self._set_config(parsed)
        elif parsed.subcommand == "list":
            return self._list_config(parsed)
        elif parsed.subcommand == "reset":
            return self._reset_config(parsed)
        elif parsed.subcommand == "edit":
            return self._edit_config(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_config_path(self, scope: str) -> Path:
        if scope == "user":
            return Path.home() / ".kovanica" / "settings.json"
        else:  # project
            return Path.cwd() / ".kovanica" / "settings.json"
    
    def _load_config(self, scope: str) -> dict:
        path = self._get_config_path(scope)
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_config(self, scope: str, config: dict) -> None:
        path = self._get_config_path(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
    
    def _get_merged_config(self) -> dict:
        """Get merged config (project overrides user)."""
        user_config = self._load_config("user")
        project_config = self._load_config("project")
        merged = {**user_config, **project_config}
        return merged
    
    def _get_config(self, parsed) -> CommandResult:
        merged = self._get_merged_config()
        
        if parsed.key not in merged:
            # Check user and project separately
            user_config = self._load_config("user")
            project_config = self._load_config("project")
            
            if parsed.key in project_config:
                source = "project"
                value = project_config[parsed.key]
            elif parsed.key in user_config:
                source = "user"
                value = user_config[parsed.key]
            else:
                return CommandResult(success=False, error=f"Config key not found: {parsed.key}")
        else:
            # Determine source
            project_config = self._load_config("project")
            if parsed.key in project_config:
                source = "project"
            else:
                source = "user"
            value = merged[parsed.key]
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps({"key": parsed.key, "value": value, "source": source}, indent=2))
        
        return CommandResult(success=True, output=f"{parsed.key} = {value}  (source: {source})")
    
    def _set_config(self, parsed) -> CommandResult:
        config = self._load_config(parsed.scope)
        config[parsed.key] = parsed.value
        self._save_config(parsed.scope, config)
        
        return CommandResult(success=True, output=f"Set {parsed.key} = {parsed.value} (scope: {parsed.scope})")
    
    def _list_config(self, parsed) -> CommandResult:
        if parsed.scope == "all":
            user_config = self._load_config("user")
            project_config = self._load_config("project")
            merged = self._get_merged_config()
            
            if parsed.json:
                return CommandResult(success=True, output=json.dumps({
                    "user": user_config,
                    "project": project_config,
                    "merged": merged,
                }, indent=2))
            
            lines = ["Configuration:"]
            lines.append("\n[User] (~/.kovanica/settings.json)")
            for k, v in sorted(user_config.items()):
                lines.append(f"  {k} = {v}")
            
            lines.append("\n[Project] (.kovanica/settings.json)")
            for k, v in sorted(project_config.items()):
                lines.append(f"  {k} = {v}  (overrides user)")
            
            return CommandResult(success=True, output="\n".join(lines))
        else:
            config = self._load_config(parsed.scope)
            if parsed.json:
                return CommandResult(success=True, output=json.dumps(config, indent=2))
            
            lines = [f"Configuration ({parsed.scope}):"]
            for k, v in sorted(config.items()):
                lines.append(f"  {k} = {v}")
            
            return CommandResult(success=True, output="\n".join(lines))
    
    def _reset_config(self, parsed) -> CommandResult:
        if not parsed.force and not parsed.key:
            return CommandResult(success=False, error="Use --force to confirm full reset, or specify a key")
        
        if parsed.key:
            config = self._load_config(parsed.scope)
            if parsed.key in config:
                del config[parsed.key]
                self._save_config(parsed.scope, config)
                return CommandResult(success=True, output=f"Reset {parsed.key} (scope: {parsed.scope})")
            else:
                return CommandResult(success=False, error=f"Key not found in {parsed.scope} config: {parsed.key}")
        else:
            # Reset all
            path = self._get_config_path(parsed.scope)
            if path.exists():
                path.unlink()
            return CommandResult(success=True, output=f"Reset all {parsed.scope} configuration")
    
    def _edit_config(self, parsed) -> CommandResult:
        import subprocess
        import os
        
        path = self._get_config_path(parsed.scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if not path.exists():
            # Create default config
            default_config = {
                "model": "qwen2.5-coder:3b",
                "theme": "default",
                "api_url": "",
                "api_token": "",
                "auto_approve": False,
                "verbose": False,
                "output_format": "text",
            }
            with open(path, "w") as f:
                json.dump(default_config, f, indent=2)
        
        editor = os.environ.get("EDITOR", "vi")
        try:
            subprocess.run([editor, str(path)], check=True)
            return CommandResult(success=True, output=f"Edited {path}")
        except subprocess.CalledProcessError:
            return CommandResult(success=False, error=f"Editor {editor} exited with error")
        except FileNotFoundError:
            return CommandResult(success=False, error=f"Editor not found: {editor}")


class ModelCommand(BaseCommand):
    """Switch LLM model (alias for /config set model)."""
    
    name = "model"
    description = "Switch the LLM model"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("model", nargs="?", help="Model name (e.g. qwen2.5-coder:3b, gpt-4)")
        parser.add_argument("--list", action="store_true", help="List available models")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.list:
            # In a real implementation, this would query the LLM endpoint
            models = [
                "qwen2.5-coder:3b",
                "qwen2.5-coder:7b",
                "qwen2.5-coder:14b",
                "qwen2.5-coder:32b",
                "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
                "gpt-4",
                "gpt-4o",
                "claude-3-5-sonnet",
                "claude-3-opus",
            ]
            return CommandResult(success=True, output="Available models:\n" + "\n".join(f"  {m}" for m in models))
        
        if not parsed.model:
            # Show current model
            config_cmd = ConfigCommand(self.cli)
            return config_cmd.execute(["get", "model"])
        
        config_cmd = ConfigCommand(self.cli)
        return config_cmd.execute(["set", "model", parsed.model])


class ThemeCommand(BaseCommand):
    """Switch theme (alias for /config set theme)."""
    
    name = "theme"
    description = "Switch the UI theme"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("theme", nargs="?", help="Theme name")
        parser.add_argument("--list", action="store_true", help="List available themes")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.list:
            themes_dir = Path.home() / ".kovanica" / "themes"
            builtin_themes = ["default", "dark", "light", "tokyonight", "grokday", "rosepinemoon", "oscuramidnight"]
            
            custom_themes = []
            if themes_dir.exists():
                custom_themes = [f.stem for f in themes_dir.glob("*.yaml")]
            
            all_themes = builtin_themes + custom_themes
            return CommandResult(success=True, output="Available themes:\n" + "\n".join(f"  {t}" for t in all_themes))
        
        if not parsed.theme:
            config_cmd = ConfigCommand(self.cli)
            return config_cmd.execute(["get", "theme"])
        
        config_cmd = ConfigCommand(self.cli)
        result = config_cmd.execute(["set", "theme", parsed.theme])
        
        if result.success:
            # Reload theme
            self.cli.theme.load_theme(parsed.theme)
        
        return result


class AlwaysApproveCommand(BaseCommand):
    """Toggle auto-approve mode."""
    
    name = "always-approve"
    description = "Toggle auto-approve mode for tool calls"
    aliases = ["auto-approve", "aa"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("value", nargs="?", choices=["on", "off", "true", "false", "1", "0"], help="Enable/disable")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if not parsed.value:
            config_cmd = ConfigCommand(self.cli)
            return config_cmd.execute(["get", "auto_approve"])
        
        value = parsed.value.lower() in ("on", "true", "1")
        config_cmd = ConfigCommand(self.cli)
        return config_cmd.execute(["set", "auto_approve", str(value).lower()])


class CompactCommand(BaseCommand):
    """Compress conversation history."""
    
    name = "compact"
    description = "Compress the current conversation history"
    aliases = []
    
    def execute(self, args: list[str]) -> CommandResult:
        # This would trigger the conversation compression logic
        # For now, just a placeholder
        return CommandResult(success=True, output="Conversation compressed (placeholder)")