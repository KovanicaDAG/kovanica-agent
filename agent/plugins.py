"""
Kovanica plugin registry — load skills, subagents, hooks, and MCP servers from plugin bundles.

Mirrors Claude Code's plugin system:
- Plugins are directories containing SKILL.md + optional subagents/, hooks/, mcp/
- Plugins can be loaded from a marketplace or from a local path
- Each plugin declares its own skills, subagents, hooks, and MCP servers
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import importlib.util
from pathlib import Path as _Path

HERE = _Path(__file__).resolve().parent.parent  # /root/kovanica-agent
AGENT_DIR = HERE
from dataclasses import dataclass
from typing import Any

# Plugin info
@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    path: str
    marketplace: str | None = None
    installed_at: str = ""


# Global plugin store
_PLUGINS: dict[str, PluginInfo] = {}
_PLUGINS_LOCK = threading.Lock()


def list_plugins() -> list[dict]:
    with _PLUGINS_LOCK:
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "path": p.path,
                "marketplace": p.marketplace,
                "installed_at": p.installed_at,
            }
            for p in _PLUGINS.values()
        ]


def load_plugin(plugin_path: str) -> dict:
    """Load a plugin from a directory containing plugin.json."""
    path = pathlib.Path(plugin_path)
    if not path.is_dir():
        return {"status": "error", "error": f"not a directory: {plugin_path}"}
    pj = path / "plugin.json"
    if not pj.is_file():
        return {"status": "error", "error": f"no plugin.json in {plugin_path}"}
    try:
        data = json.loads(pj.read_text())
    except Exception as e:
        return {"status": "error", "error": f"invalid plugin.json: {e}"}
    name = data.get("name", path.name)
    version = data.get("version", "0.1.0")
    description = data.get("description", "")
    with _PLUGINS_LOCK:
        if name in _PLUGINS:
            return {"status": "error", "error": f"plugin {name!r} already loaded"}
        _PLUGINS[name] = PluginInfo(
            name=name,
            version=version,
            description=description,
            path=str(path),
        )
    return {"status": "loaded", "name": name, "version": version}


def unload_plugin(plugin_name: str) -> dict:
    with _PLUGINS_LOCK:
        if plugin_name in _PLUGINS:
            del _PLUGINS[plugin_name]
            return {"status": "unloaded", "name": plugin_name}
        return {"status": "error", "error": f"plugin {plugin_name!r} not loaded"}


def plugin_skills(plugin_name: str) -> list[dict[str, str]]:
    """Return the skills declared by a plugin."""
    with _PLUGINS_LOCK:
        p = _PLUGINS.get(plugin_name)
        if p is None:
            return []
    base = pathlib.Path(p.path)
    skills_dir = base / "skills"
    if not skills_dir.is_dir():
        return []
    out = []
    for md in sorted(skills_dir.glob("*.md")):
        out.append({"name": md.stem, "path": str(md)})
    return out


def plugin_subagents(plugin_name: str) -> list[dict]:
    """Return the subagent definitions declared by a plugin."""
    with _PLUGINS_LOCK:
        p = _PLUGINS.get(plugin_name)
        if p is None:
            return []
    base = pathlib.Path(p.path)
    subagents_dir = base / "subagents"
    if not subagents_dir.is_dir():
        return []
    out = []
    for md in sorted(subagents_dir.glob("*.md")):
        try:
            text = md.read_text()
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    fm = text[3:end]
                    import yaml
                    data = yaml.safe_load(fm) or {}
                    out.append({"name": md.stem, "description": data.get("description", ""), "path": str(md)})
        except Exception:
            pass
    return out


def plugin_hooks(plugin_name: str) -> list[dict]:
    """Return the hooks declared by a plugin."""
    with _PLUGINS_LOCK:
        p = _PLUGINS.get(plugin_name)
        if p is None:
            return []
    base = pathlib.Path(p.path)
    hooks_dir = base / "hooks"
    if not hooks_dir.is_dir():
        return []
    out = []
    for py in sorted(hooks_dir.glob("*.py")):
        out.append({"name": py.stem, "path": str(py)})
    return out


def plugin_mcp_servers(plugin_name: str) -> list[dict]:
    """Return the MCP server configs declared by a plugin."""
    with _PLUGINS_LOCK:
        p = _PLUGINS.get(plugin_name)
        if p is None:
            return []
    base = pathlib.Path(p.path)
    mcp_dir = base / "mcp"
    if not mcp_dir.is_dir():
        return []
    out = []
    for cfg in sorted(mcp_dir.glob("*.json")):
        try:
            data = json.loads(cfg.read_text())
            out.append({"name": cfg.stem, "config": data})
        except Exception:
            pass
    return out


def install_plugin(plugin_name: str, repo_url: str = "") -> dict[str, Any]:
    """
    Stub for plugin marketplace install.

    Mirrors Codex plugin install: download a plugin from a git repo,
    verify its plugin.json, and load it. Currently a stub — the actual
    download/extraction is not yet wired.
    """
    if not plugin_name:
        return {"status": "error", "error": "plugin_name is required"}
    with _PLUGINS_LOCK:
        if plugin_name in _PLUGINS:
            return {"status": "error", "error": f"plugin {plugin_name!r} already loaded"}
    if not repo_url:
        return {
            "status": "stub",
            "message": f"install_plugin is a stub — no marketplace wired yet. "
                       f"To install {plugin_name!r} manually, place a plugin directory "
                       f"under {AGENT_DIR / 'plugins' / plugin_name} with a plugin.json "
                       f"and run 'kovi plugin load {AGENT_DIR / 'plugins' / plugin_name}'.",
            "plugin_name": plugin_name,
            "repo_url": repo_url,
        }
    return {
        "status": "stub",
        "message": f"install_plugin from {repo_url!r} is a stub — marketplace download not yet wired.",
        "plugin_name": plugin_name,
        "repo_url": repo_url,
    }
