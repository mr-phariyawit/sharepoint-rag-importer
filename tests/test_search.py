"""Tests for Phase 3: Search & Intelligence"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import pytest


class TestSearchFilters(unittest.IsolatedAsyncioTestCase):
    """Test search filtering functionality"""
    
    async def test_file_type_filter(self):
        """Test that file_types filter is built correctly"""
        from app.api.query import SearchFilters, SearchRequest, SearchMode
        
        filters = SearchFilters(file_types=["pdf", "docx"])
        request = SearchRequest(
            query="test query",
            mode=SearchMode.SEMANTIC,
            filters=filters
        )
        
        assert request.filters.file_types == ["pdf", "docx"]
        assert request.mode == SearchMode.SEMANTIC
    
    async def test_folder_path_filter(self):
        """Test that folder_path filter is built correctly"""
        from app.api.query import SearchFilters, SearchRequest
        
        filters = SearchFilters(folder_path="/Documents/Reports")
        request = SearchRequest(
            query="sales report",
            filters=filters
        )
        
        assert request.filters.folder_path == "/Documents/Reports"


class TestSearchModes(unittest.IsolatedAsyncioTestCase):
    """Test search mode enum"""
    
    async def test_search_modes_exist(self):
        """Test all search modes are defined"""
        from app.api.query import SearchMode
        
        assert SearchMode.SEMANTIC.value == "semantic"
        assert SearchMode.KEYWORD.value == "keyword"
        assert SearchMode.HYBRID.value == "hybrid"


class TestVectorStoreFilters(unittest.IsolatedAsyncioTestCase):
    """Test vector store with filters"""
    
    async def test_search_with_file_type_filter(self):
        """Test that VectorStore.search accepts filters dict"""
        try:
            from app.storage.vector_store import VectorStore
        except ImportError:
            self.skipTest("VectorStore could not be imported")
        
        store = VectorStore()
        store._client = AsyncMock()
        store._client.search = AsyncMock(return_value=[])
        
        # Mock embedding - 1536 dimensions for OpenAI ada-002
        fake_embedding = [0.1] * 1536
        
        filters_dict = {
            "file_types": ["pdf"],
            "folder_path": "/Reports"
        }
        
        await store.search(
            query_embedding=fake_embedding,
            top_k=10,
            filters=filters_dict
        )
        
        # Verify search was called
        store._client.search.assert_called_once()


if __name__ == '__main__':
    unittest.main()
