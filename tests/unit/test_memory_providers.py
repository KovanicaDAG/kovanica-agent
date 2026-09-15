"""
Unit tests for Memory Providers.
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/root/kovanica-agent')

from agent.memory_providers import (
    MemoryProvider, LocalMemoryProvider, SQLiteMemoryProvider,
    VectorMemoryProvider, ByteRoverProvider, SupermemoryProvider,
    MemoryItem, get_provider, get_available_providers, initialize_providers
)


class TestMemoryItem:
    """Tests for MemoryItem dataclass."""
    
    def test_creation(self):
        item = MemoryItem(
            id="mem123",
            type="fact",
            content="User prefers dark mode",
            session_id="sess123",
            timestamp="2024-01-01T00:00:00",
            provider="local",
            metadata={"source": "chat"},
            approved_at="2024-01-01T01:00:00",
            embedding=[0.1, 0.2, 0.3]
        )
        
        assert item.id == "mem123"
        assert item.type == "fact"
        assert item.content == "User prefers dark mode"
        assert item.session_id == "sess123"
        assert item.provider == "local"
        assert item.metadata == {"source": "chat"}
        assert item.approved_at == "2024-01-01T01:00:00"
        assert item.embedding == [0.1, 0.2, 0.3]
    
    def test_to_dict(self):
        item = MemoryItem(
            id="mem123",
            type="fact",
            content="Test content",
            session_id="sess123",
            timestamp="2024-01-01T00:00:00"
        )
        
        d = item.to_dict()
        assert d["id"] == "mem123"
        assert d["type"] == "fact"
        assert d["content"] == "Test content"
    
    def test_from_dict(self):
        data = {
            "id": "mem123",
            "type": "fact",
            "content": "Test content",
            "session_id": "sess123",
            "timestamp": "2024-01-01T00:00:00",
            "provider": "local",
            "metadata": {"source": "chat"},
            "approved_at": "2024-01-01T01:00:00",
            "embedding": [0.1, 0.2]
        }
        
        item = MemoryItem.from_dict(data)
        assert item.id == "mem123"
        assert item.metadata == {"source": "chat"}
        assert item.embedding == [0.1, 0.2]


class TestLocalMemoryProvider:
    """Tests for LocalMemoryProvider."""
    
    @pytest.fixture
    def provider(self, tmp_path):
        provider = LocalMemoryProvider()
        provider.initialize({
            "memory_dir": str(tmp_path / "memory"),
            "memory_approval": True
        })
        return provider
    
    def test_is_available(self, provider):
        assert provider.is_available() is True
    
    def test_initialize(self, provider, tmp_path):
        assert provider.memory_dir.exists()
        assert provider.pending_file.exists()
        assert provider.approved_file.exists()
        assert provider.approval_mode is True
    
    def test_sync_turn_placeholder(self, provider):
        """Test sync_turn returns empty list (placeholder implementation)."""
        items = provider.sync_turn("user message", "assistant reply", "session123")
        assert items == []
    
    def test_prefetch_local(self, provider):
        """Test prefetching from local storage."""
        # Add some approved items
        approved = [
            {"id": "1", "type": "fact", "content": "User likes Python", "session_id": "sess1", "timestamp": "2024-01-01T00:00:00", "provider": "local"},
            {"id": "2", "type": "preference", "content": "User prefers dark mode", "session_id": "sess1", "timestamp": "2024-01-01T01:00:00", "provider": "local"},
            {"id": "3", "type": "fact", "content": "User knows Rust", "session_id": "sess2", "timestamp": "2024-01-01T02:00:00", "provider": "local"},
        ]
        provider._save_jsonl(provider.approved_file, approved)
        
        # Search for Python
        results = provider.prefetch("Python", session_id="sess1", limit=10)
        assert len(results) == 1
        assert results[0].content == "User likes Python"
        
        # Search for dark mode
        results = provider.prefetch("dark mode", limit=10)
        assert len(results) == 1
        assert results[0].content == "User prefers dark mode"
    
    def test_store_approved(self, provider):
        """Test storing approved memory items."""
        items = [
            MemoryItem(id="1", type="fact", content="Test fact", session_id="sess1", timestamp="2024-01-01T00:00:00"),
            MemoryItem(id="2", type="preference", content="Test preference", session_id="sess1", timestamp="2024-01-01T01:00:00"),
        ]
        
        result = provider.store(items)
        assert result is True
        
        # Verify stored
        approved = provider._load_jsonl(provider.approved_file)
        assert len(approved) == 2
    
    def test_health_check(self, provider):
        health = provider.health_check()
        assert health["provider"] == "local"
        assert health["status"] == "healthy"
        assert "pending_count" in health
        assert "approved_count" in health
    
    def test_get_tool_schemas(self, provider):
        schemas = provider.get_tool_schemas()
        assert schemas == []


class TestSQLiteMemoryProvider:
    """Tests for SQLiteMemoryProvider."""
    
    @pytest.fixture
    def provider(self, tmp_path):
        provider = SQLiteMemoryProvider()
        provider.initialize({"sqlite_path": str(tmp_path / "memory.db")})
        return provider
    
    def test_is_available(self, provider):
        assert provider.is_available() is True
    
    def test_initialize(self, provider, tmp_path):
        assert provider.db_path.exists()
        assert provider.conn is not None
    
    def test_store_and_prefetch(self, provider):
        """Test storing and retrieving items."""
        items = [
            MemoryItem(id="1", type="fact", content="User likes Python", session_id="sess1", timestamp="2024-01-01T00:00:00"),
            MemoryItem(id="2", type="fact", content="User knows Rust", session_id="sess1", timestamp="2024-01-01T01:00:00"),
            MemoryItem(id="3", type="preference", content="User prefers dark mode", session_id="sess2", timestamp="2024-01-01T02:00:00"),
        ]
        
        # Store items
        result = provider.store(items)
        assert result is True
        
        # Prefetch
        results = provider.prefetch("Python", session_id="sess1", limit=10)
        assert len(results) == 1
        assert results[0].content == "User likes Python"
        
        # Search without session filter
        results = provider.prefetch("dark mode", limit=10)
        assert len(results) == 1
        assert results[0].content == "User prefers dark mode"
    
    def test_health_check(self, provider):
        health = provider.health_check()
        assert health["provider"] == "sqlite"
        assert health["status"] == "healthy"
        assert "item_count" in health
        assert "db_path" in health


class TestVectorMemoryProvider:
    """Tests for VectorMemoryProvider (mocked)."""
    
    def test_is_available_without_chromadb(self):
        """Test availability when chromadb not installed."""
        provider = VectorMemoryProvider()
        # Should be False since chromadb not installed in test env
        assert provider.is_available() is False
    
    def test_initialize_without_chromadb(self):
        provider = VectorMemoryProvider()
        result = provider.initialize({"chroma_path": "/tmp/chroma"})
        assert result is False


class TestByteRoverProvider:
    """Tests for ByteRoverProvider."""
    
    def test_is_available_without_api_key(self):
        provider = ByteRoverProvider()
        assert provider.is_available() is False
    
    def test_initialize_without_api_key(self):
        provider = ByteRoverProvider()
        result = provider.initialize({})
        assert result is False
    
    def test_initialize_with_api_key(self):
        provider = ByteRoverProvider()
        result = provider.initialize({"api_key": "test-key"})
        assert result is True
        assert provider.api_key == "test-key"


class TestSupermemoryProvider:
    """Tests for SupermemoryProvider."""
    
    def test_is_available_without_api_key(self):
        provider = SupermemoryProvider()
        assert provider.is_available() is False
    
    def test_initialize_without_api_key(self):
        provider = SupermemoryProvider()
        result = provider.initialize({})
        assert result is False
    
    def test_initialize_with_api_key(self):
        provider = SupermemoryProvider()
        result = provider.initialize({"api_key": "test-key"})
        assert result is True
        assert provider.api_key == "test-key"


class TestProviderRegistry:
    """Tests for provider registry functions."""
    
    def test_get_provider(self):
        provider = get_provider("local")
        assert provider is not None
        assert provider.name == "local"
        
        provider = get_provider("sqlite")
        assert provider is not None
        assert provider.name == "sqlite"
        
        provider = get_provider("nonexistent")
        assert provider is None
    
    def test_get_available_providers(self):
        providers = get_available_providers()
        
        assert len(providers) == 5
        names = {p["name"] for p in providers}
        assert names == {"local", "sqlite", "vector", "byterover", "supermemory"}
        
        for p in providers:
            assert "name" in p
            assert "description" in p
            assert "available" in p
            assert "configured" in p
    
    def test_initialize_providers(self):
        config = {
            "local": {"memory_dir": "/tmp/memory", "memory_approval": True},
            "sqlite": {"sqlite_path": "/tmp/memory.db"},
        }
        
        providers = initialize_providers(config)
        
        assert "local" in providers
        assert "sqlite" in providers
        assert providers["local"].is_available() is True
        assert providers["sqlite"].is_available() is True


class TestMemoryProviderInterface:
    """Tests for MemoryProvider abstract interface."""
    
    def test_abstract_methods(self):
        """Verify all abstract methods are defined."""
        # Check all abstract methods exist
        assert hasattr(MemoryProvider, 'is_available')
        assert hasattr(MemoryProvider, 'initialize')
        assert hasattr(MemoryProvider, 'sync_turn')
        assert hasattr(MemoryProvider, 'prefetch')
        assert MemoryProvider.store.__isabstractmethod__
        assert MemoryProvider.get_tool_schemas.__isabstractmethod__
        assert MemoryProvider.health_check.__isabstractmethod__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])