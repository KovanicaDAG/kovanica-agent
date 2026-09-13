"""
Session management commands for Kovanica CLI.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Optional

from .base import BaseCommand, CLIContext, CommandResult


class SessionCommand(BaseCommand):
    """Manage conversation sessions."""
    
    name = "session"
    description = "Manage conversation sessions (list, resume, fork, delete)"
    aliases = ["sessions", "s"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # list
        list_parser = subparsers.add_parser("list", help="List all sessions")
        list_parser.add_argument("--limit", type=int, default=50, help="Max sessions to show")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        list_parser.add_argument("--worktree", help="Filter by worktree name or path")
        list_parser.add_argument("--all-worktrees", action="store_true", help="Show sessions from all worktrees")
        
        # resume
        resume_parser = subparsers.add_parser("resume", help="Resume a session")
        resume_parser.add_argument("session_id", nargs="?", help="Session ID to resume (or 'latest')")
        resume_parser.add_argument("--fork", action="store_true", help="Fork the session (new ID, keeps history)")
        resume_parser.add_argument("--worktree", help="Prefer sessions from specific worktree")
        
        # new
        new_parser = subparsers.add_parser("new", help="Start a new session")
        new_parser.add_argument("name", nargs="?", help="Optional session name")
        
        # delete
        delete_parser = subparsers.add_parser("delete", help="Delete a session")
        delete_parser.add_argument("session_id", help="Session ID to delete")
        delete_parser.add_argument("--force", action="store_true", help="Skip confirmation")
        
        # export
        export_parser = subparsers.add_parser("export", help="Export session to JSONL")
        export_parser.add_argument("session_id", help="Session ID to export")
        export_parser.add_argument("--output", "-o", help="Output file path")
        export_parser.add_argument("--redact", action="store_true", help="Redact sensitive data")
        
        # import
        import_parser = subparsers.add_parser("import", help="Import session from JSONL")
        import_parser.add_argument("file", help="JSONL file to import")
        import_parser.add_argument("--name", help="Name for imported session")
        
        # info
        info_parser = subparsers.add_parser("info", help="Show session details")
        info_parser.add_argument("session_id", nargs="?", help="Session ID (default: current)")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "list":
            return self._list_sessions(parsed)
        elif parsed.subcommand == "resume":
            return self._resume_session(parsed)
        elif parsed.subcommand == "new":
            return self._new_session(parsed)
        elif parsed.subcommand == "delete":
            return self._delete_session(parsed)
        elif parsed.subcommand == "export":
            return self._export_session(parsed)
        elif parsed.subcommand == "import":
            return self._import_session(parsed)
        elif parsed.subcommand == "info":
            return self._session_info(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_sessions_dir(self) -> Path:
        """Get the sessions directory."""
        base = Path.home() / ".kovanica" / "sessions"
        base.mkdir(parents=True, exist_ok=True)
        return base
    
    def _list_sessions(self, parsed) -> CommandResult:
        sessions_dir = self._get_sessions_dir()
        sessions = []
        
        # Get current worktree for default filtering
        current_worktree = self.cli.session.get_worktree_info()
        current_worktree_name = current_worktree.get("name")
        current_worktree_root = current_worktree.get("root")
        
        # Determine filter
        filter_worktree = parsed.worktree
        show_all = parsed.all_worktrees
        
        for session_file in sorted(sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True):
            if parsed.limit and len(sessions) >= parsed.limit:
                break
            
            # Read first line for metadata
            try:
                with open(session_file) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        meta = json.loads(first_line)
                        
                        # Get worktree info from session
                        session_worktree = meta.get("worktree", {})
                        session_worktree_name = session_worktree.get("name")
                        session_worktree_root = session_worktree.get("root")
                        
                        # Apply worktree filter
                        if not show_all and filter_worktree:
                            # Filter by provided worktree name/path
                            if filter_worktree not in (session_worktree_name or "", session_worktree_root or ""):
                                continue
                        elif not show_all and not filter_worktree and current_worktree_name:
                            # Default: filter to current worktree
                            if current_worktree_name != session_worktree_name and current_worktree_root != session_worktree_root:
                                continue
                        
                        sessions.append({
                            "id": session_file.stem,
                            "title": meta.get("title", "Untitled"),
                            "created": meta.get("created", ""),
                            "updated": meta.get("updated", ""),
                            "turns": meta.get("turns", 0),
                            "model": meta.get("model", ""),
                            "worktree": session_worktree_name,
                            "worktree_root": session_worktree_root,
                        })
            except Exception:
                sessions.append({
                    "id": session_file.stem,
                    "title": "Unknown",
                    "created": "",
                    "updated": "",
                    "turns": 0,
                    "model": "",
                    "worktree": None,
                    "worktree_root": None,
                })
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(sessions, indent=2), data=sessions)
        
        if not sessions:
            return CommandResult(success=True, output="No sessions found.")
        
        lines = ["Sessions:"]
        for s in sessions:
            wt_info = f"  [{s['worktree']}]" if s['worktree'] else ""
            lines.append(f"  {s['id']}  |  {s['title']}  |  {s['turns']} turns  |  {s['model']}{wt_info}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _resume_session(self, parsed) -> CommandResult:
        sessions_dir = self._get_sessions_dir()
        
        # Get current worktree for default filtering
        current_worktree = self.cli.session.get_worktree_info()
        current_worktree_name = current_worktree.get("name")
        current_worktree_root = current_worktree.get("root")
        
        # Determine worktree filter for "latest"
        filter_worktree = parsed.worktree
        if not filter_worktree and not parsed.session_id:
            filter_worktree = current_worktree_name
        
        if not parsed.session_id or parsed.session_id == "latest":
            # Find most recent session (optionally filtered by worktree)
            session_files = sorted(sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
            
            if filter_worktree:
                # Filter by worktree
                filtered_files = []
                for sf in session_files:
                    try:
                        with open(sf) as f:
                            first_line = f.readline().strip()
                            if first_line:
                                meta = json.loads(first_line)
                                session_worktree = meta.get("worktree", {})
                                session_worktree_name = session_worktree.get("name")
                                session_worktree_root = session_worktree.get("root")
                                if filter_worktree in (session_worktree_name or "", session_worktree_root or ""):
                                    filtered_files.append(sf)
                    except Exception:
                        pass
                session_files = filtered_files
            
            if not session_files:
                if filter_worktree:
                    return CommandResult(success=False, error=f"No sessions found for worktree: {filter_worktree}")
                return CommandResult(success=False, error="No sessions found to resume")
            session_file = session_files[0]
        else:
            session_file = sessions_dir / f"{parsed.session_id}.jsonl"
            if not session_file.exists():
                return CommandResult(success=False, error=f"Session not found: {parsed.session_id}")
        
        # Load session
        try:
            with open(session_file) as f:
                lines = f.readlines()
            
            if not lines:
                return CommandResult(success=False, error="Session file is empty")
            
            meta = json.loads(lines[0])
            session_id = session_file.stem
            
            if parsed.fork:
                # Create new session with same history
                import uuid
                new_id = str(uuid.uuid4())[:8]
                new_file = sessions_dir / f"{new_id}.jsonl"
                
                # Copy with new ID in metadata
                new_meta = meta.copy()
                new_meta["id"] = new_id
                new_meta["forked_from"] = session_id
                # Update worktree to current
                new_meta["worktree"] = self.cli.session.get_worktree_info()
                
                with open(new_file, "w") as f:
                    f.write(json.dumps(new_meta) + "\n")
                    f.writelines(lines[1:])
                
                self.cli.session.load_session(new_id)
                return CommandResult(
                    success=True, 
                    output=f"Forked session {session_id} -> {new_id}",
                    data={"session_id": new_id, "forked_from": session_id}
                )
            else:
                self.cli.session.load_session(session_id)
                return CommandResult(
                    success=True,
                    output=f"Resumed session: {session_id} ({meta.get('title', 'Untitled')})",
                    data={"session_id": session_id}
                )
        except Exception as e:
            return CommandResult(success=False, error=f"Failed to resume session: {e}")
    
    def _new_session(self, parsed) -> CommandResult:
        import uuid
        from datetime import datetime
        
        session_id = str(uuid.uuid4())[:8]
        sessions_dir = self._get_sessions_dir()
        session_file = sessions_dir / f"{session_id}.jsonl"
        
        meta = {
            "id": session_id,
            "title": parsed.name or "New Session",
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "turns": 0,
            "model": self.cli.config.get("model", ""),
        }
        
        with open(session_file, "w") as f:
            f.write(json.dumps(meta) + "\n")
        
        self.cli.session.load_session(session_id)
        return CommandResult(
            success=True,
            output=f"Started new session: {session_id}",
            data={"session_id": session_id}
        )
    
    def _delete_session(self, parsed) -> CommandResult:
        sessions_dir = self._get_sessions_dir()
        session_file = sessions_dir / f"{parsed.session_id}.jsonl"
        
        if not session_file.exists():
            return CommandResult(success=False, error=f"Session not found: {parsed.session_id}")
        
        if not parsed.force:
            # In a real CLI, we'd prompt for confirmation
            # For now, just require --force
            return CommandResult(success=False, error="Use --force to confirm deletion")
        
        session_file.unlink()
        return CommandResult(success=True, output=f"Deleted session: {parsed.session_id}")
    
    def _export_session(self, parsed) -> CommandResult:
        sessions_dir = self._get_sessions_dir()
        session_file = sessions_dir / f"{parsed.session_id}.jsonl"
        
        if not session_file.exists():
            return CommandResult(success=False, error=f"Session not found: {parsed.session_id}")
        
        output_path = Path(parsed.output) if parsed.output else Path.cwd() / f"{parsed.session_id}.jsonl"
        
        try:
            with open(session_file) as src, open(output_path, "w") as dst:
                for line in src:
                    if parsed.redact:
                        # Redact sensitive fields
                        try:
                            obj = json.loads(line)
                            # Redact API keys, tokens, etc.
                            if "api_key" in obj:
                                obj["api_key"] = "[REDACTED]"
                            if "token" in obj:
                                obj["token"] = "[REDACTED]"
                            line = json.dumps(obj) + "\n"
                        except Exception:
                            pass
                    dst.write(line)
            
            return CommandResult(success=True, output=f"Exported to {output_path}")
        except Exception as e:
            return CommandResult(success=False, error=f"Export failed: {e}")
    
    def _import_session(self, parsed) -> CommandResult:
        import uuid
        from datetime import datetime
        
        input_file = Path(parsed.file)
        if not input_file.exists():
            return CommandResult(success=False, error=f"File not found: {parsed.file}")
        
        session_id = str(uuid.uuid4())[:8]
        sessions_dir = self._get_sessions_dir()
        session_file = sessions_dir / f"{session_id}.jsonl"
        
        try:
            with open(input_file) as src, open(session_file, "w") as dst:
                first = True
                for line in src:
                    if first:
                        try:
                            obj = json.loads(line)
                            obj["id"] = session_id
                            obj["title"] = parsed.name or obj.get("title", "Imported Session")
                            obj["imported_at"] = datetime.now().isoformat()
                            line = json.dumps(obj) + "\n"
                        except Exception:
                            pass
                        first = False
                    dst.write(line)
            
            self.cli.session.load_session(session_id)
            return CommandResult(
                success=True,
                output=f"Imported session as: {session_id}",
                data={"session_id": session_id}
            )
        except Exception as e:
            return CommandResult(success=False, error=f"Import failed: {e}")
    
    def _session_info(self, parsed) -> CommandResult:
        session_id = parsed.session_id or self.cli.session.current_id
        if not session_id:
            return CommandResult(success=False, error="No active session")
        
        sessions_dir = self._get_sessions_dir()
        session_file = sessions_dir / f"{session_id}.jsonl"
        
        if not session_file.exists():
            return CommandResult(success=False, error=f"Session not found: {session_id}")
        
        try:
            with open(session_file) as f:
                lines = f.readlines()
            
            meta = json.loads(lines[0]) if lines else {}
            turns = len(lines) - 1
            
            worktree = meta.get("worktree", {})
            worktree_name = worktree.get("name")
            worktree_root = worktree.get("root")
            
            info = [
                f"Session: {session_id}",
                f"Title: {meta.get('title', 'Untitled')}",
                f"Created: {meta.get('created', 'Unknown')}",
                f"Updated: {meta.get('updated', 'Unknown')}",
                f"Turns: {turns}",
                f"Model: {meta.get('model', 'Unknown')}",
                f"Forked from: {meta.get('forked_from', 'N/A')}",
            ]
            
            if worktree_name:
                info.append(f"Worktree: {worktree_name}")
            if worktree_root:
                info.append(f"Worktree Root: {worktree_root}")
            
            return CommandResult(success=True, output="\n".join(info), data=meta)
        except Exception as e:
            return CommandResult(success=False, error=f"Failed to read session: {e}")


class NewCommand(BaseCommand):
    """Start a new session (alias for /session new)."""
    
    name = "new"
    description = "Start a new conversation session"
    aliases = []
    
    def execute(self, args: list[str]) -> CommandResult:
        session_cmd = SessionCommand(self.cli)
        return session_cmd.execute(["new"] + args)


class ResumeCommand(BaseCommand):
    """Resume a session (alias for /session resume)."""
    
    name = "resume"
    description = "Resume a previous session"
    aliases = ["continue"]
    
    def execute(self, args: list[str]) -> CommandResult:
        session_cmd = SessionCommand(self.cli)
        resume_args = ["resume"]
        if args:
            resume_args.extend(args)
        return session_cmd.execute(resume_args)