# app/main.py
"""FastAPI Application - SharePoint RAG Importer"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from app.config import settings
from app.api import connections, import_routes, query
from app.storage.vector_store import VectorStore
from app.storage.metadata_store import MetadataStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    logger.info("Starting SharePoint RAG Importer...")

    # Validate required security settings at startup
    if not settings.SECURITY_KEY:
        raise RuntimeError(
            "SECURITY_KEY is required. Generate with: openssl rand -base64 32"
        )

    # Initialize stores
    app.state.vector_store = VectorStore()
    app.state.metadata_store = MetadataStore()
    
    # Connect to services
    await app.state.vector_store.connect()
    await app.state.metadata_store.connect()
    
    # Ensure collection exists
    await app.state.vector_store.ensure_collection()
    
    logger.info("✅ All services connected")
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down...")
    await app.state.metadata_store.disconnect()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    ## SharePoint RAG Importer
    
    Import files from SharePoint/OneDrive folders recursively into a Vector Database
    for RAG (Retrieval-Augmented Generation) queries.
    
    ### Features
    - 📁 Recursive folder import
    - 📄 Multiple file types (PDF, DOCX, XLSX, PPTX, etc.)
    - 🔍 Hybrid search (Vector + Keyword)
    - 🤖 AI-powered answers with citations
    - 🔄 Incremental sync
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS - Get allowed origins from environment or use defaults
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Include routers
app.include_router(connections.router, prefix="/api/connections", tags=["Connections"])
app.include_router(import_routes.router, prefix="/api/import", tags=["Import"])
app.include_router(query.router, prefix="/api/query", tags=["Query"])

# Import webhook router
try:
    from app.api import webhooks
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
except ImportError:
    logger.warning("Webhooks module not available")

# Import auth router
try:
    from app.api import auth
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
except ImportError:
    logger.warning("Auth module not available")

# Import notifications router
try:
    from app.api import notifications
    app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
except ImportError:
    logger.warning("Notifications module not available")

# Serve static frontend
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    
    @app.get("/dashboard")
    async def dashboard():
        """Serve admin dashboard"""
        return FileResponse(os.path.join(frontend_path, "index.html"))


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - API info"""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        # Check vector store
        vector_ok = await app.state.vector_store.health_check()
        
        # Check metadata store
        metadata_ok = await app.state.metadata_store.health_check()
        
        return {
            "status": "healthy" if (vector_ok and metadata_ok) else "degraded",
            "services": {
                "vector_store": "ok" if vector_ok else "error",
                "metadata_store": "ok" if metadata_ok else "error"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return {
        "error": "Internal server error",
        "detail": str(exc) if settings.DEBUG else "An unexpected error occurred"
    }
