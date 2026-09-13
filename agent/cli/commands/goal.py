"""
Goal/Heartbeat/Steer commands for autonomous workflows.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .base import BaseCommand, CLIContext, CommandResult


class GoalCommand(BaseCommand):
    """Manage persistent goals for autonomous workflows."""
    
    name = "goal"
    description = "Set and manage persistent cross-turn goals"
    aliases = ["goals"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # set
        set_parser = subparsers.add_parser("set", help="Set a new goal")
        set_parser.add_argument("objective", help="Goal objective")
        set_parser.add_argument("--auto-continue", action="store_true", help="Auto-continue until goal complete")
        
        # subgoal
        subgoal_parser = subparsers.add_parser("subgoal", help="Add a sub-goal")
        subgoal_parser.add_argument("objective", help="Sub-goal objective")
        
        # list
        list_parser = subparsers.add_parser("list", help="List active goals")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # status
        status_parser = subparsers.add_parser("status", help="Show goal progress")
        status_parser.add_argument("goal_id", nargs="?", help="Goal ID (default: current)")
        
        # complete
        complete_parser = subparsers.add_parser("complete", help="Mark goal as complete")
        complete_parser.add_argument("goal_id", nargs="?", help="Goal ID (default: current)")
        
        # cancel
        cancel_parser = subparsers.add_parser("cancel", help="Cancel a goal")
        cancel_parser.add_argument("goal_id", nargs="?", help="Goal ID (default: current)")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "set":
            return self._set_goal(parsed)
        elif parsed.subcommand == "subgoal":
            return self._set_subgoal(parsed)
        elif parsed.subcommand == "list":
            return self._list_goals(parsed)
        elif parsed.subcommand == "status":
            return self._goal_status(parsed)
        elif parsed.subcommand == "complete":
            return self._complete_goal(parsed)
        elif parsed.subcommand == "cancel":
            return self._cancel_goal(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _get_goals(self) -> list:
        # Placeholder - would load from session/goal store
        return []
    
    def _save_goals(self, goals: list) -> None:
        # Placeholder
        pass
    
    def _set_goal(self, parsed) -> CommandResult:
        import uuid
        from datetime import datetime
        
        goal_id = str(uuid.uuid4())[:8]
        goal = {
            "id": goal_id,
            "objective": parsed.objective,
            "created": datetime.now().isoformat(),
            "status": "active",
            "auto_continue": parsed.auto_continue,
            "subgoals": [],
            "progress": 0,
        }
        
        goals = self._get_goals()
        goals.append(goal)
        self._save_goals(goals)
        
        # Set as current goal in session
        self.cli.session.set_current_goal(goal_id)
        
        return CommandResult(
            success=True,
            output=f"Goal set: {goal_id}\nObjective: {parsed.objective}" + 
                   ("\nAuto-continue enabled" if parsed.auto_continue else ""),
            data=goal
        )
    
    def _set_subgoal(self, parsed) -> CommandResult:
        current_goal_id = self.cli.session.get_current_goal()
        if not current_goal_id:
            return CommandResult(success=False, error="No active goal. Set a goal first with /goal set")
        
        goals = self._get_goals()
        goal = next((g for g in goals if g["id"] == current_goal_id), None)
        
        if not goal:
            return CommandResult(success=False, error=f"Goal not found: {current_goal_id}")
        
        import uuid
        from datetime import datetime
        
        subgoal_id = str(uuid.uuid4())[:8]
        subgoal = {
            "id": subgoal_id,
            "objective": parsed.objective,
            "created": datetime.now().isoformat(),
            "status": "active",
        }
        
        goal["subgoals"].append(subgoal)
        self._save_goals(goals)
        
        return CommandResult(
            success=True,
            output=f"Sub-goal added to {current_goal_id}: {subgoal_id}\nObjective: {parsed.objective}",
            data=subgoal
        )
    
    def _list_goals(self, parsed) -> CommandResult:
        goals = self._get_goals()
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(goals, indent=2))
        
        if not goals:
            return CommandResult(success=True, output="No goals set.")
        
        lines = ["Active Goals:"]
        for g in goals:
            status = "[green]active[/green]" if g["status"] == "active" else "[yellow]completed[/yellow]" if g["status"] == "completed" else "[red]cancelled[/red]"
            auto = " [auto-continue]" if g.get("auto_continue") else ""
            lines.append(f"  {g['id']}  {status}{auto}")
            lines.append(f"    {g['objective']}")
            if g["subgoals"]:
                for sg in g["subgoals"]:
                    sg_status = "[green]active[/green]" if sg["status"] == "active" else "[yellow]done[/yellow]"
                    lines.append(f"    - {sg['id']} {sg_status}: {sg['objective']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _goal_status(self, parsed) -> CommandResult:
        goal_id = parsed.goal_id or self.cli.session.get_current_goal()
        if not goal_id:
            return CommandResult(success=False, error="No active goal")
        
        goals = self._get_goals()
        goal = next((g for g in goals if g["id"] == goal_id), None)
        
        if not goal:
            return CommandResult(success=False, error=f"Goal not found: {goal_id}")
        
        lines = [
            f"Goal: {goal['id']}",
            f"Objective: {goal['objective']}",
            f"Status: {goal['status']}",
            f"Progress: {goal['progress']}%",
            f"Auto-continue: {'Yes' if goal.get('auto_continue') else 'No'}",
            f"Created: {goal['created']}",
        ]
        
        if goal["subgoals"]:
            lines.append("\nSub-goals:")
            for sg in goal["subgoals"]:
                sg_status = "active" if sg["status"] == "active" else "completed"
                lines.append(f"  {sg['id']} [{sg_status}]: {sg['objective']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _complete_goal(self, parsed) -> CommandResult:
        goal_id = parsed.goal_id or self.cli.session.get_current_goal()
        if not goal_id:
            return CommandResult(success=False, error="No active goal")
        
        goals = self._get_goals()
        goal = next((g for g in goals if g["id"] == goal_id), None)
        
        if not goal:
            return CommandResult(success=False, error=f"Goal not found: {goal_id}")
        
        goal["status"] = "completed"
        goal["progress"] = 100
        goal["completed_at"] = "now"  # Would use datetime in real impl
        self._save_goals(goals)
        
        self.cli.session.clear_current_goal()
        
        return CommandResult(success=True, output=f"Goal completed: {goal_id}")
    
    def _cancel_goal(self, parsed) -> CommandResult:
        goal_id = parsed.goal_id or self.cli.session.get_current_goal()
        if not goal_id:
            return CommandResult(success=False, error="No active goal")
        
        goals = self._get_goals()
        goal = next((g for g in goals if g["id"] == goal_id), None)
        
        if not goal:
            return CommandResult(success=False, error=f"Goal not found: {goal_id}")
        
        goal["status"] = "cancelled"
        self._save_goals(goals)
        
        self.cli.session.clear_current_goal()
        
        return CommandResult(success=True, output=f"Goal cancelled: {goal_id}")


class HeartbeatCommand(BaseCommand):
    """Manage recurring heartbeat prompts."""
    
    name = "heartbeat"
    description = "Set recurring prompts on idle intervals"
    aliases = ["hb"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # set
        set_parser = subparsers.add_parser("set", help="Set a heartbeat")
        set_parser.add_argument("interval", help="Interval (e.g. 30s, 5m, 1h)")
        set_parser.add_argument("prompt", help="Prompt to send on each heartbeat")
        
        # list
        list_parser = subparsers.add_parser("list", help="List active heartbeats")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # stop
        stop_parser = subparsers.add_parser("stop", help="Stop a heartbeat")
        stop_parser.add_argument("heartbeat_id", nargs="?", help="Heartbeat ID (default: all)")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "set":
            return self._set_heartbeat(parsed)
        elif parsed.subcommand == "list":
            return self._list_heartbeats(parsed)
        elif parsed.subcommand == "stop":
            return self._stop_heartbeat(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _set_heartbeat(self, parsed) -> CommandResult:
        import uuid
        from datetime import datetime
        
        hb_id = str(uuid.uuid4())[:8]
        heartbeat = {
            "id": hb_id,
            "interval": parsed.interval,
            "prompt": parsed.prompt,
            "created": datetime.now().isoformat(),
            "status": "active",
        }
        
        # Store in session
        heartbeats = self.cli.session.get_heartbeats()
        heartbeats.append(heartbeat)
        self.cli.session.set_heartbeats(heartbeats)
        
        return CommandResult(
            success=True,
            output=f"Heartbeat set: {hb_id}\nInterval: {parsed.interval}\nPrompt: {parsed.prompt}",
            data=heartbeat
        )
    
    def _list_heartbeats(self, parsed) -> CommandResult:
        heartbeats = self.cli.session.get_heartbeats()
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(heartbeats, indent=2))
        
        if not heartbeats:
            return CommandResult(success=True, output="No active heartbeats.")
        
        lines = ["Active Heartbeats:"]
        for hb in heartbeats:
            status = "[green]active[/green]" if hb["status"] == "active" else "[red]stopped[/red]"
            lines.append(f"  {hb['id']}  {status}  every {hb['interval']}")
            lines.append(f"    {hb['prompt']}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _stop_heartbeat(self, parsed) -> CommandResult:
        heartbeats = self.cli.session.get_heartbeats()
        
        if not parsed.heartbeat_id:
            # Stop all
            for hb in heartbeats:
                hb["status"] = "stopped"
            self.cli.session.set_heartbeats(heartbeats)
            return CommandResult(success=True, output="Stopped all heartbeats")
        
        hb = next((h for h in heartbeats if h["id"] == parsed.heartbeat_id), None)
        if not hb:
            return CommandResult(success=False, error=f"Heartbeat not found: {parsed.heartbeat_id}")
        
        hb["status"] = "stopped"
        self.cli.session.set_heartbeats(heartbeats)
        
        return CommandResult(success=True, output=f"Stopped heartbeat: {parsed.heartbeat_id}")


class SteerCommand(BaseCommand):
    """Inject mid-run guidance."""
    
    name = "steer"
    description = "Inject guidance after next tool call"
    aliases = []
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        parser.add_argument("guidance", nargs="?", help="Guidance to inject")
        parser.add_argument("--clear", action="store_true", help="Clear pending steer guidance")
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.clear:
            self.cli.session.set_steer_guidance(None)
            return CommandResult(success=True, output="Steer guidance cleared")
        
        if not parsed.guidance:
            current = self.cli.session.get_steer_guidance()
            if current:
                return CommandResult(success=True, output=f"Current steer guidance: {current}")
            else:
                return CommandResult(success=True, output="No steer guidance set")
        
        self.cli.session.set_steer_guidance(parsed.guidance)
        return CommandResult(success=True, output=f"Steer guidance set (will apply after next tool call): {parsed.guidance}")


class QueueCommand(BaseCommand):
    """Queue prompts for next turn."""
    
    name = "queue"
    description = "Queue prompts for next turn without interrupting"
    aliases = ["q"]
    
    def create_parser(self) -> argparse.ArgumentParser:
        parser = super().create_parser()
        subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")
        
        # add
        add_parser = subparsers.add_parser("add", help="Add prompt to queue")
        add_parser.add_argument("prompt", help="Prompt to queue")
        
        # list
        list_parser = subparsers.add_parser("list", help="List queued prompts")
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")
        
        # clear
        clear_parser = subparsers.add_parser("clear", help="Clear queue")
        
        return parser
    
    def execute(self, args: list[str]) -> CommandResult:
        if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
            return CommandResult(success=True, output=self.format_help())
        
        parsed = self.parse_args(args)
        
        if parsed.subcommand == "add":
            return self._add_queue(parsed)
        elif parsed.subcommand == "list":
            return self._list_queue(parsed)
        elif parsed.subcommand == "clear":
            return self._clear_queue(parsed)
        else:
            return CommandResult(success=False, error=f"Unknown subcommand: {parsed.subcommand}")
    
    def _add_queue(self, parsed) -> CommandResult:
        queue = self.cli.session.get_queue()
        queue.append(parsed.prompt)
        self.cli.session.set_queue(queue)
        return CommandResult(success=True, output=f"Queued: {parsed.prompt}")
    
    def _list_queue(self, parsed) -> CommandResult:
        queue = self.cli.session.get_queue()
        
        if parsed.json:
            return CommandResult(success=True, output=json.dumps(queue, indent=2))
        
        if not queue:
            return CommandResult(success=True, output="Queue is empty.")
        
        lines = ["Queued Prompts:"]
        for i, prompt in enumerate(queue):
            lines.append(f"  {i+1}. {prompt}")
        
        return CommandResult(success=True, output="\n".join(lines))
    
    def _clear_queue(self, parsed) -> CommandResult:
        self.cli.session.set_queue([])
        return CommandResult(success=True, output="Queue cleared")


class PromptCommand(BaseCommand):
    """Open $EDITOR for multi-line prompt composition."""
    
    name = "prompt"
    description = "Open $EDITOR to compose a multi-line prompt"
    aliases = ["compose"]
    
    def execute(self, args: list[str]) -> CommandResult:
        import subprocess
        import os
        import tempfile
        
        editor = os.environ.get("EDITOR", "vi")
        
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as f:
            f.write("# Compose your prompt below\n")
            temp_path = f.name
        
        try:
            subprocess.run([editor, temp_path], check=True)
            
            with open(temp_path) as f:
                content = f.read()
            
            # Remove comment lines
            lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
            prompt = "\n".join(lines).strip()
            
            os.unlink(temp_path)
            
            if not prompt:
                return CommandResult(success=False, error="Empty prompt")
            
            # Send to chat
            return CommandResult(success=True, output=prompt, data={"prompt": prompt, "send_to_chat": True})
            
        except subprocess.CalledProcessError:
            os.unlink(temp_path)
            return CommandResult(success=False, error=f"Editor {editor} exited with error")
        except FileNotFoundError:
            os.unlink(temp_path)
            return CommandResult(success=False, error=f"Editor not found: {editor}")