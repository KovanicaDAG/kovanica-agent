"""
Enhanced observability and analytics for Kovanica Agent.
Provides advanced analytics, usage reporting, and business intelligence.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
import threading
import sqlite3
from enum import Enum


class EventType(Enum):
    """Types of events that can be tracked for analytics."""
    CHAT_MESSAGE = "chat_message"
    TOOL_USE = "tool_use"
    SUBAGENT_SPAWN = "subagent_spawn"
    SUBAGENT_COMPLETE = "subagent_complete"
    PATCH_PROPOSED = "patch_proposed"
    PATCH_APPROVED = "patch_approved"
    PATCH_REJECTED = "patch_rejected"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    CARGO_COMMAND = "cargo_command"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class AnalyticsEvent:
    """An analytics event for tracking user behavior and system usage."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    user_id: str = ""  # For multi-user support
    event_type: EventType = EventType.CHAT_MESSAGE
    agent_role: str = "user"  # dev or user
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "event_type": self.event_type.value,
            "agent_role": self.agent_role,
            "properties": json.dumps(self.properties),
            "metadata": json.dumps(self.metadata)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalyticsEvent':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            session_id=data["session_id"],
            user_id=data["user_id"],
            event_type=EventType(data["event_type"]),
            agent_role=data["agent_role"],
            properties=json.loads(data["properties"]) if data["properties"] else {},
            metadata=json.loads(data["metadata"]) if data["metadata"] else {}
        )


@dataclass
class UserInfo:
    """Information about a user in the system."""
    user_id: str
    username: str
    email: str = ""
    role: str = "user"  # user, dev, admin
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserInfo':
        return cls(**data)


@dataclass
class TeamInfo:
    """Information about a team/organization."""
    team_id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = ""  # user_id of creator
    members: List[str] = field(default_factory=list)  # user_ids
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TeamInfo':
        return cls(**data)


class AnalyticsDatabase:
    """Manages the analytics database for storing events and user/team info."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or Path.home() / ".kovanica" / "analytics.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    properties TEXT,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    metadata TEXT,
                    FOREIGN KEY (created_by) REFERENCES users (user_id)
                );
                
                CREATE TABLE IF NOT EXISTS team_members (
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (team_id, user_id),
                    FOREIGN KEY (team_id) REFERENCES teams (team_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON analytics_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_session ON analytics_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_events_user ON analytics_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_events_type ON analytics_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper locking."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    def record_event(self, event: AnalyticsEvent):
        """Record an analytics event."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO analytics_events 
                (id, timestamp, session_id, user_id, event_type, agent_role, properties, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.id, event.timestamp, event.session_id, event.user_id,
                event.event_type.value, event.agent_role,
                json.dumps(event.properties), json.dumps(event.metadata)
            ))
            conn.commit()
    
    def record_user(self, user: UserInfo):
        """Record or update user information."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO users 
                (user_id, username, email, role, created_at, last_active, is_active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user.user_id, user.username, user.email, user.role,
                user.created_at, user.last_active, user.is_active,
                json.dumps(user.metadata)
            ))
            conn.commit()
    
    def get_user(self, user_id: str) -> Optional[UserInfo]:
        """Get user information by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return UserInfo.from_dict(dict(row))
            return None
    
    def record_team(self, team: TeamInfo):
        """Record or update team information."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO teams 
                (team_id, name, description, created_at, created_by, is_active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                team.team_id, team.name, team.description, team.created_at,
                team.created_by, team.is_active, json.dumps(team.metadata)
            ))
            conn.commit()
    
    def add_team_member(self, team_id: str, user_id: str):
        """Add a user to a team."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO team_members (team_id, user_id, joined_at)
                VALUES (?, ?, ?)
            """, (team_id, user_id, datetime.now().isoformat()))
            conn.commit()
    
    def get_team_members(self, team_id: str) -> List[str]:
        """Get all user IDs in a team."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT user_id FROM team_members WHERE team_id = ?", (team_id,)
            )
            return [row["user_id"] for row in cursor.fetchall()]
    
    def get_user_teams(self, user_id: str) -> List[str]:
        """Get all team IDs for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT team_id FROM team_members WHERE user_id = ?", (user_id,)
            )
            return [row["team_id"] for row in cursor.fetchall()]
    
    def get_events(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[AnalyticsEvent]:
        """Get events with optional filtering."""
        query = "SELECT * FROM analytics_events WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(str(limit))
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [AnalyticsEvent.from_dict(dict(row)) for row in cursor.fetchall()]
    
    def get_usage_stats(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get usage statistics for a time period."""
        query = """
            SELECT 
                COUNT(*) as total_events,
                COUNT(DISTINCT session_id) as unique_sessions,
                COUNT(DISTINCT user_id) as unique_users,
                agent_role,
                event_type
            FROM analytics_events 
            WHERE 1=1
        """
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " GROUP BY agent_role, event_type"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            # Process results into a nested structure
            stats = {
                "total_events": 0,
                "unique_sessions": set(),
                "unique_users": set(),
                "by_role": defaultdict(lambda: defaultdict(int)),
                "by_event_type": defaultdict(int),
                "time_period": {
                    "start": start_time.isoformat() if start_time else None,
                    "end": end_time.isoformat() if end_time else None
                }
            }
            
            for row in rows:
                stats["total_events"] += row["total_events"]
                stats["by_role"][row["agent_role"]][row["event_type"]] += row["total_events"]
                stats["by_event_type"][row["event_type"]] += row["total_events"]
                # Note: We'd need to query separately for distinct counts, but this gives a good approximation
            
            return stats


