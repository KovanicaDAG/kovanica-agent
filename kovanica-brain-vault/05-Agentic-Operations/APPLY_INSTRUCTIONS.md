# Applying this update to kovanica-agent

## What changed
- `kovanica-blockchain-developer-references/` — 18 reference docs (RFCs, tokenomics, GHOSTDAG notes, API, node ops, cheat-sheet, etc.)
- `kovanica-blockchain-developer-skill/` — symlink to the skill dir (`SKILL.md` + `references/` + `scripts/`)
- Agent wire-up: `agent/indexer.py` gains `--skill-docs`, `agent/rag.py` gains `search_kovanica_docs`, `agent/graph.py` registers it as a tool
- `README.md` and `SYSTEM_PROMPT.md` updated to mention the skill

## How to index
```bash
docker exec kovanica-agent-agent-api-1 python /app/indexer.py \
  --skill-docs /skills/kovanica-blockchain-developer/references \
  --skill-docs-collection kovanica_skill_docs
```
After that, `search_kovanica_docs` and `explain_concept` can cite `[skill_doc:...]` hits.
