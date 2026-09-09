"""
Indexing pipeline: walk a repo, Rust-aware chunk, embed, upsert to Qdrant.

Usage:
    python -m indexer --repo /root/kovanica-protocol [--collection kovanica_codebase] [--recreate]
"""

import argparse
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from embed import get_embedder  # noqa: F401  (re-exported for the CLI below)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
DEFAULT_COLLECTION = "kovanica_codebase"
VECTOR_SIZE = 384  # BAAI/bge-small-en-v1.5

# Rust-aware chunking: split on these top-level item introducers.
_RUST_ITEM_RE = re.compile(
    r"^\s*(?:pub\s+)?(?:pub\(\w+\)\s+)?"
    r"(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?"
    r"(?:extern\s+(?:\"[^\"]*\"\s+)?)?"
    r"(?:fn|impl|struct|enum|trait|mod)\s"
)

# Generic chunking: split on markdown headers or blank lines.
_HEADER_RE = re.compile(r"^#{1,3}\s")

# Indexable file extensions (lowercase, with leading dot).
_INDEXABLE_EXTENSIONS = {
    ".rs", ".md", ".toml", ".ts", ".tsx", ".js", ".jsx",
    ".py", ".yaml", ".yml", ".json", ".txt", ".cfg", ".ini",
    ".sh", ".dockerfile", ".lock",
}

# Directories to skip when walking.
_SKIP_DIRS = {
    "target", "node_modules", ".git", "__pycache__", ".venv",
    "dist", "build", ".mypy_cache", ".pytest_cache",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A single indexable chunk of source code or documentation."""

    text: str
    file_path: str       # absolute
    rel_path: str        # relative to repo root
    lang: str            # file extension (e.g. ".rs", ".md")
    start_line: int      # 1-indexed inclusive
    end_line: int        # 1-indexed inclusive
    chunk_id: str = field(default="")  # uuid5(rel_path:start:end) hex

    def __post_init__(self):
        if not self.chunk_id:
            raw = f"{self.rel_path}:{self.start_line}:{self.end_line}"
            # Qdrant point ids must be an unsigned integer or a UUID string.
            # Derive a deterministic UUID from the chunk locator.
            self.chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


# ---------------------------------------------------------------------------
# Rust-aware chunking
# ---------------------------------------------------------------------------

_ITEM_RE = re.compile(
    r"^\s*(pub(\s*\([^)]*\))?\s+)?"
    r"(async\s+|unsafe\s+|extern\s+(\"[^\"]*\"\s+)?|const\s+)*"
    r"(fn|struct|enum|trait|mod|impl|union)\b"
)


def _strip_line_for_brace_scan(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Return a copy of ``line`` with string/char literals and comments
    blanked out (so their braces can't be mistaken for structural ones),
    plus whether a ``/* ... */`` block comment is still open afterwards.
    """
    out = []
    i = 0
    n = len(line)
    in_str = False
    in_char = False
    while i < n:
        c = line[i]
        if in_block_comment:
            if c == "*" and i + 1 < n and line[i + 1] == "/":
                in_block_comment = False
                out.append("  ")
                i += 2
                continue
            out.append(" ")
            i += 1
            continue
        if in_str:
            out.append(" ")
            if c == "\\" and i + 1 < n:
                out.append(" ")
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if in_char:
            out.append(" ")
            if c == "\\" and i + 1 < n:
                out.append(" ")
                i += 2
                continue
            if c == "'":
                in_char = False
            i += 1
            continue
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break  # rest of line is a line comment
        if c == "/" and i + 1 < n and line[i + 1] == "*":
            in_block_comment = True
            out.append("  ")
            i += 2
            continue
        if c == '"':
            in_str = True
            out.append(" ")
            i += 1
            continue
        if c == "'":
            # Could be a char literal ('a', '\n') or a lifetime ('static).
            # Heuristic: char literals close within 4 chars via an
            # unescaped closing quote; lifetimes don't. Treat as char
            # literal only when we can see the closing quote nearby.
            closing = line.find("'", i + 1, i + 5)
            if closing != -1:
                in_char = True
                out.append(" ")
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out), in_block_comment