class EnhancedAnalytics:
    """Enhanced analytics system providing business intelligence and reporting."""
    
    def __init__(self, analytics_db: AnalyticsDatabase = None):
        self.db = analytics_db or AnalyticsDatabase()
    
    def track_chat_message(
        self, 
        session_id: str, 
        user_id: str, 
        message_length: int,
        agent_role: str = "user",
        metadata: Dict[str, Any] = None
    ):
        """Track a chat message event."""
        event = AnalyticsEvent(
            session_id=session_id,
            user_id=user_id,
            event_type=EventType.CHAT_MESSAGE,
            agent_role=agent_role,
            properties={
                "message_length": message_length
            },
            metadata=metadata or {}
        )
        self.db.record_event(event)
    
    def track_tool_use(
        self, 
        session_id: str, 
        user_id: str, 
        tool_name: str,
        success: bool = True,
        duration_ms: float = 0.0,
        agent_role: str = "user",
        metadata: Dict[str, Any] = None
    ):
        """Track a tool usage event."""
        event = AnalyticsEvent(
            session_id=session_id,
            user_id=user_id,
            event_type=EventType.TOOL_USE,
            agent_role=agent_role,
            properties={
                "tool_name": tool_name,
                "success": success,
                "duration_ms": duration_ms
            },
            metadata=metadata or {}
        )
        self.db.record_event(event)
    
    def track_subagent_lifecycle(
        self, 
        session_id: str, 
        user_id: str, 
        subagent_name: str,
        action: str,  # spawn or complete
        task_description: str = "",
        agent_role: str = "user",
        metadata: Dict[str, Any] = None
    ):
        """Track subagent spawn or completion."""
        event_type = EventType.SUBAGENT_SPAWN if action == "spawn" else EventType.SUBAGENT_COMPLETE
        event = AnalyticsEvent(
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            agent_role=agent_role,
            properties={
                "subagent_name": subagent_name,
                "task_description": task_description
            },
            metadata=metadata or {}
        )
        self.db.record_event(event)
    
    def track_patch_activity(
        self, 
        session_id: str, 
        user_id: str, 
        action: str,  # proposed, approved, rejected
        file_path: str = "",
        agent_role: str = "dev",  # Only dev can propose patches
        metadata: Dict[str, Any] = None
    ):
        """Track patch proposal/approval/rejection."""
        event_type_map = {
            "proposed": EventType.PATCH_PROPOSED,
            "approved": EventType.PATCH_APPROVED,
            "rejected": EventType.PATCH_REJECTED
        }
        event_type = event_type_map.get(action, EventType.PATCH_PROPOSED)
        
        event = AnalyticsEvent(
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            agent_role=agent_role,
            properties={
                "file_path": file_path,
                "action": action
            },
            metadata=metadata or {}
        )
        self.db.record_event(event)
    
    def get_productivity_report(
        self, 
        days: int = 7,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a productivity report for the specified time period."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # Get events for the period
        events = self.db.get_events(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            limit=10000  # Increase if needed
        )
        
        # Filter by team if specified
        if team_id and not user_id:
            team_users = self.db.get_team_members(team_id)
            events = [e for e in events if e.user_id in team_users]
        elif team_id and user_id:
            # Check if user is in team
            user_teams = self.db.get_user_teams(user_id)
            if team_id not in user_teams:
                events = []  # User not in team
        
        # Calculate metrics
        total_messages = len([e for e in events if e.event_type == EventType.CHAT_MESSAGE])
        total_tool_uses = len([e for e in events if e.event_type == EventType.TOOL_USE])
        total_subagents = len([e for e in events if e.event_type in [EventType.SUBAGENT_SPAWN, EventType.SUBAGENT_COMPLETE]])
        total_patches = len([e for e in events if e.event_type in [EventType.PATCH_PROPOSED, EventType.PATCH_APPROVED, EventType.PATCH_REJECTED]])
        
        # Success rates
        successful_tools = len([e for e in events if e.event_type == EventType.TOOL_USE and e.properties.get("success", False)])
        tool_success_rate = (successful_tools / total_tool_uses * 100) if total_tool_uses > 0 else 0
        
        # Patch approval rate
        proposed_patches = len([e for e in events if e.event_type == EventType.PATCH_PROPOSED])
        approved_patches = len([e for e in events if e.event_type == EventType.PATCH_APPROVED])
        patch_approval_rate = (approved_patches / proposed_patches * 100) if proposed_patches > 0 else 0
        
        # Unique sessions and users
        unique_sessions = len(set(e.session_id for e in events if e.session_id))
        unique_users = len(set(e.user_id for e in events if e.user_id))
        
        # Average message length
        message_lengths = [e.properties.get("message_length", 0) for e in events if e.event_type == EventType.CHAT_MESSAGE]
        avg_message_length = sum(message_lengths) / len(message_lengths) if message_lengths else 0
        
        return {
            "time_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "days": days
            },
            "activity": {
                "total_messages": total_messages,
                "total_tool_uses": total_tool_uses,
                "total_subagent_operations": total_subagents,
                "total_patch_activities": total_patches
            },
            "efficiency": {
                "tool_success_rate_percent": round(tool_success_rate, 2),
                "patch_approval_rate_percent": round(patch_approval_rate, 2),
                "avg_message_length": round(avg_message_length, 2)
            },
            "engagement": {
                "unique_sessions": unique_sessions,
                "unique_users": unique_users,
                "messages_per_session": round(total_messages / unique_sessions, 2) if unique_sessions > 0 else 0,
                "tools_per_session": round(total_tool_uses / unique_sessions, 2) if unique_sessions > 0 else 0
            }
        }
    
    def get_user_activity_report(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get detailed activity report for a specific user."""
        return self.get_productivity_report(days=days, user_id=user_id)
    
    def get_team_activity_report(self, team_id: str, days: int = 30) -> Dict[str, Any]:
        """Get activity report for a specific team."""
        return self.get_productivity_report(days=days, team_id=team_id)
    
    def export_analytics_data(
        self, 
        format: str = "json",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """Export analytics data in various formats."""
        events = self.db.get_events(
            start_time=start_time,
            end_time=end_time,
            limit=100000  # Large limit for export
        )
        
        if format.lower() == "json":
            return json.dumps([asdict(e) for e in events], indent=2, default=str)
        elif format.lower() == "csv":
            # Simple CSV export
            if not events:
                return "id,timestamp,session_id,user_id,event_type,agent_role,properties,metadata\n"
            
            lines = ["id,timestamp,session_id,user_id,event_type,agent_role,properties,metadata"]
            for event in events:
                escaped_props = json.dumps(event.properties).replace('"', '""')
                escaped_meta = json.dumps(event.metadata).replace('"', '""')
                line = f'"{event.id}","{event.timestamp}","{event.session_id}","{event.user_id}","{event.event_type.value}","{event.agent_role}","{escaped_props}","{escaped_meta}"'
                lines.append(line)
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")


# Global instances
_analytics_db: Optional[AnalyticsDatabase] = None
_enhanced_analytics: Optional[EnhancedAnalytics] = None


def get_analytics_database() -> AnalyticsDatabase:
    """Get or create the global analytics database."""
    global _analytics_db
    if _analytics_db is None:
        _analytics_db = AnalyticsDatabase()
    return _analytics_db


def get_enhanced_analytics() -> EnhancedAnalytics:
    """Get or create the global enhanced analytics instance."""
    global _enhanced_analytics
    if _enhanced_analytics is None:
        _enhanced_analytics = EnhancedAnalytics(get_analytics_database())
    return _enhanced_analytics


def init_analytics(db_path: Path = None) -> AnalyticsDatabase:
    """Initialize analytics with custom database path."""
    global _analytics_db, _enhanced_analytics
    _analytics_db = AnalyticsDatabase(db_path)
    _enhanced_analytics = EnhancedAnalytics(_analytics_db)
    return _analytics_db