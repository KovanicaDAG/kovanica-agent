"""
Session management for Kovanica CLI.
"""
from __future__ import annotations

import json
import uuid
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class SessionManager:
    """Manages conversation sessions with persistence."""
    
    def __init__(self, config: "ConfigManager"):
        self.config = config
        self.current_id: Optional[str] = None
        self.current_session: dict = {}
        self.history: list = []
        self.heartbeats: list = []
        self.queue: list = []
        self.steer_guidance: Optional[str] = None
        self.current_goal: Optional[str] = None
        self.stop_requested: bool = False
        
        # Ensure sessions directory exists
        self.sessions_dir = Path.home() / ".kovanica" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Detect current worktree
        self.worktree_root = self._detect_worktree()
        self.worktree_name = self._get_worktree_name(self.worktree_root) if self.worktree_root else None
    
    def _detect_worktree(self) -> Optional[Path]:
        """Detect the current Git worktree root."""
        try:
            # Try to get the git worktree root
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return Path(result.stdout.strip())
        except Exception:
            pass
        return None
    
    def _get_worktree_name(self, worktree_root: Path) -> str:
        """Get a human-readable name for the worktree."""
        try:
            # Get the worktree name from git
            result = subprocess.run(
                ["git", "rev-parse", "--show-superproject-working-tree"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=worktree_root
            )
            if result.returncode == 0 and result.stdout.strip():
                # This is a linked worktree
                superproject = Path(result.stdout.strip())
                # Get the relative path from superproject
                try:
                    rel = worktree_root.relative_to(superproject)
                    return f"{superproject.name}/{rel}"
                except ValueError:
                    return worktree_root.name
            else:
                # This is the main worktree or not in a worktree
                return worktree_root.name
        except Exception:
            return worktree_root.name
    
    def get_worktree_info(self) -> dict:
        """Get current worktree information."""
        return {
            "root": str(self.worktree_root) if self.worktree_root else None,
            "name": self.worktree_name,
        }
    
    def load_session(self, session_id: str) -> bool:
        """Load a session by ID."""
        session_file = self.sessions_dir / f"{session_id}.jsonl"
        if not session_file.exists():
            return False
        
        try:
            with open(session_file) as f:
                lines = f.readlines()
            
            if not lines:
                return False
            
            meta = json.loads(lines[0])
            self.current_id = session_id
            self.current_session = meta
            self.history = []
            
            for line in lines[1:]:
                try:
                    self.history.append(json.loads(line))
                except Exception:
                    pass
            
            return True
        except Exception:
            return False
    
    def create_session(self, name: str = "New Session") -> str:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:8]
        session_file = self.sessions_dir / f"{session_id}.jsonl"
        
        meta = {
            "id": session_id,
            "title": name,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "turns": 0,
            "model": self.config.get("model", ""),
            "worktree": self.get_worktree_info(),
        }
        
        with open(session_file, "w") as f:
            f.write(json.dumps(meta) + "\n")
        
        self.current_id = session_id
        self.current_session = meta
        self.history = []
        
        return session_id
    
    def save_turn(self, role: str, content: str, metadata: dict = None) -> None:
        """Save a conversation turn."""
        if not self.current_id:
            self.create_session()
        
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            turn["metadata"] = metadata
        
        self.history.append(turn)
        
        # Update session file
        session_file = self.sessions_dir / f"{self.current_id}.jsonl"
        with open(session_file, "a") as f:
            f.write(json.dumps(turn) + "\n")
        
        # Update metadata
        self.current_session["turns"] = len(self.history)
        self.current_session["updated"] = datetime.now().isoformat()
        self._update_session_meta()
    
    def _update_session_meta(self) -> None:
        """Update session metadata in file."""
        if not self.current_id:
            return
        
        # Update worktree info in case it changed
        self.current_session["worktree"] = self.get_worktree_info()
        
        session_file = self.sessions_dir / f"{self.current_id}.jsonl"
        lines = [json.dumps(self.current_session)]
        for turn in self.history:
            lines.append(json.dumps(turn))
        
        with open(session_file, "w") as f:
            f.write("\n".join(lines) + "\n")
    
    def get_history(self, limit: int = 50) -> list:
        """Get conversation history."""
        return self.history[-limit:] if limit > 0 else self.history
    
    def get_current_session(self) -> dict:
        """Get current session metadata."""
        return self.current_session
    
    # Goal management
    def set_current_goal(self, goal_id: str) -> None:
        self.current_goal = goal_id
    
    def get_current_goal(self) -> Optional[str]:
        return self.current_goal
    
    def clear_current_goal(self) -> None:
        self.current_goal = None
    
    # Heartbeat management
    def get_heartbeats(self) -> list:
        return self.heartbeats
    
    def set_heartbeats(self, heartbeats: list) -> None:
        self.heartbeats = heartbeats
    
    # Queue management
    def get_queue(self) -> list:
        return self.queue
    
    def set_queue(self, queue: list) -> None:
        self.queue = queue
    
    # Steer guidance
    def set_steer_guidance(self, guidance: Optional[str]) -> None:
        self.steer_guidance = guidance
    
    def get_steer_guidance(self) -> Optional[str]:
        return self.steer_guidance
    
    # Stop control
    def request_stop(self) -> None:
        self.stop_requested = True
    
    def clear_stop(self) -> None:
        self.stop_requested = False
    
    def is_stop_requested(self) -> bool:
        return self.stop_requested