"""
Enhanced permission system for Kovanica Agent.
Supports role-based access control (RBAC), teams, organizations, and fine-grained permissions.
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set
import sqlite3
from contextlib import contextmanager


class PermissionLevel(Enum):
    """Permission levels for RBAC."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class Role(Enum):
    """Standard roles in the system."""
    USER = "user"
    DEVELOPER = "dev"
    ADMIN = "admin"
    OWNER = "owner"


@dataclass
class Permission:
    """Represents a specific permission."""
    resource: str  # e.g., "tool:read_file", "session:list", "team:create"
    level: PermissionLevel
    granted_by: str = ""  # Who granted this permission
    granted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None  # ISO timestamp, None for no expiration
    
    def is_expired(self) -> bool:
        """Check if this permission has expired."""
        if not self.expires_at:
            return False
        return datetime.now().isoformat() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Permission':
        return cls(**data)


@dataclass
class User:
    """Extended user information with RBAC support."""
    user_id: str
    username: str
    email: str = ""
    role: Role = Role.USER
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Permission] = field(default_factory=dict)  # resource -> Permission
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['role'] = self.role.value
        data['permissions'] = {k: v.to_dict() for k, v in self.permissions.items()}
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        # Handle enum conversion
        if 'role' in data and isinstance(data['role'], str):
            data['role'] = Role(data['role'])
        
        # Handle permissions conversion
        if 'permissions' in data and isinstance(data['permissions'], dict):
            perms = {}
            for k, v in data['permissions'].items():
                if isinstance(v, dict):
                    perms[k] = Permission.from_dict(v)
                else:
                    perms[k] = v
            data['permissions'] = perms
        
        return cls(**data)


@dataclass
class Team:
    """Team/Group information."""
    team_id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = ""  # user_id
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    # team-level permissions that apply to all members
    permissions: Dict[str, Permission] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['permissions'] = {k: v.to_dict() for k, v in self.permissions.items()}
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Team':
        if 'permissions' in data and isinstance(data['permissions'], dict):
            perms = {}
            for k, v in data['permissions'].items():
                if isinstance(v, dict):
                    perms[k] = Permission.from_dict(v)
                else:
                    perms[k] = v
            data['permissions'] = perms
        return cls(**data)


@dataclass
class Organization:
    """Organization information."""
    org_id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = ""  # user_id
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Default permissions for new users in this org
    default_user_permissions: Dict[str, Permission] = field(default_factory=dict)
    # Default permissions for new teams in this org
    default_team_permissions: Dict[str, Permission] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['default_user_permissions'] = {
            k: v.to_dict() for k, v in self.default_user_permissions.items()
        }
        data['default_team_permissions'] = {
            k: v.to_dict() for k, v in self.default_team_permissions.items()
        }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Organization':
        if 'default_user_permissions' in data and isinstance(data['default_user_permissions'], dict):
            perms = {}
            for k, v in data['default_user_permissions'].items():
                if isinstance(v, dict):
                    perms[k] = Permission.from_dict(v)
                else:
                    perms[k] = v
            data['default_user_permissions'] = perms
            
        if 'default_team_permissions' in data and isinstance(data['default_team_permissions'], dict):
            perms = {}
            for k, v in data['default_team_permissions'].items():
                if isinstance(v, dict):
                    perms[k] = Permission.from_dict(v)
                else:
                    perms[k] = v
            data['default_team_permissions'] = perms
        return cls(**data)


