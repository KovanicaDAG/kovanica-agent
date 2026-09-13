"""
Configuration manager for Kovanica CLI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class ConfigManager:
    """Manages configuration with user/project scope precedence."""
    
    def __init__(self):
        self.user_config_path = Path.home() / ".kovanica" / "settings.json"
        self.project_config_path = Path.cwd() / ".kovanica" / "settings.json"
        self._user_config: dict = {}
        self._project_config: dict = {}
        self._load_configs()
    
    def _load_configs(self) -> None:
        """Load user and project configs."""
        if self.user_config_path.exists():
            try:
                with open(self.user_config_path) as f:
                    self._user_config = json.load(f)
            except Exception:
                self._user_config = {}
        
        if self.project_config_path.exists():
            try:
                with open(self.project_config_path) as f:
                    self._project_config = json.load(f)
            except Exception:
                self._project_config = {}
    
    def _save_user_config(self) -> None:
        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.user_config_path, "w") as f:
            json.dump(self._user_config, f, indent=2)
    
    def _save_project_config(self) -> None:
        self.project_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.project_config_path, "w") as f:
            json.dump(self._project_config, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value (project overrides user)."""
        if key in self._project_config:
            return self._project_config[key]
        return self._user_config.get(key, default)
    
    def set(self, key: str, value: Any, scope: str = "user") -> None:
        """Set config value."""
        if scope == "project":
            self._project_config[key] = value
            self._save_project_config()
        else:
            self._user_config[key] = value
            self._save_user_config()
    
    def get_merged_config(self) -> dict:
        """Get merged config (project overrides user)."""
        return {**self._user_config, **self._project_config}
    
    def get_user_config(self) -> dict:
        return self._user_config.copy()
    
    def get_project_config(self) -> dict:
        return self._project_config.copy()
    
    def delete(self, key: str, scope: str = "user") -> bool:
        """Delete config key."""
        if scope == "project":
            if key in self._project_config:
                del self._project_config[key]
                self._save_project_config()
                return True
        else:
            if key in self._user_config:
                del self._user_config[key]
                self._save_user_config()
                return True
        return False
    
    def reset(self, scope: str = "user") -> None:
        """Reset all config for scope."""
        if scope == "project":
            self._project_config = {}
            self._save_project_config()
        else:
            self._user_config = {}
            self._save_user_config()