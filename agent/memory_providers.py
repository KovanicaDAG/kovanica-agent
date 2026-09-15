"""
Memory Provider Interface and Implementations for Kovanica CLI.

Provides pluggable memory backends for persistent, cross-session memory.
"""
from __future__ import annotations

import abc
import json
import sqlite3
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, asdict


@dataclass
class MemoryItem:
    """A single memory item."""
    id: str
    type: str  # fact, preference, pattern, skill, etc.
    content: str
    session_id: str
    timestamp: str
    provider: str = "local"
    metadata: Optional[Dict[str, Any]] = None
    approved_at: Optional[str] = None
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(**data)


class MemoryProvider(abc.ABC):
    """Abstract base class for memory providers."""
    
    name: str = "base"
    description: str = "Base memory provider"
    
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available (dependencies installed, configured)."""
        pass
    
    @abc.abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize provider with configuration. Returns True on success."""
        pass
    
    @abc.abstractmethod
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        """Process a conversation turn and extract memory items.
        
        Returns list of extracted memory items (pending approval).
        """
        pass
    
    @abc.abstractmethod
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        """Retrieve relevant memory items for a query."""
        pass
    
    @abc.abstractmethod
    def store(self, items: List[MemoryItem]) -> bool:
        """Store approved memory items."""
        pass
    
    @abc.abstractmethod
    def get_tool_schemas(self) -> List[Dict]:
        """Return tool schemas for this provider (if any)."""
        pass
    
    @abc.abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return health status of provider."""
        pass


class LocalMemoryProvider(MemoryProvider):
    """Local JSONL file-based memory provider."""
    
    name = "local"
    description = "Local JSONL storage"
    
    def __init__(self):
        self.memory_dir: Optional[Path] = None
        self.pending_file: Optional[Path] = None
        self.approved_file: Optional[Path] = None
        self.approval_mode: bool = True
    
    def is_available(self) -> bool:
        return True
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.memory_dir = Path(config.get("memory_dir", Path.home() / ".kovanica" / "memory"))
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.pending_file = self.memory_dir / "pending.jsonl"
        self.approved_file = self.memory_dir / "approved.jsonl"
        # Create empty files if they don't exist
        self.pending_file.touch(exist_ok=True)
        self.approved_file.touch(exist_ok=True)
        self.approval_mode = config.get("memory_approval", True)
        return True
    
    def _load_jsonl(self, file: Path) -> List[Dict]:
        items = []
        if file.exists():
            with open(file) as f:
                for line in f:
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        pass
        return items
    
    def _save_jsonl(self, file: Path, items: List[Dict]) -> None:
        with open(file, "w") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        """Extract memory items from conversation turn (placeholder - would use LLM)."""
        # In a real implementation, this would use an LLM to extract facts/preferences
        # For now, return empty list
        return []
    
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        """Search approved memory for relevant items."""
        approved = self._load_jsonl(self.approved_file)
        items = []
        query_lower = query.lower()
        
        for item in approved:
            if query_lower in item.get("content", "").lower():
                items.append(MemoryItem.from_dict(item))
                if len(items) >= limit:
                    break
        
        return items
    
    def store(self, items: List[MemoryItem]) -> bool:
        """Store approved memory items."""
        approved = self._load_jsonl(self.approved_file)
        for item in items:
            approved.append(item.to_dict())
        self._save_jsonl(self.approved_file, approved)
        return True
    
    def get_tool_schemas(self) -> List[Dict]:
        return []
    
    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "healthy",
            "pending_count": len(self._load_jsonl(self.pending_file)),
            "approved_count": len(self._load_jsonl(self.approved_file)),
        }


class SQLiteMemoryProvider(MemoryProvider):
    """SQLite-backed memory provider with FTS5 full-text search."""
    
    name = "sqlite"
    description = "SQLite-backed memory with FTS5"
    
    def __init__(self):
        self.db_path: Optional[Path] = None
        self.conn: Optional[sqlite3.Connection] = None
    
    def is_available(self) -> bool:
        return True  # sqlite3 is in stdlib
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.db_path = Path(config.get("sqlite_path", Path.home() / ".kovanica" / "memory" / "memory.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_tables()
            return True
        except Exception as e:
            print(f"SQLite provider init failed: {e}")
            return False
    
    def _create_tables(self) -> None:
        assert self.conn is not None
        cursor = self.conn.cursor()
        
        # Main memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                provider TEXT DEFAULT 'sqlite',
                metadata TEXT,
                approved_at TEXT,
                embedding BLOB
            )
        """)
        
        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id UNINDEXED,
                type UNINDEXED,
                content,
                session_id UNINDEXED,
                timestamp UNINDEXED,
                provider UNINDEXED,
                metadata UNINDEXED,
                content='memory_items',
                content_rowid='rowid'
            )
        """)
        
        # Triggers to keep FTS in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_items BEGIN
                INSERT INTO memory_fts (rowid, id, type, content, session_id, timestamp, provider, metadata)
                VALUES (new.rowid, new.id, new.type, new.content, new.session_id, new.timestamp, new.provider, new.metadata);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_items BEGIN
                INSERT INTO memory_fts (memory_fts, rowid, id, type, content, session_id, timestamp, provider, metadata)
                VALUES ('delete', old.rowid, old.id, old.type, old.content, old.session_id, old.timestamp, old.provider, old.metadata);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_items BEGIN
                INSERT INTO memory_fts (memory_fts, rowid, id, type, content, session_id, timestamp, provider, metadata)
                VALUES ('delete', old.rowid, old.id, old.type, old.content, old.session_id, old.timestamp, old.provider, old.metadata);
                INSERT INTO memory_fts (rowid, id, type, content, session_id, timestamp, provider, metadata)
                VALUES (new.rowid, new.id, new.type, new.content, new.session_id, new.timestamp, new.provider, new.metadata);
            END
        """)
        
        self.conn.commit()
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        # Placeholder - would use LLM to extract facts
        return []
    
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        assert self.conn is not None
        cursor = self.conn.cursor()
        
        # Use FTS5 for full-text search
        cursor.execute("""
            SELECT m.* FROM memory_items m
            JOIN memory_fts f ON m.rowid = f.rowid
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        
        rows = cursor.fetchall()
        items = []
        for row in rows:
            item = MemoryItem(
                id=row["id"],
                type=row["type"],
                content=row["content"],
                session_id=row["session_id"],
                timestamp=row["timestamp"],
                provider=row["provider"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                approved_at=row["approved_at"],
                embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            )
            items.append(item)
        
        return items
    
    def store(self, items: List[MemoryItem]) -> bool:
        assert self.conn is not None
        cursor = self.conn.cursor()
        
        for item in items:
            cursor.execute("""
                INSERT OR REPLACE INTO memory_items 
                (id, type, content, session_id, timestamp, provider, metadata, approved_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.id,
                item.type,
                item.content,
                item.session_id,
                item.timestamp,
                item.provider,
                json.dumps(item.metadata) if item.metadata else None,
                item.approved_at,
                json.dumps(item.embedding) if item.embedding else None,
            ))
        
        self.conn.commit()
        return True
    
    def get_tool_schemas(self) -> List[Dict]:
        return []
    
    def health_check(self) -> Dict[str, Any]:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memory_items")
        count = cursor.fetchone()[0]
        return {
            "provider": self.name,
            "status": "healthy",
            "item_count": count,
            "db_path": str(self.db_path),
        }


