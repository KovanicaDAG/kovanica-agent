"""
Memory management commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult

# Import memory providers
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from memory_providers import (
    MemoryProvider,
    LocalMemoryProvider,
    SQLiteMemoryProvider,
    VectorMemoryProvider,
    ByteRoverProvider,
    SupermemoryProvider,
    get_provider,
    get_available_providers,
    initialize_providers,
    MemoryItem,
)


class MemoryCommand(BaseCommand):
    """Manage conversation memory."""
    
    name = "memory"
    description = "Manage persistent memory across sessions"
    aliases = ["mem"]
    
    def __init__(self, cli_context: CLIContext):
        super().__init__(cli_context)
        self._provider_instances: dict[str, MemoryProvider] = {}
        self._init_providers()
    
    def _init_providers(self) -> None:
        """Initialize memory providers from config."""
        config = self.cli.config.get_merged_config()
        provider_configs = {
            "local": {"memory_dir": str(Path.home() / ".kovanica" / "memory"), "memory_approval": config.get("memory_approval", True)},
            "sqlite": {"sqlite_path": str(Path.home() / ".kovanica" / "memory" / "memory.db")},
            "vector": {"chroma_path": str(Path.home() / ".kovanica" / "memory" / "chroma")},
            "byterover": {"api_key": os.environ.get("BYTEROVER_API_KEY")},
            "supermemory": {"api_key": os.environ.get("SUPERMEMORY_API_KEY")},
        }
        
        for name, provider_class in {
            "local": LocalMemoryProvider,
            "sqlite": SQLiteMemoryProvider,
            "vector": VectorMemoryProvider,
            "byterover": ByteRoverProvider,
            "supermemory": SupermemoryProvider,
        }.items():
            provider = provider_class()
            if provider.initialize(provider_configs.get(name, {})):
                self._provider_instances[name] = provider
    
    def _get_provider(self, name: str) -> MemoryProvider:
        """Get provider by name, defaulting to local."""
        return self._provider_instances.get(name, self._provider_instances.get("local"))
    
    def _get_all_providers(self) -> list[MemoryProvider]:
        return list(self._provider_instances.values())
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # pending
        pending_parser = subparsers.add_parser("pending", help="Show pending memory items awaiting approval")
        pending_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # approve
        approve_parser = subparsers.add_parser("approve", help="Approve a pending memory item")
        approve_parser.add_argument("item_id", help="Memory item ID to approve")
        
        # reject
        reject_parser = subparsers.add_parser("reject", help="Reject a pending memory item")
        reject_parser.add_argument("item_id", help="Memory item ID to reject")
        
        # approval
        approval_parser = subparsers.add_parser("approval", help="Toggle memory approval gate")
        approval_parser.add_argument("mode", choices=["on", "off"], help="Enable or disable approval")
        
        # list
        list_parser = subparsers.add_parser("list", help="List approved memory items")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        list_parser.add_argument("--provider", help="Filter by memory provider")
        
        # providers
        providers_parser = subparsers.add_parser("providers", help="List available memory providers")
        providers_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # sync
        sync_parser = subparsers.add_parser("sync", help="Force memory sync with providers")
        sync_parser.add_argument("--provider", help="Specific provider to sync")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "pending":
            return self._pending(parsed)
        elif parsed.subcommand == "approve":
            return self._approve(parsed)
        elif parsed.subcommand == "reject":
            return self._reject(parsed)
        elif parsed.subcommand == "approval":
            return self._approval(parsed)
        elif parsed.subcommand == "list":
            return self._list(parsed)
        elif parsed.subcommand == "providers":
            return self._providers(parsed)
        elif parsed.subcommand == "sync":
            return self._sync(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_memory_dir(self) -> Path:
        base = Path.home() / ".kovanica" / "memory"
        base.mkdir(parents=True, exist_ok=True)
        return base
    
    def _load_pending(self) -> list:
        pending_file = self._get_memory_dir() / "pending.jsonl"
        items = []
        if pending_file.exists():
            with open(pending_file) as f:
                for line in f:
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        pass
        return items
    
    def _save_pending(self, items: list) -> None:
        pending_file = self._get_memory_dir() / "pending.jsonl"
        with open(pending_file, "w") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")
    
    def _load_approved(self) -> list:
        approved_file = self._get_memory_dir() / "approved.jsonl"
        items = []
        if approved_file.exists():
            with open(approved_file) as f:
                for line in f:
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        pass
        return items
    
    def _save_approved(self, items: list) -> None:
        approved_file = self._get_memory_dir() / "approved.jsonl"
        with open(approved_file, "w") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")
    
    def _get_approval_mode(self) -> bool:
        config = self.cli.config.get_merged_config()
        return config.get("memory_approval", True)
    
    def _set_approval_mode(self, enabled: bool) -> None:
        config_cmd = self.cli.commands.get("config")
        if config_cmd:
            config_cmd.execute(["set", "memory_approval", str(enabled).lower()])
    
    def _pending(self, parsed) -> CommandResult:
        items = self._load_pending()
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(items, indent=2))
        
        if not items:
            return CommandResult(success=True, output="No pending memory items.")
        
        lines = ["Pending Memory Items (awaiting approval):"]
        for item in items:
            lines.append(f"  [{item['id']}] {item['type']}: {item['content'][:80]}...")
            lines.append(f"      From: {item['session_id']} at {item['timestamp']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _approve(self, parsed) -> CommandResult:
        items = self._load_pending()
        item = next((i for i in items if i["id"] == parsed.item_id), None)
        
        if not item:
            return CommandResult(success=False, error=f"Pending item not found: {parsed.item_id}")
        
        # Move to approved
        items.remove(item)
        self._save_pending(items)
        
        approved = self._load_approved()
        item["approved_at"] = item.get("timestamp")  # Would use current time in real impl
        approved.append(item)
        self._save_approved(approved)
        
        # Notify memory provider
        self._notify_provider("approve", item)
        
        return CommandResult(success=True, output=f"Approved memory item: {parsed.item_id}")
    
    def _reject(self, parsed) -> CommandResult:
        items = self._load_pending()
        item = next((i for i in items if i["id"] == parsed.item_id), None)
        
        if not item:
            return CommandResult(success=False, error=f"Pending item not found: {parsed.item_id}")
        
        items.remove(item)
        self._save_pending(items)
        
        return CommandResult(success=True, output=f"Rejected memory item: {parsed.item_id}")
    
    def _approval(self, parsed) -> CommandResult:
        enabled = parsed.mode == "on"
        self._set_approval_mode(enabled)
        return CommandResult(success=True, output=f"Memory approval gate: {'enabled' if enabled else 'disabled'}")
    
    def _list(self, parsed) -> CommandResult:
        # Search across all configured providers
        all_items = []
        providers_to_search = [parsed.provider] if parsed.provider else list(self._providers.keys())
        
        for provider_name in providers_to_search:
            provider = self._get_provider(provider_name)
            if provider:
                # For listing, we'd need a way to get all items from provider
                # For now, fall back to local storage
                pass
        
        # Fallback to local storage for now
        items = self._load_approved()
        
        if parsed.provider:
            items = [i for i in items if i.get("provider") == parsed.provider]
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(items, indent=2))
        
        if not items:
            return CommandResult(success=True, output="No approved memory items.")
        
        lines = ["Approved Memory Items:"]
        for item in items:
            provider = item.get("provider", "local")
            lines.append(f"  [{item['id']}] ({provider}) {item['type']}: {item['content'][:80]}...")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _providers(self, parsed) -> CommandResult:
        providers = []
        for name, provider in self._provider_instances.items():
            health = provider.health_check()
            providers.append({
                "name": name,
                "description": provider.description,
                "available": True,
                "configured": True,
                "health": health,
            })
        
        # Add unavailable providers
        all_names = {"local", "sqlite", "vector", "byterover", "supermemory"}
        for name in all_names - set(self._provider_instances.keys()):
            provider_class = {
                "local": LocalMemoryProvider,
                "sqlite": SQLiteMemoryProvider,
                "vector": VectorMemoryProvider,
                "byterover": ByteRoverProvider,
                "supermemory": SupermemoryProvider,
            }[name]
            provider = provider_class()
            providers.append({
                "name": name,
                "description": provider.description,
                "available": provider.is_available(),
                "configured": False,
            })
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(providers, indent=2))
        
        lines = ["Memory Providers:"]
        for p in providers:
            status = "[green]available[/green]" if p["available"] else "[red]unavailable[/red]"
            configured = "[blue]configured[/blue]" if p["configured"] else ""
            lines.append(f"  {p['name']}  {status} {configured}")
            lines.append(f"    {p['description']}")
            if "health" in p:
                health = p["health"]
                lines.append(f"    Status: {health.get('status', 'unknown')}")
                if "item_count" in health:
                    lines.append(f"    Items: {health['item_count']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _sync(self, parsed) -> CommandResult:
        providers_to_sync = [parsed.provider] if parsed.provider else list(self._provider_instances.keys())
        results = []
        
        for provider_name in providers_to_sync:
            provider = self._get_provider(provider_name)
            if provider:
                health = provider.health_check()
                results.append(f"  {provider_name}: {health.get('status', 'unknown')}")
            else:
                results.append(f"  {provider_name}: not configured")
        
        return CommandResult(success=True, output="Syncing memory with providers:\n" + "\n".join(results))
    
    def _notify_provider(self, action: str, item: dict) -> None:
        # Placeholder - would call provider sync_turn
        pass


class RefineCommand(BaseCommand):
    """Trigger background memory/skill review."""
    
    name = "refine"
    description = "Trigger background memory and skill review"
    aliases = []
    
    def execute(self, args: list[str]) -> CommandResult:
        # Placeholder - would trigger curator/background review
        return CommandResult(success=True, output="Background refinement triggered (placeholder)")