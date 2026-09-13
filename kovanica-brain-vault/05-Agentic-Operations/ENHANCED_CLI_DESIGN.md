# Enhanced Kovanica CLI Design

Based on research of Claude Code, Grok Build, and Hermes Agent best practices.

## Architecture Overview

```
kovanica/
├── kovanica                    # Main CLI entrypoint (enhanced)
├── agent/
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── commands/           # Slash command implementations
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Base command class
│   │   │   ├── session.py      # Session management commands
│   │   │   ├── config.py       # Config commands
│   │   │   ├── tools.py        # Tool management commands
│   │   │   ├── memory.py       # Memory commands
│   │   │   ├── plugins.py      # Plugin commands
│   │   │   ├── theme.py        # Theme commands
│   │   │   ├── mcp.py          # MCP commands
│   │   │   ├── goal.py         # Goal/heartbeat/steer commands
│   │   │   └── help.py         # Help/fuzzy search
│   │   ├── session.py          # Session management (resume, continue, fork)
│   │   ├── completer.py        # Shell completions (bash/zsh/fish)
│   │   ├── output.py           # JSON output modes (json, stream-json)
│   │   ├── theme.py            # YAML theming system
│   │   ├── plugin.py           # Plugin system (manifest + commands + hooks + MCP)
│   │   ├── memory.py           # Memory provider interface
│   │   ├── goal.py             # Goal/heartbeat/steer engine
│   │   ├── worktree.py         # Worktree-aware sessions
│   │   └── repl.py             # Enhanced REPL with slash commands
│   ├── kovanica_sdk.py         # Existing SDK (keep)
│   └── ...                     # Other existing files
```

## Feature Implementation Plan

### 1. Slash Command System with Fuzzy Search
- **Pattern**: `/command [args]` with Tab/Enter selection
- **Built-in commands**: `/model`, `/compact`, `/always-approve`, `/new`, `/theme`, `/config`, `/permissions`, `/hooks`, `/mcp`, `/skills`, `/tools`, `/memory`, `/goal`, `/heartbeat`, `/steer`, `/queue`, `/prompt`, `/history`, `/jump`, `/timeline`, `/help`
- **Custom commands**: Markdown files in `.kovanica/commands/` or plugin `commands/` dirs with YAML frontmatter
- **Fuzzy search**: Use `fuzzywuzzy` or `rapidfuzz` for command matching

### 2. Session Management
- **`--resume <session-id>`**: Resume specific session
- **`--continue`**: Resume most recent session
- **`--fork`**: Fork session (new ID, keeps history)
- **`--teleport <session-id>`**: Teleport cloud session locally
- **Session storage**: JSONL transcripts at `~/.kovanica/sessions/`
- **Lineage-based sessions**: Named lineages with multiple sessions (Hermes pattern)

### 3. JSON Output Modes
- **`--output-format json`**: Single JSON envelope
- **`--output-format stream-json`**: Streaming JSON (print mode)
- **`--output-format text`**: Default human-readable

### 4. Plugin System
- **Manifest**: `.kovanica-plugin/plugin.json` with name, version, commands, agents, skills, hooks, mcpServers
- **Structure**:
  ```
  plugin-name/
  ├── .kovanica-plugin/plugin.json
  ├── commands/
  ├── agents/
  ├── skills/
  ├── hooks/hooks.json
  ├── .mcp.json
  ├── scripts/
  └── lib/
  ```
- **Hook events**: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`
- **MCP servers**: Via `.mcp.json` in plugins

### 5. Memory Providers (Pluggable)
- **Interface**: `MemoryProvider` base class with `name()`, `is_available()`, `sync_turn()`, `prefetch()`, `get_tool_schemas()`
- **Built-in providers**: Local JSONL, SQLite, Vector DB
- **External providers**: ByteRover, Supermemory (Hermes pattern)
- **Approval gate**: `/memory pending`, `/memory approve/reject`

### 6. Goal/Heartbeat/Steer for Autonomous Workflows
- **`/goal <objective>`**: Persistent cross-turn objective with auto-continue
- **`/subgoal <objective>`**: Sub-goal within parent goal
- **`/heartbeat <interval> <prompt>`**: Recurring prompts on idle intervals
- **`/steer <guidance>`**: Inject mid-run guidance after next tool call
- **`/queue <prompt>`**: Queue prompts for next turn without interrupting
- **`/refine`**: Trigger background memory/skill review

### 7. Shell Completions
- **`kovanica completion bash`**: Generate bash completions
- **`kovanica completion zsh`**: Generate zsh completions
- **`kovanica completion fish`**: Generate fish completions
- **Profile/subcommand completion included**

### 8. YAML Theming
- **Theme files**: `~/.kovanica/themes/*.yaml`
- **3-layer palette**: background, midground, foreground with alpha
- **Typography**: fontSans, fontMono, fontDisplay, fontUrl, baseSize, lineHeight
- **Layout variants**: standard, cockpit, tiled
- **Component styles**: card, header, tab, sidebar, backdrop, footer, progress, badge, page
- **Color overrides**: primary, accent, ring, destructive, border
- **Custom CSS** injection

### 9. Worktree-Aware Sessions
- **`--worktree=name`**: Named worktree
- **`--ref=branch`**: Git ref for worktree
- **Session isolation per worktree**

### 10. Multi-Platform Messaging Gateway (Future)
- **Telegram, Discord, Slack, WhatsApp** integration
- **Shared memory across platforms**

## Implementation Priority

### Phase 1: Core Enhancements (High Priority)
1. Slash command system with fuzzy search
2. Session management (--resume, --continue, --fork)
3. JSON output modes (json, stream-json)
4. Enhanced REPL with slash commands

### Phase 2: Extensibility (High Priority)
5. Plugin system with manifest + commands + hooks + MCP
6. Memory providers as pluggable interface
7. Shell completions for bash/zsh/fish

### Phase 3: Advanced Features (Medium Priority)
8. Goal/heartbeat/steer for autonomous workflows
9. YAML theming with component-level customization
10. Worktree-aware sessions

## Technical Decisions

### Dependencies to Add
- `rapidfuzz` - Fuzzy search for commands
- `pyyaml` - YAML theming (already likely present)
- `argcomplete` - Shell completions
- `rich` - Enhanced terminal output (already likely present)

### Configuration
- **User config**: `~/.kovanica/settings.json` (3-tier: user < project < policy)
- **Project config**: `.kovanica/settings.json`
- **Themes**: `~/.kovanica/themes/`
- **Plugins**: `~/.kovanica/plugins/` and `.kovanica/plugins/`
- **Sessions**: `~/.kovanica/sessions/`
- **Memory**: `~/.kovanica/memory/`

### Backward Compatibility
- Keep existing `kovanica chat`, `kovanica search`, etc. commands
- Add new slash commands in REPL mode
- New flags (`--output-format`, `--resume`, etc.) are additive

## Verification Plan

Each feature will be verified with:
1. Unit tests for core logic
2. Integration tests for CLI commands
3. Manual verification of REPL interactions
4. Shell completion generation testing
5. Plugin loading/unloading testing
6. Session persistence/resume testing