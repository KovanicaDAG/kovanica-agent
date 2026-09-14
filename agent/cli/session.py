"""
Session management for Kovanica CLI.
"""
from __future__ import annotations

import json
import uuid
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable


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
        
        # Background task support
        self._bg_tasks: dict[str, threading.Thread] = {}
        self._bg_stop_events: dict[str, threading.Event] = {}
        self._bg_lock = threading.Lock()
        
        # Auto-continue state
        self.auto_continue_active: bool = False
        self.auto_continue_goal_id: Optional[str] = None
        
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
            "goals": [],
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
    
    # Background task management
    def start_background_task(self, task_id: str, target: Callable, *args, **kwargs) -> bool:
        """Start a background task."""
        with self._bg_lock:
            if task_id in self._bg_tasks:
                return False  # Already running
            
            stop_event = threading.Event()
            thread = threading.Thread(target=target, args=(stop_event,) + args, kwargs=kwargs, daemon=True)
            
            self._bg_stop_events[task_id] = stop_event
            self._bg_tasks[task_id] = thread
            thread.start()
            return True
    
    def stop_background_task(self, task_id: str) -> bool:
        """Stop a background task."""
        with self._bg_lock:
            if task_id not in self._bg_tasks:
                return False
            
            self._bg_stop_events[task_id].set()
            thread = self._bg_tasks.pop(task_id)
            self._bg_stop_events.pop(task_id)
            
            # Wait for thread to finish (with timeout)
            thread.join(timeout=2.0)
            return True
    
    def stop_all_background_tasks(self) -> None:
        """Stop all background tasks."""
        with self._bg_lock:
            for task_id in list(self._bg_tasks.keys()):
                self._bg_stop_events[task_id].set()
            
            for task_id, thread in self._bg_tasks.items():
                thread.join(timeout=2.0)
            
            self._bg_tasks.clear()
            self._bg_stop_events.clear()
    
    def is_background_task_running(self, task_id: str) -> bool:
        """Check if a background task is running."""
        with self._bg_lock:
            return task_id in self._bg_tasks
    
    # Heartbeat runner
    def _run_heartbeat(self, stop_event: threading.Event, heartbeat_id: str, interval_seconds: float, prompt: str) -> None:
        """Background task to send heartbeat prompts at intervals."""
        while not stop_event.is_set():
            # Wait for interval or stop
            if stop_event.wait(timeout=interval_seconds):
                break
            
            # Check if session is still active
            if not self.current_id:
                break
            
            # Add heartbeat prompt to queue for next turn
            self.queue.append(f"[Heartbeat {heartbeat_id}] {prompt}")
    
    def start_heartbeat(self, heartbeat_id: str, interval_seconds: float, prompt: str) -> bool:
        """Start a heartbeat background task."""
        task_id = f"heartbeat_{heartbeat_id}"
        return self.start_background_task(task_id, self._run_heartbeat, heartbeat_id, interval_seconds, prompt)
    
    def stop_heartbeat(self, heartbeat_id: str) -> bool:
        """Stop a heartbeat background task."""
        task_id = f"heartbeat_{heartbeat_id}"
        return self.stop_background_task(task_id)
    
    # Auto-continue for goals
    def set_auto_continue(self, goal_id: str, active: bool) -> None:
        """Enable/disable auto-continue for a goal."""
        self.auto_continue_active = active
        self.auto_continue_goal_id = goal_id if active else None
    
    def is_auto_continue_active(self) -> bool:
        return self.auto_continue_active
    
    def get_auto_continue_goal(self) -> Optional[str]:
        return self.auto_continue_goal_id
    
    # Parse interval string (e.g., "30s", "5m", "1h")
    @staticmethod
    def parse_interval(interval_str: str) -> float:
        """Parse interval string to seconds."""
        interval_str = interval_str.strip().lower()
        if interval_str.endswith('s'):
            return float(interval_str[:-1])
        elif interval_str.endswith('m'):
            return float(interval_str[:-1]) * 60
        elif interval_str.endswith('h'):
            return float(interval_str[:-1]) * 3600
        else:
            # Default to seconds
            return float(interval_str)