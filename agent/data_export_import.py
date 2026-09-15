"""
Data export/import functionality for Kovanica Agent.
Provides backup/restore, migration tools, and data export capabilities.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tarfile
import zipfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import tempfile


class ExportFormat(Enum):
    """Supported export formats."""
    JSON = "json"
    SQLITE = "sqlite"
    CSV = "csv"
    MARKDOWN = "md"


class BackupType(Enum):
    """Types of backups."""
    FULL = "full"
    INCREMENTAL = "incremental"
    CONFIG_ONLY = "config_only"
    DATA_ONLY = "data_only"


class DataExportImportManager:
    """Manages data export, import, backup, and restore operations."""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path.home() / ".kovanica"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.base_path / "backups"
        self.export_dir = self.base_path / "exports"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(
        self, 
        backup_type: BackupType = BackupType.FULL,
        include_paths: Optional[List[Path]] = None,
        exclude_paths: Optional[List[Path]] = None,
        compress: bool = True
    ) -> Path:
        """Create a backup of specified components."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"kovanica_backup_{backup_type.value}_{timestamp}"
        
        if compress:
            backup_path = self.backup_dir / f"{backup_name}.tar.gz"
            return self._create_compressed_backup(backup_path, backup_type, include_paths, exclude_paths)
        else:
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(parents=True, exist_ok=True)
            return self._create_uncompressed_backup(backup_path, backup_type, include_paths, exclude_paths)
    
    def _create_compressed_backup(
        self, 
        backup_path: Path, 
        backup_type: BackupType,
        include_paths: Optional[List[Path]] = None,
        exclude_paths: Optional[List[Path]] = None
    ) -> Path:
        """Create a compressed tar.gz backup."""
        with tarfile.open(backup_path, "w:gz") as tar:
            # Determine what to backup based on type
            paths_to_backup = self._get_paths_for_backup_type(backup_type, include_paths)
            
            # Apply exclusions
            if exclude_paths:
                paths_to_backup = [
                    p for p in paths_to_backup 
                    if not any(str(p).startswith(str(ex)) for ex in exclude_paths)
                ]
            
            # Add each path to the archive
            for path in paths_to_backup:
                if path.exists():
                    tar.add(path, arcname=path.relative_to(self.base_path.parent))
        
        return backup_path
    
    def _create_uncompressed_backup(
        self, 
        backup_path: Path, 
        backup_type: BackupType,
        include_paths: Optional[List[Path]] = None,
        exclude_paths: Optional[List[Path]] = None
    ) -> Path:
        """Create an uncompressed directory backup."""
        # Determine what to backup based on type
        paths_to_backup = self._get_paths_for_backup_type(backup_type, include_paths)
        
        # Apply exclusions
        if exclude_paths:
            paths_to_backup = [
                p for p in paths_to_backup 
                if not any(str(p).startswith(str(ex)) for ex in exclude_paths)
            ]
        
        # Copy each path to the backup directory
        for path in paths_to_backup:
            if path.exists():
                relative_path = path.relative_to(self.base_path.parent)
                dest_path = backup_path / relative_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                if path.is_file():
                    shutil.copy2(path, dest_path)
                else:
                    shutil.copytree(path, dest_path, dirs_exist_ok=True)
        
        return backup_path
    
    def _get_paths_for_backup_type(
        self, 
        backup_type: BackupType,
        include_paths: Optional[List[Path]] = None
    ) -> List[Path]:
        """Get the list of paths to backup based on backup type."""
        if include_paths:
            return include_paths
        
        # Default paths for each backup type
        default_paths = {
            BackupType.FULL: [
                self.base_path / "agent.sqlite3",           # Main session/checkpoint DB
                self.base_path / ".kovi" / "tasks.sqlite3", # Task database
                self.base_path / ".kovi" / "memory.sqlite3", # Memory database
                self.base_path / "logs",                     # Log files
                self.base_path / "config",                   # Configuration files
                self.base_path / "plugins",                  # Installed plugins
                self.base_path / "skills",                   # Installed skills
                self.base_path / "vault" if (self.base_path / "vault").exists() else None, # Vault data
            ],
            BackupType.INCREMENTAL: [
                self.base_path / "agent.sqlite3",           # Main session/checkpoint DB (most important)
                self.base_path / ".kovi" / "tasks.sqlite3", # Task database
                self.base_path / ".kovi" / "memory.sqlite3", # Memory database
                self.base_path / "logs",                     # Recent log files
            ],
            BackupType.CONFIG_ONLY: [
                self.base_path / "config",                   # Configuration files
                self.base_path / "plugins",                  # Installed plugins
                self.base_path / "skills",                   # Installed skills
            ],
            BackupType.DATA_ONLY: [
                self.base_path / "agent.sqlite3",           # Main session/checkpoint DB
                self.base_path / ".kovi" / "tasks.sqlite3", # Task database
                self.base_path / ".kovi" / "memory.sqlite3", # Memory database
            ]
        }
        
        paths = default_paths.get(backup_type, [])
        # Filter out None values and non-existing paths
        return [p for p in paths if p is not None]
    
    def restore_backup(
        self, 
        backup_path: Path,
        restore_paths: Optional[List[Path]] = None,
        overwrite: bool = False
    ) -> bool:
        """Restore from a backup."""
        try:
            if backup_path.suffix == ".gz" or backup_path.suffixes == [".tar", ".gz"]:
                return self._restore_compressed_backup(backup_path, restore_paths, overwrite)
            else:
                return self._restore_uncompressed_backup(backup_path, restore_paths, overwrite)
        except Exception as e:
            print(f"Error restoring backup: {e}")
            return False
    
    def _restore_compressed_backup(
        self, 
        backup_path: Path,
        restore_paths: Optional[List[Path]] = None,
        overwrite: bool = False
    ) -> bool:
        """Restore from a compressed tar.gz backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract the backup
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(temp_path)
            
            # Determine what to restore
            if restore_paths is None:
                # Restore everything from the backup
                restore_paths = [temp_path]
            else:
                # Map restore paths to what exists in the backup
                actual_restore_paths = []
                for restore_path in restore_paths:
                    # Find corresponding path in backup
                    backup_relative = restore_path.relative_to(self.base_path.parent) \
                        if self.base_path.parent in restore_path.parents else restore_path.name
                    backup_path_item = temp_path / backup_relative
                    if backup_path_item.exists():
                        actual_restore_paths.append(backup_path_item)
                restore_paths = actual_restore_paths
            
            # Copy/restore each path
            for src_path in restore_paths:
                if src_path.exists():
                    # Calculate destination path
                    try:
                        relative_path = src_path.relative_to(temp_path)
                    except ValueError:
                        # If we can't get relative path, use the filename
                        relative_path = src_path.name
                    
                    dest_path = self.base_path.parent / relative_path
                    
                    # Handle overwrite logic
                    if dest_path.exists() and not overwrite:
                        # Skip if exists and not overwriting
                        continue
                    
                    # Remove existing if overwriting
                    if dest_path.exists() and overwrite:
                        if dest_path.is_file():
                            dest_path.unlink()
                        else:
                            shutil.rmtree(dest_path)
                    
                    # Copy the file/directory
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if src_path.is_file():
                        shutil.copy2(src_path, dest_path)
                    else:
                        shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            
            return True
    
    def _restore_uncompressed_backup(
        self, 
        backup_path: Path,
        restore_paths: Optional[List[Path]] = None,
        overwrite: bool = False
    ) -> bool:
        """Restore from an uncompressed directory backup."""
        # Determine what to restore
        if restore_paths is None:
            # Restore everything from the backup
            restore_items = [backup_path]
        else:
            # Map restore paths to what exists in the backup
            restore_items = []
            for restore_path in restore_paths:
                # Find corresponding path in backup
                try:
                    relative_path = restore_path.relative_to(self.base_path.parent)
                except ValueError:
                    relative_path = restore_path.name
                
                backup_path_item = backup_path / relative_path
                if backup_path_item.exists():
                    restore_items.append(backup_path_item)
        
        # Copy/restore each path
        for src_path in restore_items:
            if src_path.exists():
                # Calculate destination path
                try:
                    relative_path = src_path.relative_to(backup_path)
                except ValueError:
                    # If we can't get relative path, use the filename
                    relative_path = src_path.name
                
                dest_path = self.base_path.parent / relative_path
                
                # Handle overwrite logic
                if dest_path.exists() and not overwrite:
                    # Skip if exists and not overwriting
                    continue
                
                # Remove existing if overwriting
                if dest_path.exists() and overwrite:
                    if dest_path.is_file():
                        dest_path.unlink()
                    else:
                        shutil.rmtree(dest_path)
                
                # Copy the file/directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if src_path.is_file():
                    shutil.copy2(src_path, dest_path)
                else:
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
        
        return True
    
    def export_data(
        self, 
        format: ExportFormat = ExportFormat.JSON,
        data_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Path:
        """Export data in various formats."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Determine what data to export
        data_to_export = self._collect_data_for_export(data_types, session_id, user_id)
        
        # Export based on format
        if format == ExportFormat.JSON:
            export_path = self.export_dir / f"kovanica_export_{timestamp}.json"
            with open(export_path, 'w') as f:
                json.dump(data_to_export, f, indent=2, default=str)
        
        elif format == ExportFormat.SQLITE:
            export_path = self.export_dir / f"kovanica_export_{timestamp}.sqlite"
            self._export_to_sqlite(data_to_export, export_path)
        
        elif format == ExportFormat.CSV:
            export_path = self.export_dir / f"kovanica_export_{timestamp}"
            export_path.mkdir(parents=True, exist_ok=True)
            self._export_to_csv(data_to_export, export_path)
        
        elif format == ExportFormat.MARKDOWN:
            export_path = self.export_dir / f"kovanica_export_{timestamp}.md"
            with open(export_path, 'w') as f:
                f.write(self._export_to_markdown(data_to_export))
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        return export_path
    
    def _collect_data_for_export(
        self, 
        data_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect data for export based on specified types and filters."""
        data = {
            "export_info": {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "user_id": user_id,
                "export_version": "1.0"
            }
        }
        
        # If no specific data types requested, export everything
        if data_types is None:
            data_types = ["sessions", "tasks", "memory", "config", "logs"]
        
        # Collect each requested data type
        if "sessions" in data_types:
            data["sessions"] = self._export_sessions(session_id, user_id)
        
        if "tasks" in data_types:
            data["tasks"] = self._export_tasks(session_id, user_id)
        
        if "memory" in data_types:
            data["memory"] = self._export_memory(session_id, user_id)
        
        if "config" in data_types:
            data["config"] = self._export_config()
        
        if "logs" in data_types:
            data["logs"] = self._export_logs(session_id, user_id)
        
        if "plugins" in data_types:
            data["plugins"] = self._export_plugins()
        
        if "skills" in data_types:
            data["skills"] = self._export_skills()
        
        return data
    
    def _export_sessions(self, session_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export session data from the checkpoint database."""
        sessions = []
        try:
            # Try to get from the session database used by the agent
            session_db_path = Path(os.environ.get("AGENT_DB", "/data/agent.sqlite3"))
            if not session_db_path.exists():
                # Fallback to local path
                session_db_path = self.base_path / "agent.sqlite3"
            
            if session_db_path.exists():
                conn = sqlite3.connect(str(session_db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT DISTINCT thread_id FROM checkpoints"
                params = []
                
                if user_id:
                    # This would require joining with user data - simplified for now
                    pass
                
                cursor.execute(query, params)
                thread_ids = cursor.fetchall()
                
                for (thread_id,) in thread_ids:
                    # Get latest checkpoint for this thread
                    cursor.execute(
                        "SELECT * FROM checkpoints WHERE thread_id = ? ORDER BY id DESC LIMIT 1",
                        (thread_id,)
                    )
                    row = cursor.fetchone()
                    if row:
                        sessions.append({
                            "thread_id": thread_id,
                            "checkpoint_data": dict(row),
                            "exported_at": datetime.now().isoformat()
                        })
                
                conn.close()
        except Exception as e:
            sessions = [{"error": f"Failed to export sessions: {e}"}]
        
        return sessions
    
    def _export_tasks(self, session_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export task data."""
        tasks = []
        try:
            task_db_path = self.base_path / ".kovi" / "tasks.sqlite3"
            if task_db_path.exists():
                conn = sqlite3.connect(str(task_db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT * FROM tasks"
                params = []
                
                if session_id:
                    query += " WHERE session_id = ?"
                    params.append(session_id)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    tasks.append(dict(row))
                
                conn.close()
        except Exception as e:
            tasks = [{"error": f"Failed to export tasks: {e}"}]
        
        return tasks
    
    def _export_memory(self, session_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export memory data."""
        memories = []
        try:
            memory_db_path = self.base_path / ".kovi" / "memory.sqlite3"
            if memory_db_path.exists():
                conn = sqlite3.connect(str(memory_db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT * FROM memory"
                params = []
                
                if session_id:
                    query += " WHERE session_id = ?"
                    params.append(session_id)
                
                if user_id:
                    # Add user filter if needed
                    pass
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    memories.append(dict(row))
                
                conn.close()
        except Exception as e:
            memories = [{"error": f"Failed to export memory: {e}"}]
        
        return memories
    
    def _export_config(self) -> Dict[str, Any]:
        """Export configuration data."""
        config_data = {}
        try:
            config_dir = self.base_path / "config"
            if config_dir.exists():
                # Export all config files
                for config_file in config_dir.rglob("*"):
                    if config_file.is_file():
                        try:
                            relative_path = config_file.relative_to(config_dir)
                            with open(config_file, 'r') as f:
                                content = f.read()
                            
                            # Try to parse as JSON if possible
                            try:
                                parsed_content = json.loads(content)
                                config_data[str(relative_path)] = {
                                    "type": "json",
                                    "content": parsed_content
                                }
                            except json.JSONDecodeError:
                                config_data[str(relative_path)] = {
                                    "type": "text",
                                    "content": content
                                }
                        except Exception:
                            # Skip unreadable files
                            pass
        except Exception as e:
            config_data = {"error": f"Failed to export config: {e}"}
        
        return config_data
    
    def _export_logs(self, session_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export log data."""
        logs = []
        try:
            log_dir = self.base_path / "logs"
            if log_dir.exists():
                # Export recent log files
                for log_file in log_dir.glob("*.log*"):
                    try:
                        # Read last 1000 lines or so
                        with open(log_file, 'r') as f:
                            lines = f.readlines()
                        
                        # Get recent lines
                        recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                        
                        logs.append({
                            "file": log_file.name,
                            "path": str(log_file.relative_to(log_dir)),
                            "lines": recent_lines,
                            "line_count": len(lines),
                            "exported_at": datetime.now().isoformat()
                        })
                    except Exception:
                        # Skip unreadable log files
                        pass
        except Exception as e:
            logs = [{"error": f"Failed to export logs: {e}"}]
        
        return logs
    
    def _export_plugins(self) -> List[Dict[str, Any]]:
        """Export plugin information."""
        plugins = []
        try:
            plugins_dir = self.base_path / "plugins"
            if plugins_dir.exists():
                for plugin_dir in plugins_dir.iterdir():
                    if plugin_dir.is_dir():
                        plugin_info = {
                            "name": plugin_dir.name,
                            "path": str(plugin_dir.relative_to(self.base_path)),
                            "files": []
                        }
                        
                        # List files in plugin directory
                        for file_path in plugin_dir.rglob("*"):
                            if file_path.is_file():
                                try:
                                    relative_path = file_path.relative_to(plugin_dir)
                                    plugin_info["files"].append(str(relative_path))
                                except Exception:
                                    pass
                        
                        plugins.append(plugin_info)
        except Exception as e:
            plugins = [{"error": f"Failed to export plugins: {e}"}]
        
        return plugins
    
    def _export_skills(self) -> List[Dict[str, Any]]:
        """Export skill information."""
        skills = []
        try:
            skills_dir = self.base_path / "skills"
            if skills_dir.exists():
                for skill_dir in skills_dir.iterdir():
                    if skill_dir.is_dir():
                        skill_info = {
                            "name": skill_dir.name,
                            "path": str(skill_dir.relative_to(self.base_path)),
                            "files": []
                        }
                        
                        # List files in skill directory
                        for file_path in skill_dir.rglob("*"):
                            if file_path.is_file():
                                try:
                                    relative_path = file_path.relative_to(skill_dir)
                                    skill_info["files"].append(str(relative_path))
                                except Exception:
                                    pass
                        
                        skills.append(skill_info)
        except Exception as e:
            skills = [{"error": f"Failed to export skills: {e}"}]
        
        return skills
    
    def _export_to_sqlite(self, data: Dict[str, Any], export_path: Path):
        """Export data to SQLite format."""
        conn = sqlite3.connect(str(export_path))
        cursor = conn.cursor()
        
        # Create tables for each data type
        for data_type, data_content in data.items():
            if data_type == "export_info":
                continue
            
            # Create a table for this data type
            table_name = f"data_{data_type}"
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            
            # For simplicity, we'll store as JSON in a text column
            # In a real implementation, we'd normalize the data
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL,
                    exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert the data
            if isinstance(data_content, list):
                for item in data_content:
                    cursor.execute(
                        f"INSERT INTO {table_name} (data_json) VALUES (?)",
                        (json.dumps(item, default=str),)
                    )
            elif isinstance(data_content, dict):
                cursor.execute(
                    f"INSERT INTO {table_name} (data_json) VALUES (?)",
                    (json.dumps(data_content, default=str),)
                )
            else:
                # Handle other types
                cursor.execute(
                    f"INSERT INTO {table_name} (data_json) VALUES (?)",
                    (json.dumps({"value": data_content}, default=str),)
                )
        
        conn.commit()
        conn.close()
    
    def _export_to_csv(self, data: Dict[str, Any], export_path: Path):
        """Export data to CSV format."""
        import csv
        
        for data_type, data_content in data.items():
            if data_type == "export_info":
                continue
            
            type_dir = export_path / data_type
            type_dir.mkdir(parents=True, exist_ok=True)
            
            if isinstance(data_content, list) and data_content:
                # Get all possible keys from all items
                if isinstance(data_content[0], dict):
                    fieldnames = set()
                    for item in data_content:
                        if isinstance(item, dict):
                            fieldnames.update(item.keys())
                    
                    fieldnames = list(fieldnames)
                    
                    # Write CSV
                    csv_file = type_dir / "data.csv"
                    with open(csv_file, 'w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        for item in data_content:
                            if isinstance(item, dict):
                                writer.writerow(item)
            
            elif isinstance(data_content, dict):
                # Write as key-value pairs
                csv_file = type_dir / "data.csv"
                with open(csv_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["key", "value"])
                    for key, value in data_content.items():
                        writer.writerow([key, str(value)])
    
    def _export_to_markdown(self, data: Dict[str, Any]) -> str:
        """Export data to Markdown format."""
        md_lines = [
            "# Kovanica Agent Data Export",
            "",
            f"**Exported at:** {datetime.now().isoformat()}",
            ""
        ]
        
        # Add export info if present
        if "export_info" in data:
            md_lines.extend([
                "## Export Information",
                ""
            ])
            for key, value in data["export_info"].items():
                md_lines.append(f"- **{key}:** {value}")
            md_lines.append("")
        
        # Add each data type
        for data_type, data_content in data.items():
            if data_type == "export_info":
                continue
            
            md_lines.extend([
                f"## {data_type.title()}",
                "",
                f"*Count: {len(data_content) if isinstance(data_content, list) else 1 if data_content else 0}*",
                ""
            ])
            
            if isinstance(data_content, list) and data_content:
                if isinstance(data_content[0], dict):
                    # Create a table for list of dicts
                    if data_content:
                        headers = list(data_content[0].keys())
                        md_lines.append("| " + " | ".join(headers) + " |")
                        md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                        
                        for item in data_content[:10]:  # Limit to first 10 items for readability
                            if isinstance(item, dict):
                                row = [str(item.get(h, "")) for h in headers]
                                md_lines.append("| " + " | ".join(row) + " |")
                        
                        if len(data_content) > 10:
                            md_lines.append(f"| ... and {len(data_content) - 10} more |")
                else:
                    # Simple list
                    for item in data_content[:20]:  # Limit to first 20 items
                        md_lines.append(f"- {item}")
                    
                    if len(data_content) > 20:
                        md_lines.append(f"- ... and {len(data_content) - 20} more")
            
            elif isinstance(data_content, dict):
                # Key-value pairs
                for key, value in list(data_content.items())[:20]:  # Limit to first 20
                    md_lines.append(f"- **{key}:** {value}")
                
                if len(data_content) > 20:
                    md_lines.append(f"- ... and {len(data_content) - 20} more")
            
            else:
                # Simple value
                md_lines.append(f"{data_content}")
            
            md_lines.append("")
        
        return "\n".join(md_lines)
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups."""
        backups = []
        try:
            for backup_file in self.backup_dir.iterdir():
                if backup_file.is_file():
                    stat = backup_file.stat()
                    backups.append({
                        "name": backup_file.name,
                        "path": str(backup_file),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": "compressed" if backup_file.suffix == ".gz" else "directory"
                    })
                elif backup_file.is_dir():
                    stat = backup_file.stat()
                    backups.append({
                        "name": backup_file.name,
                        "path": str(backup_file),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": "directory"
                    })
        except Exception:
            pass
        
        # Sort by modification time, newest first
        backups.sort(key=lambda x: x["modified"], reverse=True)
        return backups
    
    def list_exports(self) -> List[Dict[str, Any]]:
        """List available exports."""
        exports = []
        try:
            for export_item in self.export_dir.iterdir():
                if export_item.is_file():
                    stat = export_item.stat()
                    exports.append({
                        "name": export_item.name,
                        "path": str(export_item),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": export_item.suffix[1:] if export_item.suffix else "file"
                    })
                elif export_item.is_dir():
                    stat = export_item.stat()
                    exports.append({
                        "name": export_item.name,
                        "path": str(export_item),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": "directory"
                    })
        except Exception:
            pass
        
        # Sort by modification time, newest first
        exports.sort(key=lambda x: x["modified"], reverse=True)
        return exports


# Global instance
_data_export_import_manager: Optional[DataExportImportManager] = None


def get_data_export_import_manager() -> DataExportImportManager:
    """Get or create the global data export/import manager."""
    global _data_export_import_manager
    if _data_export_import_manager is None:
        _data_export_import_manager = DataExportImportManager()
    return _data_export_import_manager


def init_data_export_import(base_path: Path = None) -> DataExportImportManager:
    """Initialize data export/import with custom base path."""
    global _data_export_import_manager
    _data_export_import_manager = DataExportImportManager(base_path)
    return _data_export_import_manager