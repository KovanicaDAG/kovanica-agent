vault: Kovanica agent brain (Obsidian-compatible Markdown vault)
created: 2026-09-12
role: sessions / memory / tasks / knowledge — human-readable, git-trackable

# Markdown.kov — Kovanica agent brain

This vault is the agent's long-term, human-readable, git-trackable memory.

## Folder layout

- `Chats/` — one note per session (transcript + summary + decisions)
- `Memory/` — one note per learned fact (YAML frontmatter + prose)
- `Tasks/` — markdown task lists (one note per session or topic, `- [ ]` / `- [x]`)
- `Notes/` — protocol/RFC notes, engineering conventions, anything you write

## Conventions

- All paths are relative to this vault root.
- `Memory/` notes use YAML frontmatter: `key`, `value`, `role`, `learned_at`.
- `Chats/` notes use a `# Session` heading, then transcript, then `# Summary`.
- `Tasks/` notes use standard markdown task syntax.
- The agent appends to sessions and memory; it does not rewrite history.
- Git tracks changes; the vault is the durable layer on top of Qdrant + SQLite.

## What it does and doesn't replace

- **Replaces**: SQLite `agent/__memory__.db` for learned facts (now Markdown + YAML).
- **Replaces**: ad-hoc session logs with structured `Chats/` notes.
- **Does NOT replace**: Qdrant (semantic search over codebase/docs) — that stays.
- **Does NOT replace**: LangGraph SQLite checkpoint DB — that stays for runtime state.
