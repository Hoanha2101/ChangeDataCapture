"""
FastAPI Server - CDC + Incremental RAG + Pinecone Integration
REST API để manage full ingestion và incremental updates
"""

import os
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import threading

from ingest_data import DataIngestion
from cdc_kafka_consumer import get_consumer
from incremental_pinecone_updater import IncrementalPineconeUpdater

load_dotenv()

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class HealthResponse(BaseModel):
    status: str
    message: str
    timestamp: str


class IngestionRequest(BaseModel):
    data_folder: str = "./rag"
    force_recreate_index: bool = False


class IngestionResponse(BaseModel):
    status: str
    message: str
    documents_processed: int
    chunks_created: int
    vectors_indexed: int


class CDCEventRequest(BaseModel):
    """Manual CDC event submission (for testing)"""
    op: str  # c, u, d
    before: Optional[Dict] = None
    after: Optional[Dict] = None
    table: str = "stores"


class CDCEventResponse(BaseModel):
    status: str
    operation: str
    vector_ids: List[str]
    message: str


class ConsumerStatusResponse(BaseModel):
    is_running: bool
    topic: str
    uptime_seconds: float
    total_messages: int
    successful_updates: int
    failed_updates: int


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="CDC + Incremental RAG API",
    description="Real-time data ingestion + CDC-driven Pinecone updates",
    version="1.0.0"
)


# Global state
data_ingestion = None
cdc_consumer = None
pinecone_updater = None


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global data_ingestion, cdc_consumer, pinecone_updater
    
    data_ingestion = DataIngestion()
    cdc_consumer = get_consumer()
    
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "store-knowledge")
    pinecone_updater = IncrementalPineconeUpdater(pinecone_api_key, index_name)
    
    print("✅ Application startup completed")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global cdc_consumer
    if cdc_consumer and cdc_consumer.is_running:
        cdc_consumer.stop()
    print("✅ Application shutdown completed")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    from datetime import datetime
    
    return HealthResponse(
        status="healthy",
        message="CDC + RAG API is running",
        timestamp=datetime.now().isoformat()
    )


# =============================================================================
# FULL DATA INGESTION ENDPOINTS
# =============================================================================