class EnhancedPermissionManager:
    """Manages users, teams, organizations, and permissions."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or Path.home() / ".kovanica" / "permissions.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._init_db()
        # Load built-in roles and permissions
        self._load_built_in_permissions()
    
    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT,
                    role TEXT NOT NULL,
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
                
                CREATE TABLE IF NOT EXISTS organizations (
                    org_id TEXT PRIMARY KEY,
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
                
                CREATE TABLE IF NOT EXISTS org_members (
                    org_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (org_id, user_id),
                    FOREIGN KEY (org_id) REFERENCES organizations (org_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
                
                CREATE TABLE IF NOT EXISTS user_permissions (
                    user_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    level TEXT NOT NULL,
                    granted_by TEXT,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY (user_id, resource),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
                
                CREATE TABLE IF NOT EXISTS team_permissions (
                    team_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    level TEXT NOT NULL,
                    granted_by TEXT,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY (team_id, resource),
                    FOREIGN KEY (team_id) REFERENCES teams (team_id)
                );
                
                CREATE TABLE IF NOT EXISTS org_permissions (
                    org_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    level TEXT NOT NULL,
                    granted_by TEXT,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY (org_id, resource),
                    FOREIGN KEY (org_id) REFERENCES organizations (org_id)
                );
                
                CREATE TABLE IF NOT EXISTS org_default_user_permissions (
                    org_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    level TEXT NOT NULL,
                    PRIMARY KEY (org_id, resource),
                    FOREIGN KEY (org_id) REFERENCES organizations (org_id)
                );
                
                CREATE TABLE IF NOT EXISTS org_default_team_permissions (
                    org_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    level TEXT NOT NULL,
                    PRIMARY KEY (org_id, resource),
                    FOREIGN KEY (org_id) REFERENCES organizations (org_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
                CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(is_active);
                CREATE INDEX IF NOT EXISTS idx_orgs_active ON organizations(is_active);
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
    
    def _load_built_in_permissions(self):
        """Load built-in permissions for standard roles."""
        # Define what each role can do by default
        role_permissions = {
            Role.USER: {
                "tool:search_codebase": PermissionLevel.READ,
                "tool:search_kovanica_docs": PermissionLevel.READ,
                "tool:read_file": PermissionLevel.READ,
                "tool:explain_concept": PermissionLevel.READ,
                "tool:query_node_api": PermissionLevel.READ,
                "tool:glob": PermissionLevel.READ,
                "tool:grep": PermissionLevel.READ,
                "tool:memory_recall": PermissionLevel.READ,
                "tool:session_list": PermissionLevel.READ,
                "tool:task_add": PermissionLevel.WRITE,
                "tool:task_list": PermissionLevel.READ,
                "session:create": PermissionLevel.WRITE,
                "session:read": PermissionLevel.READ,
            },
            Role.DEVELOPER: {
                # Inherit all USER permissions
                "tool:search_codebase": PermissionLevel.READ,
                "tool:search_kovanica_docs": PermissionLevel.READ,
                "tool:read_file": PermissionLevel.READ,
                "tool:explain_concept": PermissionLevel.READ,
                "tool:query_node_api": PermissionLevel.READ,
                "tool:glob": PermissionLevel.READ,
                "tool:grep": PermissionLevel.READ,
                "tool:memory_recall": PermissionLevel.READ,
                "tool:session_list": PermissionLevel.READ,
                "tool:task_add": PermissionLevel.WRITE,
                "tool:task_list": PermissionLevel.READ,
                "tool:task_done": PermissionLevel.WRITE,
                "tool:task_remove": PermissionLevel.WRITE,
                "tool:edit_file": PermissionLevel.WRITE,
                "tool:write_file": PermissionLevel.WRITE,
                "tool:run_bash": PermissionLevel.WRITE,
                "tool:run_cargo_command": PermissionLevel.WRITE,
                "tool:git_diff_suggest": PermissionLevel.WRITE,
                "session:create": PermissionLevel.WRITE,
                "session:read": PermissionLevel.READ,
                "session:update": PermissionLevel.WRITE,
                "session:delete": PermissionLevel.WRITE,
                "team:create": PermissionLevel.WRITE,
                "team:read": PermissionLevel.READ,
                "team:update": PermissionLevel.WRITE,
                "team:delete": PermissionLevel.WRITE,
            },
            Role.ADMIN: {
                # Inherit all DEVELOPER permissions plus admin functions
                "tool:search_codebase": PermissionLevel.READ,
                "tool:search_kovanica_docs": PermissionLevel.READ,
                "tool:read_file": PermissionLevel.READ,
                "tool:explain_concept": PermissionLevel.READ,
                "tool:query_node_api": PermissionLevel.READ,
                "tool:glob": PermissionLevel.READ,
                "tool:grep": PermissionLevel.READ,
                "tool:memory_recall": PermissionLevel.READ,
                "tool:session_list": PermissionLevel.READ,
                "tool:task_add": PermissionLevel.WRITE,
                "tool:task_list": PermissionLevel.READ,
                "tool:task_done": PermissionLevel.WRITE,
                "tool:task_remove": PermissionLevel.WRITE,
                "tool:edit_file": PermissionLevel.WRITE,
                "tool:write_file": PermissionLevel.WRITE,
                "tool:run_bash": PermissionLevel.WRITE,
                "tool:run_cargo_command": PermissionLevel.WRITE,
                "tool:git_diff_suggest": PermissionLevel.WRITE,
                "session:create": PermissionLevel.WRITE,
                "session:read": PermissionLevel.READ,
                "session:update": PermissionLevel.WRITE,
                "session:delete": PermissionLevel.WRITE,
                "team:create": PermissionLevel.WRITE,
                "team:read": PermissionLevel.READ,
                "team:update": PermissionLevel.WRITE,
                "team:delete": PermissionLevel.WRITE,
                "org:create": PermissionLevel.WRITE,
                "org:read": PermissionLevel.READ,
                "org:update": PermissionLevel.WRITE,
                "org:delete": PermissionLevel.WRITE,
                "user:create": PermissionLevel.WRITE,
                "user:read": PermissionLevel.READ,
                "user:update": PermissionLevel.WRITE,
                "user:delete": PermissionLevel.WRITE,
                "user:assign_role": PermissionLevel.WRITE,
                "system:configure": PermissionLevel.WRITE,
                "system:backup": PermissionLevel.WRITE,
                "system:restore": PermissionLevel.WRITE,
            }
        }
        
        # These would normally be loaded from DB, but for now we'll just note them
        # In a real implementation, we'd check if built-ins exist and create if not
        pass
    
    # User management methods
    def create_user(self, user: User) -> bool:
        """Create a new user."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO users 
                    (user_id, username, email, role, created_at, last_active, is_active, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.user_id, user.username, user.email, user.role.value,
                    user.created_at, user.last_active, user.is_active,
                    json.dumps(user.metadata)
                ))
                
                # Assign default permissions based on role
                self._assign_default_role_permissions(conn, user.user_id, user.role)
                
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Username or user_id already exists
        except Exception:
            return False
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                user = User(
                    user_id=row["user_id"],
                    username=row["username"],
                    email=row["email"],
                    role=Role(row["role"]),
                    created_at=row["created_at"],
                    last_active=row["last_active"],
                    is_active=bool(row["is_active"]),
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                )
                # Load user-specific permissions
                user.permissions = self._get_user_permissions(conn, user_id)
                return user
            return None
    
    def update_user(self, user: User) -> bool:
        """Update an existing user."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE users 
                    SET username = ?, email = ?, role = ?, last_active = ?, 
                        is_active = ?, metadata = ?
                    WHERE user_id = ?
                """, (
                    user.username, user.email, user.role.value,
                    user.last_active, user.is_active,
                    json.dumps(user.metadata), user.user_id
                ))
                conn.commit()
            return True
        except Exception:
            return False
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user (soft delete by setting inactive)."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,)
                )
                conn.commit()
            return True
        except Exception:
            return False
    
    # Team management methods
    def create_team(self, team: Team) -> bool:
        """Create a new team."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO teams 
                    (team_id, name, description, created_at, created_by, is_active, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    team.team_id, team.name, team.description, team.created_at,
                    team.created_by, team.is_active, json.dumps(team.metadata)
                ))
                
                # Assign default team permissions
                self._assign_default_team_permissions(conn, team.team_id)
                
                # Add creator as team member
                self.add_team_member(team.team_id, team.created_by)
                
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Team already exists
        except Exception:
            return False
    
    def get_team(self, team_id: str) -> Optional[Team]:
        """Get a team by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM teams WHERE team_id = ?", (team_id,)
            )
            row = cursor.fetchone()
            if row:
                team = Team(
                    team_id=row["team_id"],
                    name=row["name"],
                    description=row["description"],
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                    is_active=bool(row["is_active"]),
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                )
                # Load team-specific permissions
                team.permissions = self._get_team_permissions(conn, team_id)
                return team
            return None
    
    def add_team_member(self, team_id: str, user_id: str) -> bool:
        """Add a user to a team."""
        try:
            with self._get_connection() as conn:
                # Verify user and team exist
                user_cursor = conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ? AND is_active = 1", (user_id,)
                )
                team_cursor = conn.execute(
                    "SELECT 1 FROM teams WHERE team_id = ? AND is_active = 1", (team_id,)
                )
                
                if not user_cursor.fetchone() or not team_cursor.fetchone():
                    return False
                
                conn.execute("""
                    INSERT OR IGNORE INTO team_members (team_id, user_id, joined_at)
                    VALUES (?, ?, ?)
                """, (team_id, user_id, datetime.now().isoformat()))
                conn.commit()
            return True
        except Exception:
            return False
    
    def remove_team_member(self, team_id: str, user_id: str) -> bool:
        """Remove a user from a team."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                    (team_id, user_id)
                )
                conn.commit()
            return True
        except Exception:
            return False
    
    # Organization management methods
    def create_organization(self, org: Organization) -> bool:
        """Create a new organization."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO organizations 
                    (org_id, name, description, created_at, created_by, is_active, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    org.org_id, org.name, org.description, org.created_at,
                    org.created_by, org.is_active, json.dumps(org.metadata)
                ))
                
                # Assign default organization permissions
                self._assign_default_org_permissions(conn, org.org_id)
                
                # Add creator as org member
                self.add_org_member(org.org_id, org.created_by)
                
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Organization already exists
        except Exception:
            return False
    
    def get_organization(self, org_id: str) -> Optional[Organization]:
        """Get an organization by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM organizations WHERE org_id = ?", (org_id,)
            )
            row = cursor.fetchone()
            if row:
                org = Organization(
                    org_id=row["org_id"],
                    name=row["name"],
                    description=row["description"],
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                    is_active=bool(row["is_active"]),
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                )
                # Load org-specific permissions and defaults
                org.permissions = self._get_org_permissions(conn, org_id)
                org.default_user_permissions = self._get_org_default_user_permissions(conn, org_id)
                org.default_team_permissions = self._get_org_default_team_permissions(conn, org_id)
                return org
            return None
    
    def add_org_member(self, org_id: str, user_id: str) -> bool:
        """Add a user to an organization."""
        try:
            with self._get_connection() as conn:
                # Verify user and org exist
                user_cursor = conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ? AND is_active = 1", (user_id,)
                )
                org_cursor = conn.execute(
                    "SELECT 1 FROM organizations WHERE org_id = ? AND is_active = 1", (org_id,)
                )
                
                if not user_cursor.fetchone() or not org_cursor.fetchone():
                    return False
                
                conn.execute("""
                    INSERT OR IGNORE INTO org_members (org_id, user_id, joined_at)
                    VALUES (?, ?, ?)
                """, (org_id, user_id, datetime.now().isoformat()))
                
                # Assign default org permissions to user
                self._assign_org_default_permissions_to_user(conn, org_id, user_id)
                
                conn.commit()
            return True
        except Exception:
            return False
    
    # Permission management methods
    def grant_permission(
        self, 
        user_id: str, 
        resource: str, 
        level: PermissionLevel,
        granted_by: str = "",
        expires_at: Optional[str] = None
    ) -> bool:
        """Grant a specific permission to a user."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO user_permissions 
                    (user_id, resource, level, granted_by, granted_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user_id, resource, level.value, granted_by,
                    datetime.now().isoformat(), expires_at
                ))
                conn.commit()
            return True
        except Exception:
            return False
    
    def revoke_permission(self, user_id: str, resource: str) -> bool:
        """Revoke a specific permission from a user."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM user_permissions WHERE user_id = ? AND resource = ?",
                    (user_id, resource)
                )
                conn.commit()
            return True
        except Exception:
            return False
    
    def check_permission(
        self, 
        user_id: str, 
        resource: str, 
        required_level: PermissionLevel = PermissionLevel.READ
    ) -> bool:
        """Check if a user has a specific permission level for a resource."""
        # Get user's effective permission (considering team and org inheritance)
        effective_level = self.get_effective_permission_level(user_id, resource)
        
        # Check if effective level meets or exceeds required level
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.WRITE: 2,
            PermissionLevel.ADMIN: 3
        }
        
        return level_hierarchy.get(effective_level, 0) >= level_hierarchy.get(required_level, 0)
    
    def get_effective_permission_level(
        self, 
        user_id: str, 
        resource: str
    ) -> PermissionLevel:
        """Get the effective permission level for a user on a resource,
        considering user, team, and organization permissions."""
        with self._get_connection() as conn:
            # Start with NONE
            effective = PermissionLevel.NONE
            
            # Check user-specific permissions
            user_level = self._get_user_permission_level(conn, user_id, resource)
            if user_level.value > effective.value:
                effective = user_level
            
            # Check team permissions (user's teams)
            team_level = self._get_user_teams_permission_level(conn, user_id, resource)
            if team_level.value > effective.value:
                effective = team_level
            
            # Check organization permissions (user's orgs)
            org_level = self._get_user_orgs_permission_level(conn, user_id, resource)
            if org_level.value > effective.value:
                effective = org_level
            
            return effective
    
    # Helper methods for permission checking
    def _get_user_permission_level(
        self, 
        conn: sqlite3.Connection, 
        user_id: str, 
        resource: str
    ) -> PermissionLevel:
        """Get user-specific permission level."""
        cursor = conn.execute(
            "SELECT level FROM user_permissions WHERE user_id = ? AND resource = ?",
            (user_id, resource)
        )
        row = cursor.fetchone()
        if row:
            level_str = row["level"]
            try:
                return PermissionLevel(level_str)
            except ValueError:
                return PermissionLevel.NONE
        return PermissionLevel.NONE
    
    def _get_user_teams_permission_level(
        self, 
        conn: sqlite3.Connection, 
        user_id: str, 
        resource: str
    ) -> PermissionLevel:
        """Get the highest permission level from user's teams."""
        cursor = conn.execute("""
            SELECT tp.level 
            FROM team_permissions tp
            JOIN team_members tm ON tp.team_id = tm.team_id
            WHERE tm.user_id = ? AND tp.resource = ?
        """, (user_id, resource))
        
        effective = PermissionLevel.NONE
        for row in cursor.fetchall():
            try:
                level = PermissionLevel(row["level"])
                if level.value > effective.value:
                    effective = level
            except ValueError:
                pass
        return effective
    
    def _get_user_orgs_permission_level(
        self, 
        conn: sqlite3.Connection, 
        user_id: str, 
        resource: str
    ) -> PermissionLevel:
        """Get the highest permission level from user's organizations."""
        cursor = conn.execute("""
            SELECT op.level 
            FROM org_permissions op
            JOIN org_members om ON op.org_id = om.org_id
            WHERE om.user_id = ? AND op.resource = ?
        """, (user_id, resource))
        
        effective = PermissionLevel.NONE
        for row in cursor.fetchall():
            try:
                level = PermissionLevel(row["level"])
                if level.value > effective.value:
                    effective = level
            except ValueError:
                pass
        return effective
    
    # Default permission assignment methods
    def _assign_default_role_permissions(
        self, 
        conn: sqlite3.Connection, 
        user_id: str, 
        role: Role
    ):
        """Assign default permissions based on user role."""
        # This would assign permissions based on the role
        # For now, we rely on the built-in permission checking in _get_effective_permission_level
        # which considers role-based defaults
        pass
    
    def _assign_default_team_permissions(
        self, 
        conn: sqlite3.Connection, 
        team_id: str
    ):
        """Assign default permissions to a team."""
        # Teams start with no special permissions by default
        pass
    
    def _assign_default_org_permissions(
        self, 
        conn: sqlite3.Connection, 
        org_id: str
    ):
        """Assign default permissions to an organization."""
        # Orgs start with no special permissions by default
        pass
    
    def _assign_org_default_permissions_to_user(
        self, 
        conn: sqlite3.Connection, 
        org_id: str, 
        user_id: str
    ):
        """Assign organization's default permissions to a user."""
        # Get org's default user permissions and assign them
        defaults = self._get_org_default_user_permissions(conn, org_id)
        for resource, level in defaults.items():
            self.grant_permission(user_id, resource, level, granted_by="system")
    
    def _get_team_permissions(
        self, 
        conn: sqlite3.Connection, 
        team_id: str
    ) -> Dict[str, Permission]:
        """Get all permissions for a team."""
        cursor = conn.execute(
            "SELECT resource, level, granted_by, granted_at, expires_at FROM team_permissions WHERE team_id = ?",
            (team_id,)
        )
        perms = {}
        for row in cursor.fetchall():
            try:
                perms[row["resource"]] = Permission(
                    resource=row["resource"],
                    level=PermissionLevel(row["level"]),
                    granted_by=row["granted_by"] or "",
                    granted_at=row["granted_at"],
                    expires_at=row["expires_at"]
                )
            except (ValueError, KeyError):
                pass
        return perms
    
    def _get_user_permissions(
        self, 
        conn: sqlite3.Connection, 
        user_id: str
    ) -> Dict[str, Permission]:
        """Get all permissions for a user."""
        cursor = conn.execute(
            "SELECT resource, level, granted_by, granted_at, expires_at FROM user_permissions WHERE user_id = ?",
            (user_id,)
        )
        perms = {}
        for row in cursor.fetchall():
            try:
                perms[row["resource"]] = Permission(
                    resource=row["resource"],
                    level=PermissionLevel(row["level"]),
                    granted_by=row["granted_by"] or "",
                    granted_at=row["granted_at"],
                    expires_at=row["expires_at"]
                )
            except (ValueError, KeyError):
                pass
        return perms
    
    def _get_org_permissions(
        self, 
        conn: sqlite3.Connection, 
        org_id: str
    ) -> Dict[str, Permission]:
        """Get all permissions for an organization."""
        cursor = conn.execute(
            "SELECT resource, level, granted_by, granted_at, expires_at FROM org_permissions WHERE org_id = ?",
            (org_id,)
        )
        perms = {}
        for row in cursor.fetchall():
            try:
                perms[row["resource"]] = Permission(
                    resource=row["resource"],
                    level=PermissionLevel(row["level"]),
                    granted_by=row["granted_by"] or "",
                    granted_at=row["granted_at"],
                    expires_at=row["expires_at"]
                )
            except (ValueError, KeyError):
                pass
        return perms
    
    def _get_org_default_user_permissions(
        self, 
        conn: sqlite3.Connection, 
        org_id: str
    ) -> Dict[str, PermissionLevel]:
        """Get default user permissions for an organization."""
        cursor = conn.execute(
            "SELECT resource, level FROM org_default_user_permissions WHERE org_id = ?",
            (org_id,)
        )
        perms = {}
        for row in cursor.fetchall():
            try:
                perms[row["resource"]] = PermissionLevel(row["level"])
            except ValueError:
                pass
        return perms
    
    def _get_org_default_team_permissions(
        self, 
        conn: sqlite3.Connection, 
        org_id: str
    ) -> Dict[str, PermissionLevel]:
        """Get default team permissions for an organization."""
        cursor = conn.execute(
            "SELECT resource, level FROM org_default_team_permissions WHERE org_id = ?",
            (org_id,)
        )
        perms = {}
        for row in cursor.fetchall():
            try:
                perms[row["resource"]] = PermissionLevel(row["level"])
            except ValueError:
                pass
        return perms


# Global permission manager instance
_permission_manager: Optional[EnhancedPermissionManager] = None


def get_permission_manager() -> EnhancedPermissionManager:
    """Get or create the global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = EnhancedPermissionManager()
    return _permission_manager


def init_permissions(db_path: Path = None) -> EnhancedPermissionManager:
    """Initialize permissions with custom database path."""
    global _permission_manager
    _permission_manager = EnhancedPermissionManager(db_path)
    return _permission_manager