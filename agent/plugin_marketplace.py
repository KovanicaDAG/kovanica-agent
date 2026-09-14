"""
Plugin Marketplace for Kovanica CLI.

Provides plugin discovery, installation, version management, and dependency resolution.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin


@dataclass
class PluginManifest:
    """Plugin manifest (plugin.json)."""
    name: str
    version: str
    description: str
    author: str
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    keywords: List[str] = None
    dependencies: Dict[str, str] = None  # plugin_name -> version_range
    kovanica_version: str = ">=0.2.0"
    entry_points: Dict[str, str] = None  # command_name -> module:function
    commands: List[str] = None  # List of command names
    hooks: Dict[str, List[str]] = None  # event -> list of handler paths
    mcp_servers: Dict[str, Any] = None
    assets: List[str] = None  # Additional files to include
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if self.dependencies is None:
            self.dependencies = {}
        if self.entry_points is None:
            self.entry_points = {}
        if self.commands is None:
            self.commands = []
        if self.hooks is None:
            self.hooks = {}
        if self.mcp_servers is None:
            self.mcp_servers = {}
        if self.assets is None:
            self.assets = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(**data)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "PluginManifest":
        return cls.from_dict(json.loads(json_str))
    
    def get_hash(self) -> str:
        """Get content hash for integrity verification."""
        content = self.to_json().encode()
        return hashlib.sha256(content).hexdigest()[:16]


@dataclass
class PluginIndexEntry:
    """Entry in the plugin index."""
    name: str
    version: str
    description: str
    author: str
    homepage: str
    repository: str
    keywords: List[str]
    download_url: str
    sha256: str
    size: int
    published_at: str
    kovanica_version: str
    dependencies: Dict[str, str]


class PluginRegistry:
    """Plugin registry for discovery and metadata."""
    
    def __init__(self, registry_url: str = "https://registry.kovanica.dev"):
        self.registry_url = registry_url.rstrip("/")
        self.cache_dir = Path.home() / ".kovanica" / "plugin_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.cache_dir / "index.json"
        self.index: Dict[str, List[PluginIndexEntry]] = {}
        self._load_index()
    
    def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                with open(self.index_file) as f:
                    data = json.load(f)
                    for name, entries in data.items():
                        self.index[name] = [PluginIndexEntry(**e) for e in entries]
            except Exception:
                self.index = {}
    
    def _save_index(self) -> None:
        data = {}
        for name, entries in self.index.items():
            data[name] = [asdict(e) for e in entries]
        with open(self.index_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def refresh_index(self) -> bool:
        """Fetch latest index from registry."""
        try:
            url = f"{self.registry_url}/index.json"
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode())
                self.index = {}
                for name, entries in data.items():
                    self.index[name] = [PluginIndexEntry(**e) for e in entries]
                self._save_index()
                return True
        except Exception as e:
            print(f"Failed to refresh index: {e}")
            return False
    
    def search(self, query: str = "", keywords: List[str] = None, author: str = None) -> List[PluginIndexEntry]:
        """Search plugins in index."""
        results = []
        query_lower = query.lower()
        
        for name, entries in self.index.items():
            for entry in entries:
                if query and query_lower not in name.lower() and query_lower not in entry.description.lower():
                    continue
                if keywords and not any(k.lower() in [kw.lower() for kw in entry.keywords] for k in keywords):
                    continue
                if author and author.lower() not in entry.author.lower():
                    continue
                results.append(entry)
        
        # Sort by relevance (exact name match first, then description match)
        results.sort(key=lambda e: (0 if query_lower == e.name.lower() else 1, e.name))
        return results
    
    def get_latest_version(self, name: str) -> Optional[PluginIndexEntry]:
        """Get latest version of a plugin."""
        entries = self.index.get(name, [])
        if not entries:
            return None
        # Sort by version (semver)
        entries.sort(key=lambda e: self._parse_version(e.version), reverse=True)
        return entries[0]
    
    def get_version(self, name: str, version: str) -> Optional[PluginIndexEntry]:
        """Get specific version of a plugin."""
        entries = self.index.get(name, [])
        for entry in entries:
            if entry.version == version:
                return entry
        return None
    
    def get_all_versions(self, name: str) -> List[PluginIndexEntry]:
        """Get all versions of a plugin."""
        entries = self.index.get(name, [])
        entries.sort(key=lambda e: self._parse_version(e.version), reverse=True)
        return entries
    
    def _parse_version(self, version: str) -> tuple:
        """Parse semver string to tuple for comparison."""
        parts = version.lstrip("v").split(".")
        nums = []
        for part in parts:
            # Handle pre-release suffixes
            num = ""
            for ch in part:
                if ch.isdigit():
                    num += ch
                else:
                    break
            nums.append(int(num) if num else 0)
        return tuple(nums)


class PluginManager:
    """Manages plugin installation, updates, and removal."""
    
    def __init__(self, registry: PluginRegistry = None):
        self.registry = registry or PluginRegistry()
        self.plugins_dir = Path.home() / ".kovanica" / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.installed_file = self.plugins_dir / "installed.json"
        self.installed: Dict[str, Dict[str, Any]] = {}
        self._load_installed()
    
    def _load_installed(self) -> None:
        if self.installed_file.exists():
            try:
                with open(self.installed_file) as f:
                    self.installed = json.load(f)
            except Exception:
                self.installed = {}
    
    def _save_installed(self) -> None:
        with open(self.installed_file, "w") as f:
            json.dump(self.installed, f, indent=2)
    
    def is_installed(self, name: str) -> bool:
        return name in self.installed
    
    def get_installed_version(self, name: str) -> Optional[str]:
        if name in self.installed:
            return self.installed[name].get("version")
        return None
    
    def list_installed(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "version": info["version"],
                "description": info.get("description", ""),
                "installed_at": info.get("installed_at"),
                "enabled": info.get("enabled", True),
                "path": info.get("path"),
            }
            for name, info in self.installed.items()
        ]
    
    def install(self, name: str, version: str = None, force: bool = False) -> bool:
        """Install a plugin."""
        # Check if already installed
        if self.is_installed(name) and not force:
            current = self.get_installed_version(name)
            if version is None or current == version:
                print(f"Plugin {name} v{current} already installed")
                return True
        
        # Get version info from registry
        if version:
            entry = self.registry.get_version(name, version)
        else:
            entry = self.registry.get_latest_version(name)
        
        if not entry:
            print(f"Plugin {name} not found in registry")
            return False
        
        # Check dependencies
        if not self._check_dependencies(entry.dependencies):
            print(f"Dependency check failed for {name}")
            return False
        
        # Download plugin
        plugin_dir = self.plugins_dir / name
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        
        try:
            print(f"Downloading {name} v{entry.version}...")
            with tempfile.TemporaryDirectory() as tmpdir:
                archive_path = Path(tmpdir) / f"{name}-{entry.version}.tar.gz"
                urllib.request.urlretrieve(entry.download_url, archive_path)
                
                # Verify checksum
                with open(archive_path, "rb") as f:
                    actual_sha256 = hashlib.sha256(f.read()).hexdigest()
                if actual_sha256 != entry.sha256:
                    print(f"Checksum mismatch for {name}")
                    return False
                
                # Extract
                import tarfile
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(plugin_dir)
                
                # Verify manifest
                manifest_path = plugin_dir / "plugin.json"
                if not manifest_path.exists():
                    print(f"Missing plugin.json in {name}")
                    shutil.rmtree(plugin_dir)
                    return False
                
                with open(manifest_path) as f:
                    manifest = PluginManifest.from_json(f.read())
                
                if manifest.name != name:
                    print(f"Manifest name mismatch: {manifest.name} != {name}")
                    shutil.rmtree(plugin_dir)
                    return False
                
                # Install dependencies first
                for dep_name, dep_version in entry.dependencies.items():
                    if not self.is_installed(dep_name):
                        print(f"Installing dependency: {dep_name} {dep_version}")
                        if not self.install(dep_name, dep_version):
                            print(f"Failed to install dependency {dep_name}")
                            shutil.rmtree(plugin_dir)
                            return False
                
                # Register as installed
                self.installed[name] = {
                    "version": entry.version,
                    "description": entry.description,
                    "installed_at": datetime.now().isoformat(),
                    "enabled": True,
                    "path": str(plugin_dir),
                    "manifest": manifest.to_dict(),
                    "checksum": entry.sha256,
                }
                self._save_installed()
                
                print(f"Successfully installed {name} v{entry.version}")
                return True
                
        except Exception as e:
            print(f"Installation failed: {e}")
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            return False
    
    def _check_dependencies(self, dependencies: Dict[str, str]) -> bool:
        """Check if all dependencies are satisfied."""
        for dep_name, dep_version in dependencies.items():
            if not self.is_installed(dep_name):
                return False
            # Version check would go here
        return True
    
    def uninstall(self, name: str, force: bool = False) -> bool:
        """Uninstall a plugin."""
        if not self.is_installed(name):
            print(f"Plugin {name} not installed")
            return False
        
        # Check if other plugins depend on this
        dependents = self._get_dependents(name)
        if dependents and not force:
            print(f"Plugin {name} is required by: {', '.join(dependents)}")
            print("Use --force to uninstall anyway")
            return False
        
        # Remove plugin directory
        plugin_dir = self.plugins_dir / name
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        
        # Remove from installed
        del self.installed[name]
        self._save_installed()
        
        print(f"Uninstalled {name}")
        return True
    
    def _get_dependents(self, name: str) -> List[str]:
        """Get list of plugins that depend on this plugin."""
        dependents = []
        for plugin_name, info in self.installed.items():
            manifest = info.get("manifest", {})
            deps = manifest.get("dependencies", {})
            if name in deps:
                dependents.append(plugin_name)
        return dependents
    
    def update(self, name: str, version: str = None) -> bool:
        """Update a plugin to latest or specific version."""
        if not self.is_installed(name):
            print(f"Plugin {name} not installed")
            return False
        
        current_version = self.get_installed_version(name)
        
        if version:
            entry = self.registry.get_version(name, version)
        else:
            entry = self.registry.get_latest_version(name)
        
        if not entry:
            print(f"Version not found for {name}")
            return False
        
        if entry.version == current_version:
            print(f"Already at latest version: {current_version}")
            return True
        
        print(f"Updating {name} from v{current_version} to v{entry.version}...")
        return self.install(name, entry.version, force=True)
    
    def enable(self, name: str) -> bool:
        """Enable a plugin."""
        if not self.is_installed(name):
            print(f"Plugin {name} not installed")
            return False
        
        self.installed[name]["enabled"] = True
        self._save_installed()
        print(f"Enabled {name}")
        return True
    
    def disable(self, name: str) -> bool:
        """Disable a plugin."""
        if not self.is_installed(name):
            print(f"Plugin {name} not installed")
            return False
        
        self.installed[name]["enabled"] = False
        self._save_installed()
        print(f"Disabled {name}")
        return True
    
    def get_plugin_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about installed plugin."""
        if not self.is_installed(name):
            return None
        
        info = self.installed[name].copy()
        plugin_dir = Path(info["path"])
        manifest_path = plugin_dir / "plugin.json"
        
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            info["manifest"] = manifest
        
        return info