class VectorMemoryProvider(MemoryProvider):
    """Vector database memory provider (Chroma, Pinecone, etc.)."""
    
    name = "vector"
    description = "Vector database (Chroma, Pinecone, etc.)"
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.config: Dict[str, Any] = {}
    
    def is_available(self) -> bool:
        try:
            import chromadb
            return True
        except ImportError:
            return False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.config = config
        try:
            import chromadb
            from chromadb.config import Settings
            
            persist_dir = config.get("chroma_path", Path.home() / ".kovanica" / "memory" / "chroma")
            persist_dir.mkdir(parents=True, exist_ok=True)
            
            self.client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection(
                name="kovanica_memory",
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except Exception as e:
            print(f"Vector provider init failed: {e}")
            return False
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        # Placeholder - would use LLM to extract facts and embed them
        return []
    
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        if not self.collection:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=limit,
                where={"session_id": session_id} if session_id else None
            )
            
            items = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    items.append(MemoryItem(
                        id=results["ids"][0][i],
                        type=meta.get("type", "fact"),
                        content=doc,
                        session_id=meta.get("session_id", session_id or ""),
                        timestamp=meta.get("timestamp", datetime.now().isoformat()),
                        provider="vector",
                        metadata=meta,
                    ))
            return items
        except Exception:
            return []
    
    def store(self, items: List[MemoryItem]) -> bool:
        if not self.collection:
            return False
        
        try:
            ids = [item.id for item in items]
            documents = [item.content for item in items]
            metadatas = [{
                "type": item.type,
                "session_id": item.session_id,
                "timestamp": item.timestamp,
                "provider": item.provider,
                **(item.metadata or {}),
            } for item in items]
            
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            return True
        except Exception:
            return False
    
    def get_tool_schemas(self) -> List[Dict]:
        return []
    
    def health_check(self) -> Dict[str, Any]:
        if not self.collection:
            return {"provider": self.name, "status": "not_initialized"}
        
        try:
            count = self.collection.count()
            return {"provider": self.name, "status": "healthy", "item_count": count}
        except Exception as e:
            return {"provider": self.name, "status": "error", "error": str(e)}


