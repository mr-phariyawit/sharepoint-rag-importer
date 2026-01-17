
import asyncio
import logging
import os
import signal
import sys

# Add /app to python path to ensure we can import app modules
sys.path.append("/app")

from app.api.import_routes import run_import_job
from app.storage.metadata_store import MetadataStore
from app.storage.vector_store import VectorStore
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for shutdown
SHUTDOWN = False

def handle_sigterm(signum, frame):
    """Handle Docker shutdown signal"""
    global SHUTDOWN
    logger.info("Received termination signal, shutting down...")
    SHUTDOWN = True

async def worker_loop():
    """Main worker loop"""
    logger.info("🚀 Starting Import Worker...")
    
    # Initialize stores
    metadata_store = MetadataStore()
    vector_store = VectorStore()
    
    await metadata_store.connect()
    # Vector store doesn't strictly need connect() as it uses http client per request/init
    # but let's check explicit connect method in VectorStore class
    await vector_store.connect()
    
    logger.info("✅ Services connected. Waiting for jobs...")
    
    while not SHUTDOWN:
        try:
            # Poll for pending jobs
            # We use list_import_jobs with status='pending'
            jobs = await metadata_store.list_import_jobs(status="pending", limit=1)
            
            if not jobs:
                # Sleep and wait
                await asyncio.sleep(5)
                continue
                
            job_summary = jobs[0]
            job_id = str(job_summary["id"])
            logger.info(f"📋 Found pending job: {job_id}")
            
            # Fetch full job details
            job = await metadata_store.get_import_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found after listing")
                continue
                
            # Fetch connection details
            connection_id = str(job["connection_id"])
            connection = await metadata_store.get_connection(connection_id)
            if not connection:
                logger.error(f"Connection {connection_id} not found for job {job_id}")
                await metadata_store.update_import_job_progress(
                    job_id=job_id,
                    status="failed",
                    error_log=[{"error": "Connection not found"}]
                )
                continue
                
            # Run the job
            # connection dict already has client_secret_encrypted
            
            logger.info(f"▶️ Processing job {job_id} for {job['folder_url']}")
            
            try:
                await run_import_job(
                    job_id=job_id,
                    connection=connection,
                    folder_url=job["folder_url"],
                    recursive=job["recursive"],
                    metadata_store=metadata_store,
                    vector_store=vector_store
                )
                logger.info(f"✅ Job {job_id} processing finished")
            except Exception as e:
                logger.error(f"❌ Job {job_id} failed with exception: {e}")
                # run_import_job handles its own status updates usually, 
                # but we catch here just in case wrapper fails
                
        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            await asyncio.sleep(5)
            
    # Cleanup
    logger.info("🛑 Worker shutting down...")
    await metadata_store.disconnect()

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    asyncio.run(worker_loop())