def chunk_rust(content: str, rel_path: str, abs_path: str) -> list[Chunk]:
    """Split a .rs file on top-level fn/impl/struct/enum/trait/mod/union items.

    Tracks brace depth (ignoring braces inside string/char literals and
    comments) so nested blocks -- match arms, closures, if/else, loops --
    never trigger a premature split. A chunk ends only when depth returns
    to 0 after having gone positive, i.e. at the item's *own* closing
    brace, not the first bare ``}`` anywhere inside it.

    Each chunk includes any immediately preceding doc-comment (``///``,
    ``//!``) or attribute (``#[...]``) lines that belong to the item.
    """
    lines = content.split("\n")
    total = len(lines)
    chunks: list[Chunk] = []

    start_line = 0  # 0-indexed line where the current item (+ its leading
                     # doc-comments/attributes) starts
    item_start = None  # 0-indexed line of the item's own signature, once found
    depth = 0
    in_block_comment = False
    seen_open_brace = False

    def flush(end_i: int) -> None:
        nonlocal start_line
        text = "\n".join(lines[start_line:end_i + 1]).strip()
        if text:
            chunks.append(Chunk(
                text=text,
                file_path=abs_path,
                rel_path=rel_path,
                lang=".rs",
                start_line=start_line + 1,
                end_line=end_i + 1,
            ))
        next_start = end_i + 1
        while next_start < total and lines[next_start].strip() == "":
            next_start += 1
        start_line = next_start

    i = 0
    while i < total:
        raw = lines[i]
        scan_line, in_block_comment = _strip_line_for_brace_scan(raw, in_block_comment)
        stripped = raw.strip()

        if item_start is None:
            if stripped.startswith("///") or stripped.startswith("//!") or stripped.startswith("#["):
                i += 1
                continue
            if stripped == "":
                # Blank line before any item content -- part of the gap
                # between items, drop it from the pending chunk start.
                if start_line == i:
                    start_line = i + 1
                i += 1
                continue
            # Any other top-level content (item keyword, `use`, `static`,
            # `type X = ...;`, macro invocation) becomes the item anchor.
            item_start = i
            depth = 0
            seen_open_brace = False

        depth += scan_line.count("{")
        if "{" in scan_line:
            seen_open_brace = True
        depth -= scan_line.count("}")

        # Brace-less item (e.g. `use foo::bar;`, `type X = Y;`) ends at the
        # first line containing a statement-terminating `;` with no brace
        # ever opened.
        if not seen_open_brace and ";" in scan_line:
            flush(i)
            item_start = None
            i += 1
            continue

        if seen_open_brace and depth <= 0:
            flush(i)
            item_start = None
            i += 1
            continue

        i += 1

    # Handle any trailing, unterminated content (e.g. a file that ends
    # mid-item, or trailing comments with no following item).
    if start_line < total:
        tail = "\n".join(lines[start_line:]).strip()
        if tail:
            chunks.append(Chunk(
                text=tail,
                file_path=abs_path,
                rel_path=rel_path,
                lang=".rs",
                start_line=start_line + 1,
                end_line=total,
            ))

    return chunks



# ---------------------------------------------------------------------------
# Generic (non-Rust) chunking
# ---------------------------------------------------------------------------

def _split_generic(content: str) -> list[str]:
    """Split non-Rust text into sections on headers and blank lines."""
    sections: list[str] = []
    current: list[str] = []

    for line in content.split("\n"):
        is_header = bool(_HEADER_RE.match(line))
        is_blank = line.strip() == ""

        if (is_header or is_blank) and current:
            merged = "\n".join(current).strip()
            if merged:
                sections.append(merged)
            current = []

        if not is_blank:
            current.append(line)

    if current:
        merged = "\n".join(current).strip()
        if merged:
            sections.append(merged)

    return sections


def chunk_generic(content: str, rel_path: str, abs_path: str, lang: str) -> list[Chunk]:
    """Chunk non-Rust files by headers/blank-lines, merge to ~1000 chars."""
    sections = _split_generic(content)
    lines = content.split("\n")
    target_chars = 1000

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_chars = 0
    buf_start = 0  # 1-indexed line number of the first line in the buffer

    # Map each section start text to its 0-indexed line offset for
    # accurate line-number tracking.
    section_offsets: list[int] = []
    search_from = 0
    for sec in sections:
        idx = content.find(sec, search_from)
        if idx >= 0:
            section_offsets.append(content[:idx].count("\n"))
        else:
            section_offsets.append(0)
        search_from = idx + len(sec)

    for si, sec in enumerate(sections):
        sec_lines = sec.split("\n")
        sec_len = len(sec)

        if buf_chars + sec_len + (1 if buf else 0) <= target_chars:
            if buf:
                buf.append("")
            buf.extend(sec_lines)
            buf_chars += sec_len + (1 if buf_chars > 0 else 0)
            if not chunks and not buf_start:
                buf_start = section_offsets[si] + 1
        else:
            # Flush current buffer.
            if buf:
                text = "\n".join(buf).strip()
                if text:
                    chunks.append(Chunk(
                        text=text,
                        file_path=abs_path,
                        rel_path=rel_path,
                        lang=lang,
                        start_line=buf_start,
                        end_line=buf_start + len(buf) - 1,
                    ))
            # If the section itself exceeds the target, split on blank lines.
            if sec_len > target_chars:
                sub_buf: list[str] = []
                sub_chars = 0
                sub_start = section_offsets[si] + 1
                for sl in sec_lines:
                    if sub_chars + len(sl) + (1 if sub_buf else 0) > target_chars and sub_buf:
                        text = "\n".join(sub_buf).strip()
                        if text:
                            chunks.append(Chunk(
                                text=text,
                                file_path=abs_path,
                                rel_path=rel_path,
                                lang=lang,
                                start_line=sub_start,
                                end_line=sub_start + len(sub_buf) - 1,
                            ))
                        sub_start += len(sub_buf) + 1  # +1 for skipped blank
                        sub_buf = []
                        sub_chars = 0
                    sub_buf.append(sl)
                    sub_chars += len(sl) + (1 if len(sub_buf) > 1 else 0)
                if sub_buf:
                    text = "\n".join(sub_buf).strip()
                    if text:
                        chunks.append(Chunk(
                            text=text,
                            file_path=abs_path,
                            rel_path=rel_path,
                            lang=lang,
                            start_line=sub_start,
                            end_line=sub_start + len(sub_buf) - 1,
                        ))
                buf = []
                buf_chars = 0
                buf_start = 0
            else:
                buf = list(sec_lines)
                buf_chars = sec_len
                buf_start = section_offsets[si] + 1

    # Flush remaining buffer.
    if buf:
        text = "\n".join(buf).strip()
        if text:
            chunks.append(Chunk(
                text=text,
                file_path=abs_path,
                rel_path=rel_path,
                lang=lang,
                start_line=buf_start,
                end_line=buf_start + len(buf) - 1,
            ))

    return chunks