class PluginMarketplaceCLI:
    """CLI interface for plugin marketplace."""
    
    def __init__(self):
        self.registry = PluginRegistry()
        self.manager = PluginManager(self.registry)
    
    def search(self, query: str = "", keywords: List[str] = None, author: str = None, json_output: bool = False) -> None:
        """Search for plugins."""
        self.registry.refresh_index()
        results = self.registry.search(query, keywords, author)
        
        if json_output:
            print(json.dumps([asdict(r) for r in results], indent=2))
            return
        
        if not results:
            print("No plugins found.")
            return
        
        print(f"Found {len(results)} plugin(s):")
        for entry in results:
            installed = " [installed]" if self.manager.is_installed(entry.name) else ""
            print(f"  {entry.name} v{entry.version}{installed}")
            print(f"    {entry.description}")
            print(f"    Author: {entry.author} | Keywords: {', '.join(entry.keywords)}")
            print()
    
    def install(self, name: str, version: str = None, force: bool = False) -> bool:
        return self.manager.install(name, version, force)
    
    def uninstall(self, name: str, force: bool = False) -> bool:
        return self.manager.uninstall(name, force)
    
    def update(self, name: str, version: str = None) -> bool:
        return self.manager.update(name, version)
    
    def list_installed(self, json_output: bool = False) -> None:
        installed = self.manager.list_installed()
        
        if json_output:
            print(json.dumps(installed, indent=2))
            return
        
        if not installed:
            print("No plugins installed.")
            return
        
        print("Installed Plugins:")
        for plugin in installed:
            status = "[green]enabled[/green]" if plugin["enabled"] else "[red]disabled[/red]"
            print(f"  {plugin['name']} v{plugin['version']}  {status}")
            print(f"    {plugin['description']}")
            print(f"    Installed: {plugin['installed_at']}")
            print()
    
    def enable(self, name: str) -> bool:
        return self.manager.enable(name)
    
    def disable(self, name: str) -> bool:
        return self.manager.disable(name)
    
    def info(self, name: str, json_output: bool = False) -> None:
        info = self.manager.get_plugin_info(name)
        if not info:
            print(f"Plugin {name} not installed")
            return
        
        if json_output:
            print(json.dumps(info, indent=2))
            return
        
        print(f"Plugin: {name}")
        print(f"Version: {info['version']}")
        print(f"Description: {info['description']}")
        print(f"Installed: {info['installed_at']}")
        print(f"Enabled: {info['enabled']}")
        print(f"Path: {info['path']}")
        
        manifest = info.get("manifest", {})
        if manifest:
            print(f"\nManifest:")
            print(f"  Author: {manifest.get('author', 'Unknown')}")
            print(f"  License: {manifest.get('license', 'Unknown')}")
            print(f"  Homepage: {manifest.get('homepage', 'None')}")
            print(f"  Repository: {manifest.get('repository', 'None')}")
            print(f"  Keywords: {', '.join(manifest.get('keywords', []))}")
            print(f"  Commands: {', '.join(manifest.get('commands', []))}")
            print(f"  Dependencies: {manifest.get('dependencies', {})}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica Plugin Marketplace")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # search
    search_parser = subparsers.add_parser("search", help="Search for plugins")
    search_parser.add_argument("query", nargs="?", default="", help="Search query")
    search_parser.add_argument("--keywords", nargs="+", help="Filter by keywords")
    search_parser.add_argument("--author", help="Filter by author")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # install
    install_parser = subparsers.add_parser("install", help="Install a plugin")
    install_parser.add_argument("name", help="Plugin name")
    install_parser.add_argument("--version", help="Specific version")
    install_parser.add_argument("--force", action="store_true", help="Force reinstall")
    
    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall a plugin")
    uninstall_parser.add_argument("name", help="Plugin name")
    uninstall_parser.add_argument("--force", action="store_true", help="Force uninstall even if depended on")
    
    # update
    update_parser = subparsers.add_parser("update", help="Update a plugin")
    update_parser.add_argument("name", help="Plugin name")
    update_parser.add_argument("--version", help="Specific version")
    
    # list
    list_parser = subparsers.add_parser("list", help="List installed plugins")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # enable/disable
    enable_parser = subparsers.add_parser("enable", help="Enable a plugin")
    enable_parser.add_argument("name", help="Plugin name")
    
    disable_parser = subparsers.add_parser("disable", help="Disable a plugin")
    disable_parser.add_argument("name", help="Plugin name")
    
    # info
    info_parser = subparsers.add_parser("info", help="Show plugin info")
    info_parser.add_argument("name", help="Plugin name")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # refresh
    refresh_parser = subparsers.add_parser("refresh", help="Refresh plugin index")
    
    args = parser.parse_args()
    
    cli = PluginMarketplaceCLI()
    
    if args.command == "search":
        cli.search(args.query, args.keywords, args.author, args.json)
    elif args.command == "install":
        cli.install(args.name, args.version, args.force)
    elif args.command == "uninstall":
        cli.uninstall(args.name, args.force)
    elif args.command == "update":
        cli.update(args.name, args.version)
    elif args.command == "list":
        cli.list_installed(args.json)
    elif args.command == "enable":
        cli.enable(args.name)
    elif args.command == "disable":
        cli.disable(args.name)
    elif args.command == "info":
        cli.info(args.name, args.json)
    elif args.command == "refresh":
        if cli.registry.refresh_index():
            print("Plugin index refreshed")
        else:
            print("Failed to refresh index")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()