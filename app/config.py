# app/config.py
"""Application configuration"""

from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # App
    APP_NAME: str = "SharePoint RAG Importer"
    DEBUG: bool = False
    
    # Microsoft Azure AD
    MICROSOFT_TENANT_ID: str
    MICROSOFT_CLIENT_ID: str
    MICROSOFT_CLIENT_SECRET: str
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb"
    
    # Vector Store
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "sharepoint_docs"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # OpenAI (Embeddings)
    OPENAI_API_KEY: str
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072
    
    # LLM Provider (anthropic, gemini, vertex, openai)
    LLM_PROVIDER: str = "gemini"  # Default to Gemini

    # Anthropic (Generation)
    ANTHROPIC_API_KEY: Optional[str] = None

    # Google Gemini (AI Studio)
    GEMINI_API_KEY: Optional[str] = None

    # Google Vertex AI (Enterprise)
    VERTEX_PROJECT_ID: Optional[str] = None
    VERTEX_LOCATION: str = "us-central1"

    # LLM Model (auto-detected based on provider if not set)
    LLM_MODEL: str = "gemini-1.5-flash"
    
    # Processing
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    MAX_FILE_SIZE_MB: int = 100
    
    # Supported file types
    SUPPORTED_EXTENSIONS: List[str] = [
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", 
        ".pptx", ".ppt", ".txt", ".csv", ".md", 
        ".html", ".htm", ".json"
    ]
    
    # Security
    SECURITY_KEY: Optional[str] = None

    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Allow extra env vars without validation error


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
