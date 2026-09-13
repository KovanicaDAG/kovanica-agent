"""
Theme management for Kovanica CLI.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None


class ThemeManager:
    """Manages UI themes with YAML configuration."""
    
    # Built-in themes
    BUILTIN_THEMES = {
        "default": {
            "name": "default",
            "palette": {
                "background": {"hex": "#1a1b26", "alpha": 1.0},
                "midground": {"hex": "#7aa2f7", "alpha": 1.0},
                "foreground": {"hex": "#c0caf5", "alpha": 1.0},
            },
            "colors": {
                "primary": "#7aa2f7",
                "accent": "#bb9af7",
                "success": "#9ece6a",
                "warning": "#e0af68",
                "error": "#f7768e",
                "muted": "#565f89",
            },
        },
        "dark": {
            "name": "dark",
            "palette": {
                "background": {"hex": "#0d1117", "alpha": 1.0},
                "midground": {"hex": "#58a6ff", "alpha": 1.0},
                "foreground": {"hex": "#e6edf3", "alpha": 1.0},
            },
            "colors": {
                "primary": "#58a6ff",
                "accent": "#a371f7",
                "success": "#3fb950",
                "warning": "#d29922",
                "error": "#f85149",
                "muted": "#8b949e",
            },
        },
        "light": {
            "name": "light",
            "palette": {
                "background": {"hex": "#ffffff", "alpha": 1.0},
                "midground": {"hex": "#0969da", "alpha": 1.0},
                "foreground": {"hex": "#24292f", "alpha": 1.0},
            },
            "colors": {
                "primary": "#0969da",
                "accent": "#8250df",
                "success": "#2da44e",
                "warning": "#9a6700",
                "error": "#cf222e",
                "muted": "#656d76",
            },
        },
        "tokyonight": {
            "name": "tokyonight",
            "palette": {
                "background": {"hex": "#1a1b26", "alpha": 1.0},
                "midground": {"hex": "#7aa2f7", "alpha": 1.0},
                "foreground": {"hex": "#c0caf5", "alpha": 1.0},
            },
            "colors": {
                "primary": "#7aa2f7",
                "accent": "#bb9af7",
                "success": "#9ece6a",
                "warning": "#e0af68",
                "error": "#f7768e",
                "muted": "#565f89",
            },
        },
        "grokday": {
            "name": "grokday",
            "palette": {
                "background": {"hex": "#fafafa", "alpha": 1.0},
                "midground": {"hex": "#1a1a2e", "alpha": 1.0},
                "foreground": {"hex": "#16161d", "alpha": 1.0},
            },
            "colors": {
                "primary": "#1a1a2e",
                "accent": "#e94560",
                "success": "#0f3460",
                "warning": "#e94560",
                "error": "#e94560",
                "muted": "#6b6b8a",
            },
        },
        "rosepinemoon": {
            "name": "rosepinemoon",
            "palette": {
                "background": {"hex": "#232136", "alpha": 1.0},
                "midground": {"hex": "#ebbcba", "alpha": 1.0},
                "foreground": {"hex": "#e0def4", "alpha": 1.0},
            },
            "colors": {
                "primary": "#ebbcba",
                "accent": "#f6c177",
                "success": "#3e8fb0",
                "warning": "#f6c177",
                "error": "#eb6f92",
                "muted": "#6e6a86",
            },
        },
        "oscuramidnight": {
            "name": "oscuramidnight",
            "palette": {
                "background": {"hex": "#0a0e17", "alpha": 1.0},
                "midground": {"hex": "#00d4aa", "alpha": 1.0},
                "foreground": {"hex": "#e8eaed", "alpha": 1.0},
            },
            "colors": {
                "primary": "#00d4aa",
                "accent": "#ff6b6b",
                "success": "#00d4aa",
                "warning": "#ffd93d",
                "error": "#ff6b6b",
                "muted": "#4a5568",
            },
        },
    }
    
    def __init__(self, config: "ConfigManager"):
        self.config = config
        self.current_theme: dict = {}
        self.themes_dir = Path.home() / ".kovanica" / "themes"
        self.themes_dir.mkdir(parents=True, exist_ok=True)
        
        # Load initial theme
        theme_name = config.get("theme", "default")
        self.load_theme(theme_name)
    
    def load_theme(self, name: str) -> bool:
        """Load a theme by name."""
        # Check built-in themes first
        if name in self.BUILTIN_THEMES:
            self.current_theme = self.BUILTIN_THEMES[name].copy()
            self.config.set("theme", name)
            return True
        
        # Check custom themes
        theme_file = self.themes_dir / f"{name}.yaml"
        if theme_file.exists() and yaml:
            try:
                with open(theme_file) as f:
                    theme = yaml.safe_load(f)
                if theme and "name" in theme:
                    self.current_theme = theme
                    self.config.set("theme", name)
                    return True
            except Exception:
                pass
        
        # Fallback to default
        self.current_theme = self.BUILTIN_THEMES["default"].copy()
        return False
    
    def get_theme(self) -> dict:
        """Get current theme."""
        return self.current_theme
    
    def get_color(self, name: str) -> str:
        """Get a color from the current theme."""
        return self.current_theme.get("colors", {}).get(name, "#ffffff")
    
    def get_palette(self) -> dict:
        """Get the color palette."""
        return self.current_theme.get("palette", {})
    
    def list_themes(self) -> list[str]:
        """List all available themes."""
        builtin = list(self.BUILTIN_THEMES.keys())
        custom = []
        if self.themes_dir.exists():
            custom = [f.stem for f in self.themes_dir.glob("*.yaml")]
        return builtin + custom
    
    def save_custom_theme(self, name: str, theme: dict) -> bool:
        """Save a custom theme."""
        if not yaml:
            return False
        
        theme_file = self.themes_dir / f"{name}.yaml"
        try:
            with open(theme_file, "w") as f:
                yaml.dump(theme, f, default_flow_style=False)
            return True
        except Exception:
            return False
    
    def apply_to_rich_console(self, console) -> None:
        """Apply theme to a Rich console."""
        # This would configure Rich's theme
        # For now, just a placeholder
        pass