"""
Embedding helper backed by fastembed (HuggingFace TextEmbedding).

Default model: BAAI/bge-small-en-v1.5 (384-dim).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_embedder: Optional[object] = None


def get_embedder():
    """Return a cached singleton TextEmbedder instance."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from fastembed import TextEmbedding
    except ImportError:
        raise RuntimeError(
            "fastembed is not installed.  "
            "Install it with: pip install fastembed"
        )
    _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    logger.info("Loaded embedding model BAAI/bge-small-en-v1.5")
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts and return a list of float vectors."""
    embedder = get_embedder()
    return [vec.tolist() for vec in embedder.embed(texts)]


def embed_query(text: str) -> list[float]:
    """Embed a single query string and return a float vector."""
    return embed_texts([text])[0]
