"""
Unit tests for SessionManager.
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, PropertyMock

import sys
sys.path.insert(0, '/root/kovanica-agent')

from agent.cli.session import SessionManager
from agent.cli.config import ConfigManager


class TestSessionManager:
    """Tests for SessionManager class."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def config_manager(self):
        return ConfigManager()
    
    @pytest.fixture
    def session_manager(self, config_manager, temp_dir):
        # Create a session manager with a custom sessions directory
        manager = SessionManager(config_manager)
        # Override the sessions_dir after initialization
        manager.sessions_dir = temp_dir / ".kovanica" / "sessions"
        manager.sessions_dir.mkdir(parents=True, exist_ok=True)
        return manager
    
    def test_create_session(self, session_manager):
        """Test creating a new session."""
        session_id = session_manager.create_session("Test Session")
        
        assert session_id is not None
        assert len(session_id) == 8
        assert session_manager.current_id == session_id
        assert session_manager.current_session["title"] == "Test Session"
        assert session_manager.current_session["turns"] == 0
    
    def test_create_session_default_name(self, session_manager):
        """Test creating session with default name."""
        session_id = session_manager.create_session()
        
        assert session_manager.current_session["title"] == "New Session"
    
    def test_load_session(self, session_manager):
        """Test loading an existing session."""
        # Create a session first
        original_id = session_manager.create_session("Original Session")
        session_manager.save_turn("user", "Hello")
        session_manager.save_turn("assistant", "Hi there")
        
        # Create new manager and load session
        new_manager = SessionManager(session_manager.config)
        new_manager.sessions_dir = session_manager.sessions_dir
        loaded = new_manager.load_session(original_id)
        
        assert loaded is True
        assert new_manager.current_id == original_id
        assert new_manager.current_session["title"] == "Original Session"
        assert len(new_manager.history) == 2
    
    def test_load_nonexistent_session(self, session_manager):
        """Test loading a non-existent session."""
        loaded = session_manager.load_session("nonexistent")
        assert loaded is False
    
    def test_save_turn(self, session_manager):
        """Test saving conversation turns."""
        session_manager.create_session()
        
        session_manager.save_turn("user", "Hello")
        session_manager.save_turn("assistant", "Hi there")
        
        assert len(session_manager.history) == 2
        assert session_manager.history[0]["role"] == "user"
        assert session_manager.history[0]["content"] == "Hello"
        assert session_manager.history[1]["role"] == "assistant"
        assert session_manager.history[1]["content"] == "Hi there"
    
    def test_get_history(self, session_manager):
        """Test getting conversation history."""
        session_manager.create_session()
        session_manager.save_turn("user", "Message 1")
        session_manager.save_turn("assistant", "Reply 1")
        session_manager.save_turn("user", "Message 2")
        
        history = session_manager.get_history(limit=2)
        assert len(history) == 2
        assert history[0]["content"] == "Reply 1"
        assert history[1]["content"] == "Message 2"
    
    def test_goal_management(self, session_manager):
        """Test goal management functions."""
        session_manager.create_session()
        
        # Set goal
        session_manager.set_current_goal("goal-123")
        assert session_manager.get_current_goal() == "goal-123"
        
        # Clear goal
        session_manager.clear_current_goal()
        assert session_manager.get_current_goal() is None
    
    def test_heartbeat_management(self, session_manager):
        """Test heartbeat management."""
        heartbeats = [{"id": "hb1", "interval": "30s", "prompt": "Check"}]
        session_manager.set_heartbeats(heartbeats)
        
        retrieved = session_manager.get_heartbeats()
        assert len(retrieved) == 1
        assert retrieved[0]["id"] == "hb1"
    
    def test_queue_management(self, session_manager):
        """Test queue management."""
        queue = ["task1", "task2"]
        session_manager.set_queue(queue)
        
        retrieved = session_manager.get_queue()
        assert retrieved == queue
    
    def test_steer_guidance(self, session_manager):
        """Test steer guidance."""
        session_manager.set_steer_guidance("Focus on testing")
        assert session_manager.get_steer_guidance() == "Focus on testing"
        
        session_manager.set_steer_guidance(None)
        assert session_manager.get_steer_guidance() is None
    
    def test_stop_control(self, session_manager):
        """Test stop control."""
        assert session_manager.is_stop_requested() is False
        
        session_manager.request_stop()
        assert session_manager.is_stop_requested() is True
        
        session_manager.clear_stop()
        assert session_manager.is_stop_requested() is False
    
    def test_worktree_detection(self, session_manager):
        """Test worktree detection."""
        info = session_manager.get_worktree_info()
        assert "root" in info
        assert "name" in info
    
    def test_session_persistence(self, session_manager, temp_dir):
        """Test session metadata persistence."""
        session_id = session_manager.create_session("Persistent Session")
        session_manager.save_turn("user", "Test message")
        
        # Create new manager with same directory
        new_manager = SessionManager(session_manager.config)
        new_manager.sessions_dir = temp_dir / ".kovanica" / "sessions"
        loaded = new_manager.load_session(session_id)
        
        assert loaded is True
        assert new_manager.current_session["title"] == "Persistent Session"
        assert new_manager.current_session["turns"] == 1


class TestSessionManagerWorktree:
    """Tests for worktree-aware session management."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def config_manager(self):
        return ConfigManager()
    
    @pytest.fixture
    def session_manager(self, config_manager, temp_dir):
        manager = SessionManager(config_manager)
        manager.sessions_dir = temp_dir / ".kovanica" / "sessions"
        manager.sessions_dir.mkdir(parents=True, exist_ok=True)
        return manager
    
    def test_session_worktree_info(self, session_manager):
        """Test session includes worktree info."""
        session_id = session_manager.create_session("Worktree Session")
        
        assert "worktree" in session_manager.current_session
        assert "root" in session_manager.current_session["worktree"]
        assert "name" in session_manager.current_session["worktree"]
    
    def test_session_fork_updates_worktree(self, session_manager):
        """Test forking session updates worktree to current."""
        session_manager.create_session("Original")
        session_manager.save_turn("user", "Hello")
        
        # Fork the session
        import uuid
        new_id = str(uuid.uuid4())[:8]
        new_file = session_manager.sessions_dir / f"{new_id}.jsonl"
        
        with open(session_manager.sessions_dir / f"{session_manager.current_id}.jsonl") as f:
            lines = f.readlines()
        
        meta = json.loads(lines[0])
        new_meta = meta.copy()
        new_meta["id"] = new_id
        new_meta["forked_from"] = session_manager.current_id
        new_meta["worktree"] = session_manager.get_worktree_info()
        
        with open(new_file, "w") as f:
            f.write(json.dumps(new_meta) + "\n")
            f.writelines(lines[1:])
        
        # Load forked session
        session_manager.load_session(new_id)
        assert session_manager.current_session["worktree"] == session_manager.get_worktree_info()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])