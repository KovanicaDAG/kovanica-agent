"""
Shell completion engine for Kovanica CLI (bash, zsh, fish).
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable, Dict, List, Optional

try:
    from rapidfuzz import process, fuzz
except ImportError:
    process = None
    fuzz = None


class CompletionEngine:
    """Generates shell completions for Kovanica CLI."""
    
    def __init__(self, cli: "KovanicaCLI"):
        self.cli = cli
        self.commands = cli.commands
    
    def get_completions(self, words: List[str], word_index: int) -> List[str]:
        """Get completions for the current command line."""
        if word_index == 0:
            # Completing the main command
            return self._complete_main_command(words[0] if words else "")
        
        # Completing subcommand or arguments
        main_cmd = words[0]
        if main_cmd in self.commands:
            return self._complete_command_args(self.commands[main_cmd], words[1:], word_index - 1)
        
        # Try aliases
        for name, cmd in self.commands.items():
            if main_cmd in cmd.aliases:
                return self._complete_command_args(cmd, words[1:], word_index - 1)
        
        return []
    
    def _complete_main_command(self, prefix: str) -> List[str]:
        """Complete main command names."""
        all_commands = []
        for name, cmd in self.commands.items():
            all_commands.append(name)
            all_commands.extend(cmd.aliases)
        
        if not prefix:
            return all_commands
        
        if process:
            # Use fuzzy matching
            results = process.extract(prefix, all_commands, scorer=fuzz.WRatio, limit=20)
            return [r[0] for r in results if r[1] > 50]
        else:
            # Simple prefix matching
            return [c for c in all_commands if c.startswith(prefix)]
    
    def _complete_command_args(self, cmd: "BaseCommand", words: List[str], word_index: int) -> List[str]:
        """Complete arguments for a specific command."""
        # Get the command's parser
        parser = cmd.create_parser()
        
        # For now, return common completions based on command type
        cmd_name = cmd.name
        
        if cmd_name in ("session", "sessions", "s"):
            return self._complete_session_args(words, word_index)
        elif cmd_name in ("config", "cfg"):
            return self._complete_config_args(words, word_index)
        elif cmd_name in ("tools", "tool"):
            return self._complete_tools_args(words, word_index)
        elif cmd_name in ("plugins", "plugin"):
            return self._complete_plugins_args(words, word_index)
        elif cmd_name in ("skills", "skill"):
            return self._complete_skills_args(words, word_index)
        elif cmd_name in ("goal", "goals"):
            return self._complete_goal_args(words, word_index)
        elif cmd_name in ("heartbeat", "hb"):
            return self._complete_heartbeat_args(words, word_index)
        elif cmd_name in ("mcp",):
            return self._complete_mcp_args(words, word_index)
        elif cmd_name in ("model",):
            return self._complete_model_args(words, word_index)
        elif cmd_name in ("theme",):
            return self._complete_theme_args(words, word_index)
        elif cmd_name in ("help", "h", "?"):
            return self._complete_help_args(words, word_index)
        
        return []
    
    def _complete_session_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["list", "resume", "new", "delete", "export", "import", "info"]
        elif word_index == 1 and words[0] in ("resume", "delete", "export", "import", "info"):
            # Complete session IDs
            return self._get_session_ids()
        return []
    
    def _complete_config_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["get", "set", "list", "reset", "edit"]
        elif word_index == 1 and words[0] in ("get", "set", "reset"):
            return self._get_config_keys()
        elif word_index == 1 and words[0] == "edit":
            return ["--scope", "user", "project"]
        return []
    
    def _complete_tools_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["list", "enable", "disable", "info"]
        elif word_index == 1 and words[0] in ("enable", "disable", "info"):
            return self._get_tool_names()
        return []
    
    def _complete_plugins_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["list", "install", "uninstall", "enable", "disable", "update", "details"]
        elif word_index == 1 and words[0] in ("uninstall", "enable", "disable", "update", "details"):
            return self._get_plugin_names()
        return []
    
    def _complete_skills_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["list", "enable", "disable", "info"]
        elif word_index == 1 and words[0] in ("enable", "disable", "info"):
            return self._get_skill_names()
        return []
    
    def _complete_goal_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["set", "subgoal", "list", "status", "complete", "cancel"]
        elif word_index == 1 and words[0] in ("status", "complete", "cancel"):
            return self._get_goal_ids()
        return []
    
    def _complete_heartbeat_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["set", "list", "stop"]
        elif word_index == 1 and words[0] == "stop":
            return self._get_heartbeat_ids()
        return []
    
    def _complete_mcp_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["list", "add", "remove", "test"]
        elif word_index == 1 and words[0] in ("remove", "test"):
            return self._get_mcp_names()
        return []
    
    def _complete_model_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["--list"] + self._get_available_models()
        return []
    
    def _complete_theme_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["--list"] + self.cli.theme.list_themes()
        return []
    
    def _complete_help_args(self, words: List[str], word_index: int) -> List[str]:
        if word_index == 0:
            return ["--all"] + list(self.commands.keys())
        return []
    
    # Data providers (would be implemented with actual data sources)
    def _get_session_ids(self) -> List[str]:
        from pathlib import Path
        sessions_dir = Path.home() / ".kovanica" / "sessions"
        if sessions_dir.exists():
            return [f.stem for f in sessions_dir.glob("*.jsonl")]
        return []
    
    def _get_config_keys(self) -> List[str]:
        return ["model", "theme", "api_url", "api_token", "auto_approve", "verbose", "output_format", "show_timestamps"]
    
    def _get_tool_names(self) -> List[str]:
        return ["search_codebase", "search_kovanica_docs", "read_file", "run_cargo_command", 
                "git_diff_suggest", "query_node_api", "explain_concept", "run_kovanica_cli"]
    
    def _get_plugin_names(self) -> List[str]:
        from pathlib import Path
        plugins_dir = Path.home() / ".kovanica" / "plugins"
        if plugins_dir.exists():
            return [d.name for d in plugins_dir.iterdir() if d.is_dir()]
        return []
    
    def _get_skill_names(self) -> List[str]:
        return ["kovanica-blockchain-developer", "rust-developer", "code-reviewer"]
    
    def _get_goal_ids(self) -> List[str]:
        # Would load from session
        return []
    
    def _get_heartbeat_ids(self) -> List[str]:
        # Would load from session
        return []
    
    def _get_mcp_names(self) -> List[str]:
        return ["filesystem", "github"]
    
    def _get_available_models(self) -> List[str]:
        return [
            "qwen2.5-coder:3b",
            "qwen2.5-coder:7b",
            "qwen2.5-coder:14b",
            "qwen2.5-coder:32b",
            "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
            "gpt-4",
            "gpt-4o",
            "claude-3-5-sonnet",
            "claude-3-opus",
        ]
    
    # Shell completion generation
    def generate_bash_completion(self) -> str:
        """Generate bash completion script."""
        return f'''# Kovanica CLI bash completion
_kovanica_complete() {{
    local cur prev words cword
    _init_completion || return
    
    local completions=($({sys.executable} -m kovanica_agent.cli.completer --complete "${{words[@]}}" --index $cword))
    
    COMPREPLY=($(compgen -W "${{completions[*]}}" -- "$cur"))
}}

complete -F _kovanica_complete kovanica
'''
    
    def generate_zsh_completion(self) -> str:
        """Generate zsh completion script."""
        return f'''# Kovanica CLI zsh completion
#compdef kovanica

_kovanica() {{
    local -a completions
    local -a completions_with_descriptions
    local -a response
    response=($({sys.executable} -m kovanica_agent.cli.completer --complete "${{words[@]}}" --index $CURRENT))
    
    for key in "${{response[@]}}"; do
        completions+=("$key")
    done
    
    if [ -n "$completions" ]; then
        _describe 'completions' completions
    fi
}}

compdef _kovanica kovanica
'''
    
    def generate_fish_completion(self) -> str:
        """Generate fish completion script."""
        return f'''# Kovanica CLI fish completion
function __fish_kovanica_complete
    set -l completions ({sys.executable} -m kovanica_agent.cli.completer --complete "$argv" --index (commandline -opc))
    for completion in $completions
        echo $completion
    end
end

complete -c kovanica -f -a "(__fish_kovanica_complete)"
'''


def main():
    """Entry point for completion generation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica CLI completion generator")
    parser.add_argument("--shell", choices=["bash", "zsh", "fish"], help="Shell to generate completion for")
    parser.add_argument("--complete", nargs="*", help="Words to complete")
    parser.add_argument("--index", type=int, help="Current word index")
    
    args = parser.parse_args()
    
    if args.shell:
        # Generate completion script for shell
        engine = CompletionEngine(None)  # Would need CLI instance
        if args.shell == "bash":
            print(engine.generate_bash_completion())
        elif args.shell == "zsh":
            print(engine.generate_zsh_completion())
        elif args.shell == "fish":
            print(engine.generate_fish_completion())
        return
    
    if args.complete is not None and args.index is not None:
        # This would be called by the shell for actual completions
        # For now, just return empty
        print("")
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()