@app.post("/api/v1/ingest/full", response_model=IngestionResponse)
async def full_ingestion(
    request: IngestionRequest,
    background_tasks: BackgroundTasks
):
    """
    Full data ingestion - chunk và embed toàn bộ data từ folder
    
    Use case: Lần đầu tiên setup hoặc sau schema changes
    """
    
    try:
        # Run ingestion in background
        background_tasks.add_task(
            _run_full_ingestion,
            request.data_folder,
            request.force_recreate_index
        )
        
        return IngestionResponse(
            status="in_progress",
            message="Full ingestion started in background",
            documents_processed=0,
            chunks_created=0,
            vectors_indexed=0
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_full_ingestion(data_folder: str, force_recreate_index: bool):
    """Background task cho full ingestion"""
    
    global data_ingestion
    
    try:
        if force_recreate_index:
            data_ingestion.create_index_if_not_exists()
        
        documents = data_ingestion.load_documents_from_folder(data_folder)
        
        if not documents:
            print("❌ No documents found")
            return
        
        splits = data_ingestion.split_documents(documents)
        data_ingestion.ingest_to_pinecone(splits)
        
        print(f"✅ Full ingestion completed: {len(splits)} chunks indexed")
    
    except Exception as e:
        print(f"❌ Full ingestion error: {e}")


@app.get("/api/v1/ingest/status")
async def ingestion_status():
    """Get current ingestion status"""
    
    return {
        "status": "ready",
        "last_ingestion": "N/A",
        "message": "Ready for full ingestion or CDC events"
    }


# =============================================================================
# CDC CONSUMER ENDPOINTS
# =============================================================================

@app.post("/api/v1/cdc/start")
async def start_cdc_consumer():
    """Bắt đầu lắng nghe CDC events từ Kafka"""
    
    global cdc_consumer
    
    result = cdc_consumer.start()
    
    return JSONResponse(
        status_code=200,
        content=result
    )


@app.post("/api/v1/cdc/stop")
async def stop_cdc_consumer():
    """Dừng CDC consumer"""
    
    global cdc_consumer
    
    result = cdc_consumer.stop()
    
    return JSONResponse(
        status_code=200,
        content=result
    )


@app.get("/api/v1/cdc/status")
async def cdc_consumer_status() -> Dict:
    """Lấy status của CDC consumer"""
    
    global cdc_consumer
    
    status = cdc_consumer.get_status()
    
    return {
        "is_running": status["is_running"],
        "topic": status["topic"],
        "uptime_seconds": status["uptime_seconds"],
        "stats": {
            "total_messages": status["stats"]["total_messages"],
            "successful_updates": status["stats"]["successful_updates"],
            "failed_updates": status["stats"]["failed_updates"],
            "skipped_updates": status["stats"]["skipped_updates"]
        },
        "pinecone_stats": status["pinecone_stats"]
    }


# =============================================================================
# MANUAL CDC EVENT SUBMISSION (for testing)
# =============================================================================

@app.post("/api/v1/cdc/event", response_model=CDCEventResponse)
async def submit_cdc_event(event: CDCEventRequest) -> CDCEventResponse:
    """
    Manually submit a CDC event (for testing/demo)
    
    Example:
    {
        "op": "u",
        "before": {"id": 1, "phone": "0909 456 123"},
        "after": {"id": 1, "phone": "0909 777 888"},
        "table": "stores"
    }
    """
    
    global pinecone_updater
    
    try:
        # Format event
        cdc_event = {
            "op": event.op,
            "before": event.before or {},
            "after": event.after or {},
            "source": {"table": event.table, "db": "rag_db"}
        }
        
        # Process through updater
        result = pinecone_updater.process_cdc_event(cdc_event)
        
        return CDCEventResponse(
            status=result["status"],
            operation=result["operation"],
            vector_ids=result["vector_ids"],
            message=result["message"]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MANUAL UPDATE ENDPOINTS
# =============================================================================

@app.post("/api/v1/update/single")
async def update_single_vector(
    content: str,
    record_id: str = "unknown",
    source: str = "stores"
):
    """Manually update/insert một vector"""
    
    global pinecone_updater
    
    try:
        metadata = {
            "source": source,
            "record_id": record_id,
            "operation": "manual_update"
        }
        
        vector_id = pinecone_updater.update_single_chunk(content, metadata)
        
        return {
            "status": "success",
            "vector_id": vector_id,
            "message": f"Vector updated/created: {vector_id}"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/update/batch")
async def batch_update_vectors(chunks: List[Dict]):
    """Manually batch update/insert vectors"""
    
    global pinecone_updater
    
    try:
        vector_ids = pinecone_updater.batch_update_chunks(chunks)
        
        return {
            "status": "success",
            "vector_ids": vector_ids,
            "message": f"Batch updated: {len(vector_ids)} vectors"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/update/vector/{vector_id}")
async def delete_vector(vector_id: str):
    """Xóa một vector khỏi Pinecone"""
    
    global pinecone_updater
    
    try:
        pinecone_updater.delete_chunk(vector_id)
        
        return {
            "status": "success",
            "vector_id": vector_id,
            "message": f"Vector deleted: {vector_id}"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATS & MONITORING
# =============================================================================

@app.get("/api/v1/stats")
async def get_stats() -> Dict:
    """Lấy thống kê tổng hợp"""
    
    global cdc_consumer, pinecone_updater
    
    cdc_status = cdc_consumer.get_status() if cdc_consumer else {}
    pinecone_stats = pinecone_updater.get_update_stats() if pinecone_updater else {}
    
    return {
        "cdc_consumer": {
            "is_running": cdc_status.get("is_running", False),
            "stats": cdc_status.get("stats", {})
        },
        "pinecone": pinecone_stats,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }


@app.post("/api/v1/stats/reset")
async def reset_stats():
    """Reset tất cả statistics"""
    
    global cdc_consumer
    
    result = cdc_consumer.reset_stats() if cdc_consumer else {"status": "no_consumer"}
    
    return result


# =============================================================================
# ROOT ENDPOINT
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    
    return {
        "name": "CDC + Incremental RAG API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health": "/health",
        "endpoints": {
            "ingestion": "/api/v1/ingest/full",
            "cdc_start": "/api/v1/cdc/start",
            "cdc_stop": "/api/v1/cdc/stop",
            "cdc_status": "/api/v1/cdc/status",
            "manual_event": "/api/v1/cdc/event",
            "stats": "/api/v1/stats"
        }
    }


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": str(exc),
            "type": type(exc).__name__
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("FASTAPI_PORT", 8000))
    
    print(f"""
╔════════════════════════════════════════════════════════════════╗
║         CDC + INCREMENTAL RAG API                             ║
║                                                                ║
║  Starting server on http://localhost:{port}                   ║
║  Swagger UI: http://localhost:{port}/docs                     ║
║  ReDoc: http://localhost:{port}/redoc                         ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "fastapi_server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
