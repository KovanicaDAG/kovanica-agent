"""
Unit tests for ConfigManager.
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, '/root/kovanica-agent')

from agent.cli.config import ConfigManager


class TestConfigManager:
    """Tests for ConfigManager class."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def config_manager(self, temp_dir):
        manager = ConfigManager()
        manager.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.project_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        return manager
    
    def test_get_default(self, config_manager):
        """Test getting default value for non-existent key."""
        value = config_manager.get("nonexistent_key", "default_value")
        assert value == "default_value"
    
    def test_set_and_get(self, config_manager):
        """Test setting and getting a value."""
        config_manager.set("test_key", "test_value")
        assert config_manager.get("test_key") == "test_value"
    
    def test_set_overwrites(self, config_manager):
        """Test that setting overwrites existing value."""
        config_manager.set("key", "value1")
        config_manager.set("key", "value2")
        assert config_manager.get("key") == "value2"
    
    def test_delete(self, config_manager):
        """Test deleting a key."""
        config_manager.set("key", "value")
        config_manager.delete("key")
        assert config_manager.get("key") is None
    
    def test_delete_nonexistent(self, config_manager):
        """Test deleting non-existent key doesn't error."""
        config_manager.delete("nonexistent")  # Should not raise
    
    def test_user_scope(self, config_manager):
        """Test user scope configuration."""
        config_manager.set("user_key", "user_value", scope="user")
        
        # Should be in user config
        with open(config_manager.user_config_path) as f:
            user_config = json.load(f)
        assert user_config["user_key"] == "user_value"
    
    def test_project_scope(self, config_manager):
        """Test project scope configuration."""
        config_manager.set("project_key", "project_value", scope="project")
        
        # Should be in project config
        with open(config_manager.project_config_path) as f:
            project_config = json.load(f)
        assert project_config["project_key"] == "project_value"
    
    def test_project_overrides_user(self, config_manager):
        """Test project config overrides user config."""
        config_manager.set("key", "user_value", scope="user")
        config_manager.set("key", "project_value", scope="project")
        
        # Project should override
        assert config_manager.get("key") == "project_value"
    
    def test_get_merged_config(self, config_manager):
        """Test getting merged configuration."""
        config_manager.set("user_only", "user_val", scope="user")
        config_manager.set("project_only", "project_val", scope="project")
        config_manager.set("both", "project_val", scope="project")
        config_manager.set("both", "user_val", scope="user")
        
        merged = config_manager.get_merged_config()
        
        assert merged["user_only"] == "user_val"
        assert merged["project_only"] == "project_val"
        assert merged["both"] == "project_val"  # Project overrides
    
    def test_list_config(self, config_manager):
        """Test listing configuration."""
        config_manager.set("key1", "val1", scope="user")
        config_manager.set("key2", "val2", scope="project")
        
        user_config = config_manager.get_user_config()
        project_config = config_manager.get_project_config()
        all_config = config_manager.get_merged_config()
        
        assert "key1" in user_config
        assert "key2" in project_config
        assert "key1" in all_config
        assert "key2" in all_config
    
    def test_reset_key(self, config_manager):
        """Test resetting a specific key."""
        config_manager.set("key", "value", scope="user")
        config_manager.delete("key", scope="user")
        
        assert config_manager.get("key") is None
    
    def test_reset_all(self, config_manager):
        """Test resetting all configuration."""
        config_manager.set("key1", "val1", scope="user")
        config_manager.set("key2", "val2", scope="project")
        
        config_manager.reset(scope="user")
        
        assert config_manager.get("key1") is None
        assert config_manager.get("key2") == "val2"  # Project not affected
    
    def test_persistence(self, temp_dir):
        """Test configuration persistence across instances."""
        # Create first manager with custom paths
        manager1 = ConfigManager()
        manager1.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager1.project_config_path = temp_dir / ".kovanica" / "settings.json"
        manager1.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        manager1._load_configs()  # Reload with new paths
        
        manager1.set("persistent_key", "persistent_value")
        
        # Create new manager with same paths
        manager2 = ConfigManager()
        manager2.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager2.project_config_path = temp_dir / ".kovanica" / "settings.json"
        manager2._load_configs()  # Reload with new paths
        
        assert manager2.get("persistent_key") == "persistent_value"


class TestConfigManagerEdgeCases:
    """Tests for edge cases in ConfigManager."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def config_manager(self, temp_dir):
        manager = ConfigManager()
        manager.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.project_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        yield manager
    
    def test_invalid_json_in_config_file(self, temp_dir):
        """Test handling of invalid JSON in config file."""
        manager = ConfigManager()
        manager.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write invalid JSON
        manager.user_config_path.write_text("invalid json")
        
        # Should not crash, should return empty dict
        manager._load_configs()
        assert manager._user_config == {}
    
    def test_empty_config_file(self, temp_dir):
        """Test empty config file."""
        manager = ConfigManager()
        manager.user_config_path = temp_dir / ".kovanica" / "settings.json"
        manager.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        manager.user_config_path.write_text("")
        
        # Should not crash
        manager._load_configs()
        assert manager._user_config == {}
    
    def test_special_characters_in_values(self, config_manager):
        """Test values with special characters."""
        special_value = "value with spaces, symbols: !@#$%^&*()"
        config_manager.set("special", special_value)
        
        assert config_manager.get("special") == special_value
    
    def test_unicode_values(self, config_manager):
        """Test unicode values."""
        unicode_value = "值 🎉 тест"
        config_manager.set("unicode", unicode_value)
        
        assert config_manager.get("unicode") == unicode_value
    
    def test_large_values(self, config_manager):
        """Test large values."""
        large_value = "x" * 10000
        config_manager.set("large", large_value)
        
        assert config_manager.get("large") == large_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])