# ---------------------------------------------------------------------------
# File walking & dispatching
# ---------------------------------------------------------------------------

def is_rust(path: str) -> bool:
    return path.endswith(".rs")


def chunk_file(content: str, rel_path: str, abs_path: str) -> list[Chunk]:
    """Dispatch to the appropriate chunker based on file extension."""
    if is_rust(rel_path):
        return chunk_rust(content, rel_path, abs_path)
    lang = Path(rel_path).suffix or ".txt"
    return chunk_generic(content, rel_path, abs_path, lang)


def walk_repo(repo_root: str) -> list[tuple[str, str]]:
    """Walk repo_root and return (abs_path, rel_path) pairs for indexable files."""
    root = Path(repo_root).resolve()
    files: list[tuple[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place.
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in sorted(filenames):
            ext = Path(fname).suffix.lower()
            if ext not in _INDEXABLE_EXTENSIONS:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root)
            files.append((abs_path, rel_path))

    logger.info("Found %d indexable files in %s", len(files), root)
    return files


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def get_qdrant_client():
    """Create a QdrantClient connected to QDRANT_URL."""
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL)


def recreate_collection(client, collection: str) -> None:
    """Drop (if present) and recreate a Qdrant collection with cosine distance."""
    from qdrant_client.models import Distance, VectorParams
    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    logger.info("Recreated collection '%s' (dim=%d, cosine)", collection, VECTOR_SIZE)


def ensure_collection(client, collection: str) -> None:
    """Create the collection if it doesn't already exist; no-op otherwise.

    Without this, the very first index run (no one has passed --recreate
    yet, because there's nothing to recreate) fails outright: upsert()
    404s against a collection Qdrant has never heard of. --recreate stays
    the explicit "drop and rebuild from scratch" path; this is what makes
    a bare first run (and every incremental webhook-triggered reindex,
    which never passes --recreate) actually work.
    """
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if collection in existing:
        return
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    logger.info("Created collection '%s' (dim=%d, cosine)", collection, VECTOR_SIZE)


def upsert_chunks(client, collection: str, chunks: list[Chunk], embedder) -> None:
    """Embed chunks and upsert them into the Qdrant collection in batches."""
    from qdrant_client.models import PointStruct

    batch_size = 64
    total = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c.text for c in batch]

        try:
            vectors = [v.tolist() for v in embedder.embed(texts)]
        except Exception:
            logger.exception("Embedding failed for batch starting at %d", start)
            continue

        points = []
        for chunk, vector in zip(batch, vectors):
            points.append(PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "text": chunk.text,
                    "rel_path": chunk.rel_path,
                    "lang": chunk.lang,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "abs_path": chunk.file_path,
                },
            ))

        client.upsert(collection_name=collection, points=points)
        total += len(points)
        logger.info("Upserted %d / %d points", total, len(chunks))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: walk a repo, chunk, embed, index into Qdrant."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Index a repo into Qdrant for the Kovanica agent.",
    )
    parser.add_argument(
        "--repo", default="/root/kovanica-protocol",
        help="Path to the repo root (default: /root/kovanica-protocol)",
    )
    parser.add_argument(
        "--collection", default=DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--recreate", action="store_true",
        help="Drop and recreate the collection before indexing",
    )
    args = parser.parse_args()

    client = get_qdrant_client()

    if args.recreate:
        recreate_collection(client, args.collection)
    else:
        ensure_collection(client, args.collection)

    files = walk_repo(args.repo)
    if not files:
        logger.warning("No indexable files found in %s", args.repo)
        return

    embedder = get_embedder()

    all_chunks: list[Chunk] = []
    for abs_path, rel_path in files:
        try:
            with open(abs_path, "r", errors="replace") as f:
                content = f.read()
            chunks = chunk_file(content, rel_path, abs_path)
            all_chunks.extend(chunks)
        except Exception:
            logger.exception("Failed to chunk %s", rel_path)

    logger.info(
        "Chunked %d files into %d chunks", len(files), len(all_chunks),
    )

    if all_chunks:
        upsert_chunks(client, args.collection, all_chunks, embedder)

    logger.info(
        "Done — %d files, %d chunks indexed into '%s'",
        len(files), len(all_chunks), args.collection,
    )


if __name__ == "__main__":
    main()
