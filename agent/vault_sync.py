"""
Kovanica vault sync — skills <-> vault memory, bidirectional.

Mirrors Claude Code vault brain:
- Scan skills/<name>/SKILL.md -> write markdown-vault/Memory/skills-<name>.md
- On session start, recall vault memory into system prompt
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent.parent  # /root/kovanica-agent
VAULT_ROOT = Path(os.environ.get("KOVI_VAULT_PATH", str(_HERE / "markdown-vault"))).resolve()
VAULT_MEMORY = VAULT_ROOT / "Memory"


def _ensure_vault_memory() -> None:
    VAULT_MEMORY.mkdir(parents=True, exist_ok=True)


def _skill_files() -> list[Path]:
    skills_dir = _HERE / "skills"
    if not skills_dir.is_dir():
        return []
    result: list[Path] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            result.append(entry / "SKILL.md")
    return result


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def sync_skill_to_vault(skill_path: Path) -> dict[str, Any]:
    """Sync a single SKILL.md into vault/Memory/skills-<name>.md."""
    fm = _parse_frontmatter(skill_path.read_text(encoding="utf-8", errors="replace"))
    name = fm.get("name", skill_path.parent.name)
    slug = re.sub(r"[^\w-]", "-", name)[:50]
    vault_path = VAULT_MEMORY / f"skills-{slug}.md"
    timestamp = datetime.now(timezone.utc).isoformat()

    body = skill_path.read_text(encoding="utf-8", errors="replace")
    # Strip frontmatter
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", body, count=1, flags=re.DOTALL)
    # Truncate to keep vault notes manageable
    max_chars = 8000
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n\n... (truncated, see {skill_path} for full content)"

    frontmatter = f"""\
---\n\
source: skills/{skill_path.parent.name}/SKILL.md\n\
name: {name}\n\
synced_at: {timestamp}\n\
synced_from: skills\n\
tags: [skill, kovanica]\n\
---\n\
# {name} — synced from skills/{skill_path.parent.name}/SKILL.md\n\
\n\
> This note was auto-synced from the skill file.\n\
> Last synced: {timestamp}\n\
\n\
{body}\
"""
    try:
        _ensure_vault_memory()
        vault_path.write_text(frontmatter, encoding="utf-8")
        return {"status": "synced", "skill": name, "vault_path": str(vault_path)}
    except Exception as exc:
        return {"status": "error", "skill": name, "detail": str(exc)}


def sync_all_skills_to_vault() -> dict[str, Any]:
    """Sync all skills/<name>/SKILL.md into vault/Memory/."""
    skill_paths = _skill_files()
    synced = 0
    failed: list[str] = []
    for sp in skill_paths:
        r = sync_skill_to_vault(sp)
        if r.get("status") == "synced":
            synced += 1
        else:
            failed.append(r.get("skill", sp.parent.name))
    return {
        "status": "ok" if not failed else "partial",
        "synced": synced,
        "total": len(skill_paths),
        "failed": failed,
    }


def vault_recall_for_session(prefix: str = "", limit: int = 20) -> str:
    """Recall vault memory notes and return as Markdown for system prompt injection."""
    _ensure_vault_memory()
    results: list[str] = []
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    for md_file in sorted(VAULT_MEMORY.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            m = pattern.match(text)
            if not m:
                continue
            fm_text = m.group(1)
            fm: dict[str, str] = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            key = fm.get("key", "") or fm.get("name", "")
            if prefix and not (key.startswith(prefix) or fm.get("source", "").startswith(prefix)):
                continue
            # First paragraph of body
            body = text[m.end():].strip()
            first_para = body.split("\n\n")[0][:300] if body else ""
            results.append(f"## [{fm.get('source', 'vault')}] {key}\n{first_para}\n")
        except Exception:
            pass
    if not results:
        return ""
    header = f"## Vault Memory (recalled {datetime.now(timezone.utc).isoformat()})\n"
    return header + "\n".join(results[:limit])


def vault_recall_all(limit: int = 50) -> list[dict[str, str]]:
    """Return all vault memory entries as a list of dicts."""
    _ensure_vault_memory()
    results: list[dict[str, str]] = []
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    for md_file in sorted(VAULT_MEMORY.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            m = pattern.match(text)
            if not m:
                continue
            fm_text = m.group(1)
            fm: dict[str, str] = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            results.append({
                "key": fm.get("key", "") or fm.get("name", md_file.stem),
                "value": fm.get("value", ""),
                "source": fm.get("source", "vault"),
                "learned_ts": fm.get("learned_ts", ""),
                "synced_at": fm.get("synced_at", ""),
            })
        except Exception:
            pass
    return results[:limit]


def vault_sync_status() -> dict[str, Any]:
    """Return current vault sync status."""
    skill_count = len(_skill_files())
    memory_files = list(VAULT_MEMORY.glob("skills-*.md"))
    return {
        "skills_dir": str(_HERE / "skills"),
        "skills_found": skill_count,
        "vault_memory_dir": str(VAULT_MEMORY),
        "vault_skill_notes": len(memory_files),
        "vault_root": str(VAULT_ROOT),
    }


if __name__ == "__main__":
    # Allow: python -m vault_sync
    result = sync_all_skills_to_vault()
    print(result.get("detail", str(result)))
