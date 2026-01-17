# app/storage/metadata_store.py
"""PostgreSQL metadata storage - Re-export from vector_store"""

# The MetadataStore class is defined in vector_store.py
# This file exists for proper module structure

from app.storage.vector_store import MetadataStore

__all__ = ['MetadataStore']