class ByteRoverProvider(MemoryProvider):
    """ByteRover hierarchical knowledge provider."""
    
    name = "byterover"
    description = "ByteRover hierarchical knowledge"
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url: str = "https://api.byterover.com"
    
    def is_available(self) -> bool:
        return bool(os.environ.get("BYTEROVER_API_KEY"))
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.api_key = config.get("api_key") or os.environ.get("BYTEROVER_API_KEY")
        self.base_url = config.get("base_url", "https://api.byterover.com")
        return bool(self.api_key)
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        # Would call ByteRover API
        return []
    
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        # Would call ByteRover API
        return []
    
    def store(self, items: List[MemoryItem]) -> bool:
        # Would call ByteRover API
        return True
    
    def get_tool_schemas(self) -> List[Dict]:
        return []
    
    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "configured" if self.api_key else "not_configured",
        }


class SupermemoryProvider(MemoryProvider):
    """Supermemory semantic graph provider."""
    
    name = "supermemory"
    description = "Supermemory semantic graph"
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url: str = "https://api.supermemory.ai"
    
    def is_available(self) -> bool:
        return bool(os.environ.get("SUPERMEMORY_API_KEY"))
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        self.api_key = config.get("api_key") or os.environ.get("SUPERMEMORY_API_KEY")
        self.base_url = config.get("base_url", "https://api.supermemory.ai")
        return bool(self.api_key)
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, metadata: Optional[Dict] = None) -> List[MemoryItem]:
        # Would call Supermemory API
        return []
    
    def prefetch(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[MemoryItem]:
        # Would call Supermemory API
        return []
    
    def store(self, items: List[MemoryItem]) -> bool:
        # Would call Supermemory API
        return True
    
    def get_tool_schemas(self) -> List[Dict]:
        return []
    
    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "configured" if self.api_key else "not_configured",
        }


# Provider registry
PROVIDERS: Dict[str, type] = {
    "local": LocalMemoryProvider,
    "sqlite": SQLiteMemoryProvider,
    "vector": VectorMemoryProvider,
    "byterover": ByteRoverProvider,
    "supermemory": SupermemoryProvider,
}


def get_provider(name: str) -> Optional[MemoryProvider]:
    """Get provider instance by name."""
    provider_class = PROVIDERS.get(name)
    if provider_class:
        return provider_class()
    return None


def get_available_providers() -> List[Dict[str, Any]]:
    """Get list of all providers with availability status."""
    providers = []
    for name, provider_class in PROVIDERS.items():
        provider = provider_class()
        providers.append({
            "name": name,
            "description": provider.description,
            "available": provider.is_available(),
            "configured": False,  # Would check config in real impl
        })
    return providers


def initialize_providers(config: Dict[str, Any]) -> Dict[str, MemoryProvider]:
    """Initialize all configured providers."""
    providers = {}
    for name, provider_class in PROVIDERS.items():
        provider = provider_class()
        if provider.initialize(config.get(name, {})):
            providers[name] = provider
    return providers