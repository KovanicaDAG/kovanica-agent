---
key: kovanica-tool-surface
value: "Dev tools: search_codebase, search_kovanica_docs, read_file, run_cargo_command (check/test/clippy/build only), git_diff_suggest (preview, needs /confirm), query_node_api, explain_concept, run_kovanica_cli (read-only explorer cmds only), glob_files, grep_files, edit_file (dry-run only), write_file (preview only), run_bash (whitelisted, 30s cap, shell=False, no network git), task_add/list/done/remove, memory_store/recall/forget, session_list/kill. User tools: search_codebase, search_kovanica_docs, query_node_api, explain_concept, run_kovanica_cli, glob_files, grep_files, memory_recall only."
role: dev
learned_at: 2026-09-12T00:00:00+00:00
source: KOVANICA.md + tools_ext.py
tags: [tooling, kovanica, safety, code-sample]
---

# Kovanica Tool Surface

**As of 2026-09-12 — Claude Code / Codex-style tool surface**

## Dev tools (full access)

| Tool | What it does | Safety |
|------|-------------|--------|
| `search_codebase` | Semantic + keyword search over indexed repo (Qdrant `kovanica_codebase`) | read-only |
| `search_kovanica_docs` | Semantic search over RFCs/tokenomics/GHOSTDAG notes (Qdrant `kovanica_skill_docs`) | read-only |
| `read_file(path, start_line, end_line)` | Read a slice of a repo file | read-only |
| `run_cargo_command(command, args)` | `cargo check|test|clippy|build` in network-disabled sandbox | whitelist only |
| `git_diff_suggest(path, explanation, patch)` | Propose a patch (staged for `/confirm`, never auto-applied) | preview only |
| `query_node_api(endpoint)` | Read-only GET against `/api/head`, `/api/state`, etc. | read-only |
| `explain_concept(term)` | Grounded explanation of a protocol term from code + docs | read-only |
| `run_kovanica_cli(args)` | `kovanica` binary read-only explorer commands | whitelist: head/p2p/bootstrap/state/blocks/balance/address only |
| `glob_files(pattern, path)` | Find files by glob (fnmatch, `**` recursive) | read-only |
| `grep_files(pattern, path, case_sensitive)` | Content search via rg/grep, extension-whitelisted | read-only |
| `edit_file(path, old_str, new_str, regex, replace_all)` | Preview targeted string/regex replace | dry-run only |
| `write_file(path, content, append)` | Preview file creation | preview only |
| `run_bash(command, workdir)` | Whitelisted shell commands | 30s cap, shell=False, no network git |
| `task_add(description)` | Add a todo task for the current session | — |
| `task_list()` | List tasks for the current session | — |
| `task_done(task_id)` | Mark a task done | — |
| `task_remove(task_id)` | Remove a task | — |
| `memory_store(key, value)` | Store a learned fact for future sessions | — |
| `memory_recall(prefix)` | Recall learned facts | read-only |
| `memory_forget(key)` | Forget a learned fact | — |
| `session_list()` | List active LangGraph checkpoint sessions | read-only |
| `session_kill(thread_id)` | Kill a session (delete checkpoint data) | — |

## User tools (read-only)

`search_codebase`, `search_kovanica_docs`, `query_node_api`, `explain_concept`,
`run_kovanica_cli`, `glob_files`, `grep_files`, `memory_recall`.

No file reads, no cargo, no patch proposals, no bash, no edit/write, no session kill.

## Tool conventions

- Tools never emit tool-call JSON in the chat reply. The HTTP interface is prose/JSON, not a tool-execution surface.
- `edit_file` and `write_file` are **preview-only** — they report what *would* happen, never touch the real repo.
- `run_bash` uses `shell=False` with a whitelist. Network-modifying git (push/pull/fetch/clone) is blocked. Default timeout 30s (`KOVANICA_BASH_TIMEOUT`).
- All file paths cited by tools are repo-relative (relative to `REPOS_PATH`).

## New tools added 2026-09-12 (Kovanica agent brain wiring)

- `glob_files`, `grep_files`, `edit_file`, `write_file` — Claude Code/Codex-style file tools
- `run_bash` — whitelisted bash with sandbox sidecar support (`KOVANICA_SANDBOX_URL`)
- `task_*`, `session_*`, `memory_*` — task/session/memory management
- `kovanica repl` — interactive REPL with multi-turn context, `!`-prefixed inline commands, `--json`, `--verbose`, auto-memory, vault integration

## Cross-reference

- `KOVANICA.md` — workspace guide with tool surface table
- `agent/tools_ext.py` — shared tool implementations (imports by both graph.py and kovanica)
- `agent/repl.py` — REPL with all new features
- `markdown-vault/Memory/kovanica-tool-surface.md` — this note
