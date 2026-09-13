"""
Plugin management commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult


class PluginsCommand(BaseCommand):
    """Manage Kovanica plugins."""
    
    name = "plugins"
    description = "Manage plugins (list, install, uninstall, enable, disable)"
    aliases = ["plugin"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List installed plugins")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        list_parser.add_argument("--available", action="store_true", help="Show available plugins from registry")
        
        # install
        install_parser = subparsers.add_parser("install", help="Install a plugin")
        install_parser.add_argument("name", help="Plugin name or path")
        install_parser.add_argument("--source", help="Plugin source (git URL, local path, registry)")
        
        # uninstall
        uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall a plugin")
        uninstall_parser.add_argument("name", help="Plugin name")
        uninstall_parser.add_argument("--keep-data", action="store_true", help="Keep plugin data")
        
        # enable
        enable_parser = subparsers.add_parser("enable", help="Enable a plugin")
        enable_parser.add_argument("name", help="Plugin name")
        
        # disable
        disable_parser = subparsers.add_parser("disable", help="Disable a plugin")
        disable_parser.add_argument("name", help="Plugin name")
        
        # update
        update_parser = subparsers.add_parser("update", help="Update plugins")
        update_parser.add_argument("name", nargs="?", help="Plugin name (default: all)")
        
        # details
        details_parser = subparsers.add_parser("details", help="Show plugin details")
        details_parser.add_argument("name", help="Plugin name")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_plugins(parsed)
        elif parsed.subcommand == "install":
            return self._install_plugin(parsed)
        elif parsed.subcommand == "uninstall":
            return self._uninstall_plugin(parsed)
        elif parsed.subcommand == "enable":
            return self._enable_plugin(parsed)
        elif parsed.subcommand == "disable":
            return self._disable_plugin(parsed)
        elif parsed.subcommand == "update":
            return self._update_plugin(parsed)
        elif parsed.subcommand == "details":
            return self._plugin_details(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_plugins_dir(self) -> Path:
        base = Path.home() / ".kovanica" / "plugins"
        base.mkdir(parents=True, exist_ok=True)
        return base
    
    def _load_plugin_manifest(self, plugin_dir: Path) -> dict | None:
        manifest_file = plugin_dir / ".kovanica-plugin" / "plugin.json"
        if manifest_file.exists():
            try:
                with open(manifest_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def _list_plugins(self, parsed) -> CommandResult:
        plugins_dir = self._get_plugins_dir()
        plugins = []
        
        for plugin_dir in plugins_dir.iterdir():
            if plugin_dir.is_dir():
                manifest = self._load_plugin_manifest(plugin_dir)
                if manifest:
                    plugins.append({
                        "name": manifest.get("name", plugin_dir.name),
                        "version": manifest.get("version", "unknown"),
                        "enabled": not (plugin_dir / ".disabled").exists(),
                        "path": str(plugin_dir),
                        "commands": manifest.get("commands", []),
                        "agents": manifest.get("agents", []),
                        "skills": manifest.get("skills", []),
                    })
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(plugins, indent=2))
        
        if not plugins:
            return CommandResult(success=True, output="No plugins installed.")
        
        lines = ["Installed Plugins:"]
        for p in plugins:
            status = "[green]enabled[/green]" if p["enabled"] else "[red]disabled[/red]"
            lines.append(f"  {p['name']} v{p['version']}  {status}")
            if p["commands"]:
                lines.append(f"    Commands: {', '.join(p['commands'])}")
            if p["agents"]:
                lines.append(f"    Agents: {', '.join(p['agents'])}")
            if p["skills"]:
                lines.append(f"    Skills: {', '.join(p['skills'])}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _install_plugin(self, parsed) -> CommandResult:
        # Placeholder - would clone from git, copy from local, or download from registry
        return CommandResult(success=True, output=f"Installing plugin: {parsed.name} (placeholder)")
    
    def _uninstall_plugin(self, parsed) -> CommandResult:
        plugins_dir = self._get_plugins_dir()
        plugin_dir = plugins_dir / parsed.name
        
        if not plugin_dir.exists():
            return CommandResult(success=False, error=f"Plugin not found: {parsed.name}")
        
        if not parsed.keep_data:
            import shutil
            shutil.rmtree(plugin_dir)
        else:
            # Just disable
            (plugin_dir / ".disabled").touch()
        
        return CommandResult(success=True, output=f"Uninstalled plugin: {parsed.name}")
    
    def _enable_plugin(self, parsed) -> CommandResult:
        plugins_dir = self._get_plugins_dir()
        plugin_dir = plugins_dir / parsed.name
        
        if not plugin_dir.exists():
            return CommandResult(success=False, error=f"Plugin not found: {parsed.name}")
        
        (plugin_dir / ".disabled").unlink(missing_ok=True)
        return CommandResult(success=True, output=f"Enabled plugin: {parsed.name}")
    
    def _disable_plugin(self, parsed) -> CommandResult:
        plugins_dir = self._get_plugins_dir()
        plugin_dir = plugins_dir / parsed.name
        
        if not plugin_dir.exists():
            return CommandResult(success=False, error=f"Plugin not found: {parsed.name}")
        
        (plugin_dir / ".disabled").touch()
        return CommandResult(success=True, output=f"Disabled plugin: {parsed.name}")
    
    def _update_plugin(self, parsed) -> CommandResult:
        if parsed.name:
            return CommandResult(success=True, output=f"Updating plugin: {parsed.name} (placeholder)")
        else:
            return CommandResult(success=True, output="Updating all plugins (placeholder)")
    
    def _plugin_details(self, parsed) -> CommandResult:
        plugins_dir = self._get_plugins_dir()
        plugin_dir = plugins_dir / parsed.name
        
        if not plugin_dir.exists():
            return CommandResult(success=False, error=f"Plugin not found: {parsed.name}")
        
        manifest = self._load_plugin_manifest(plugin_dir)
        if not manifest:
            return CommandResult(success=False, error=f"No manifest found for plugin: {parsed.name}")
        
        lines = [
            f"Plugin: {manifest.get('name', parsed.name)}",
            f"Version: {manifest.get('version', 'unknown')}",
            f"Description: {manifest.get('description', 'No description')}",
            f"Path: {plugin_dir}",
            f"Enabled: {not (plugin_dir / '.disabled').exists()}",
        ]
        
        if manifest.get("commands"):
            lines.append(f"Commands: {', '.join(manifest['commands'])}")
        if manifest.get("agents"):
            lines.append(f"Agents: {', '.join(manifest['agents'])}")
        if manifest.get("skills"):
            lines.append(f"Skills: {', '.join(manifest['skills'])}")
        if manifest.get("hooks"):
            lines.append(f"Hooks: {manifest['hooks']}")
        if manifest.get("mcpServers"):
            lines.append(f"MCP Servers: {manifest['mcpServers']}")
        
        return CommandResult(success=True, output="\n".join(lines))


class SkillsCommand(BaseCommand):
    """Manage skills."""
    
    name = "skills"
    description = "Manage skills (list, enable, disable, info)"
    aliases = ["skill"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List available skills")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        list_parser.add_argument("--enabled-only", action="store_true", help="Show only enabled skills")
        
        # enable
        enable_parser = subparsers.add_parser("enable", help="Enable a skill")
        enable_parser.add_argument("skill_name", help="Skill name")
        
        # disable
        disable_parser = subparsers.add_parser("disable", help="Disable a skill")
        disable_parser.add_argument("skill_name", help="Skill name")
        
        # info
        info_parser = subparsers.add_parser("info", help="Show skill details")
        info_parser.add_argument("skill_name", help="Skill name")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_skills(parsed)
        elif parsed.subcommand == "enable":
            return self._enable_skill(parsed)
        elif parsed.subcommand == "disable":
            return self._disable_skill(parsed)
        elif parsed.subcommand == "info":
            return self._skill_info(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_skills(self) -> dict:
        # Placeholder - would load from skills directory
        return {
            "kovanica-blockchain-developer": {
                "name": "Kovanica Blockchain Developer",
                "description": "Expert knowledge of Kovanica protocol, GHOSTDAG, PHANTOM, tokenomics",
                "enabled": True,
                "namespace": "kovanica",
                "tools": ["search_kovanica_docs", "explain_concept"],
            },
            "rust-developer": {
                "name": "Rust Developer",
                "description": "Rust best practices, async, traits, macros, cargo workflows",
                "enabled": True,
                "namespace": "general",
                "tools": ["search_codebase", "read_file", "run_cargo_command"],
            },
            "code-reviewer": {
                "name": "Code Reviewer",
                "description": "Security, performance, maintainability review patterns",
                "enabled": False,
                "namespace": "general",
                "tools": ["search_codebase", "read_file", "git_diff_suggest"],
            },
        }
    
    def _list_skills(self, parsed) -> CommandResult:
        skills = self._get_skills()
        
        filtered = skills
        if parsed.enabled_only:
            filtered = {k: v for k, v in skills.items() if v["enabled"]}
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(filtered, indent=2))
        
        lines = ["Available Skills:"]
        for name, info in sorted(filtered.items()):
            status = "[green]enabled[/green]" if info["enabled"] else "[red]disabled[/red]"
            lines.append(f"  {name}  ({info['namespace']})  {status}")
            lines.append(f"    {info['description']}")
            if info["tools"]:
                lines.append(f"    Tools: {', '.join(info['tools'])}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _enable_skill(self, parsed) -> CommandResult:
        skills = self._get_skills()
        if parsed.skill_name not in skills:
            return CommandResult(success=False, error=f"Unknown skill: {parsed.skill_name}")
        return CommandResult(success=True, output=f"Enabled skill: {parsed.skill_name}")
    
    def _disable_skill(self, parsed) -> CommandResult:
        skills = self._get_skills()
        if parsed.skill_name not in skills:
            return CommandResult(success=False, error=f"Unknown skill: {parsed.skill_name}")
        return CommandResult(success=True, output=f"Disabled skill: {parsed.skill_name}")
    
    def _skill_info(self, parsed) -> CommandResult:
        skills = self._get_skills()
        if parsed.skill_name not in skills:
            return CommandResult(success=False, error=f"Unknown skill: {parsed.skill_name}")
        
        info = skills[parsed.skill_name]
        lines = [
            f"Skill: {info['name']}",
            f"Namespace: {info['namespace']}",
            f"Status: {'Enabled' if info['enabled'] else 'Disabled'}",
            f"Description: {info['description']}",
            f"Tools: {', '.join(info['tools']) if info['tools'] else 'None'}",
        ]
        return CommandResult(success=True, output="\n".join(lines))