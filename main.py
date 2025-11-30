import os
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
from database import DatabaseManager
from langchain_community.embeddings import HuggingFaceEmbeddings
from pinecone import Pinecone


load_dotenv()

# FastAPI app
app = FastAPI(
    title="Change Data Capture API",
    description="API for Change data capture project",
    version="1.0.0",
    # root_path="/api"
)

# CORS - Cho phép gọi từ frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong production, chỉ định domain cụ thể
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pinecone setup
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "store-knowledge")

pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = PINECONE_INDEX_NAME
index_pc = pc.Index(index_name)
print(f"🌲 Pinecone index đã sẵn sàng: {index_name}")

# Initialize embeddings
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
print("🧠 Embeddings model đã sẵn sàng")

# =============================================================================
# MODELS
# =============================================================================

class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    service: str
    checks: Dict[str, Any]


class ConnectionCheckResult(BaseModel):
    name: str
    status: str
    message: str
    error: str = None


class CreateTableRequest(BaseModel):
    table_name: str


class AddDocumentRequest(BaseModel):
    content: str
    metadata: Optional[Dict] = None


class UpdateDocumentRequest(BaseModel):
    content: str
    metadata: Optional[Dict] = None


class ChangeDocumentRequest(BaseModel):
    from_index: int
    to_index: int
    content: str


class UploadDocumentRequest(BaseModel):
    category: Optional[str] = None


class ChunkingRequest(BaseModel):
    all: bool = True
    from_idx: Optional[int] = None
    to_idx: Optional[int] = None


class UpdateRowRequest(BaseModel):
    updates: Dict[str, Any]


# =============================================================================
# CONNECTION CHECK FUNCTIONS
# =============================================================================

def chunk_by_sections(text: str) -> list:
    """Chunk text by markdown sections (headings) with start & end indexes"""
    lines = text.split('\n')
    pattern = r'^(#+|\d+\.)\s+(.+?)$'
    
    chunks = []
    current_title = None
    current_start = None
    section_content = []
    
    # Track character position
    char_pointer = 0
    
    for line in lines:
        line_len = len(line) + 1  # +1 for newline character
        match = re.match(pattern, line)
        
        if match:
            # Save previous section if exists
            if current_title and section_content:
                content = '\n'.join(section_content).strip()
                end_index = char_pointer - line_len
                
                chunks.append({
                    "section": current_title,
                    "content": content,
                    "size": len(content),
                    "start_index": current_start,
                    "end_index": end_index
                })
            
            # Start new section
            current_title = match.group(2)
            section_content = [line]
            current_start = char_pointer
        else:
            # Add to current section
            if current_title is not None:
                section_content.append(line)
        
        # Increment character pointer
        char_pointer += line_len
    
    # Save last section
    if current_title and section_content:
        content = '\n'.join(section_content).strip()
        chunks.append({
            "section": current_title,
            "content": content,
            "size": len(content),
            "start_index": current_start,
            "end_index": len(text)
        })
    
    return chunks


def check_health() -> Dict[str, Any]:
    """Check overall health"""
    try:
        return {
            "status": "healthy",
            "message": "API is running"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": str(e)
        }


def check_pinecone_connection() -> Dict[str, Any]:
    """Check Pinecone connection"""
    try:
        import pinecone
        
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME", "store-knowledge")
        
        if not api_key:
            return {
                "status": "failed",
                "message": "PINECONE_API_KEY not set",
                "error": "Missing environment variable"
            }
        
        # Initialize Pinecone
        pinecone.Pinecone(api_key=api_key)
        
        # Try to get index
        pc = pinecone.Pinecone(api_key=api_key)
        indexes = pc.list_indexes()
        
        index_exists = any(idx.name == index_name for idx in indexes.indexes)
        
        if index_exists:
            return {
                "status": "connected",
                "message": f"Connected to Pinecone index: {index_name}",
                "index_name": index_name
            }
        else:
            return {
                "status": "warning",
                "message": f"Pinecone connected but index '{index_name}' not found",
                "available_indexes": [idx.name for idx in indexes.indexes]
            }
    
    except ImportError:
        return {
            "status": "failed",
            "message": "pinecone-client not installed",
            "error": "pip install pinecone-client"
        }
    
    except Exception as e:
        return {
            "status": "failed",
            "message": f"Pinecone connection failed",
            "error": str(e)
        }


def check_cdc_connection() -> Dict[str, Any]:
    """Check CDC/Kafka connection"""
    try:
        import requests
        
        # Check Kafka via Debezium Connect
        connect_url = os.getenv("KAFKA_CONNECT_URL", "http://localhost:8083")
        
        try:
            response = requests.get(f"{connect_url}/", timeout=5)
            
            if response.status_code == 200:
                return {
                    "status": "connected",
                    "message": f"Connected to Debezium Connect at {connect_url}",
                    "kafka_connect_url": connect_url
                }
            else:
                return {
                    "status": "warning",
                    "message": f"Kafka Connect responded with status {response.status_code}",
                    "status_code": response.status_code
                }
        
        except requests.exceptions.Timeout:
            return {
                "status": "failed",
                "message": f"Kafka Connect at {connect_url} is not responding (timeout)",
                "error": "Connection timeout"
            }
        
        except requests.exceptions.ConnectionError:
            return {
                "status": "failed",
                "message": f"Cannot connect to Kafka Connect at {connect_url}",
                "error": "Connection refused"
            }
    
    except Exception as e:
        return {
            "status": "failed",
            "message": "CDC connection check failed",
            "error": str(e)
        }


def check_mysql_connection() -> Dict[str, Any]:
    """Check MySQL connection"""
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "root")
    mysql_database = os.getenv("MYSQL_DATABASE", "testdb")
    
    try:
        import mysql.connector
        
        try:
            connection = mysql.connector.connect(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                database=mysql_database,
                connection_timeout=5
            )
            
            if connection.is_connected():
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                connection.close()
                
                return {
                    "status": "connected",
                    "message": f"Connected to MySQL at {mysql_host}:{mysql_port}",
                    "host": mysql_host,
                    "port": mysql_port,
                    "database": mysql_database
                }
        
        except mysql.connector.errors.ProgrammingError as e:
            return {
                "status": "failed",
                "message": "MySQL authentication failed",
                "error": str(e)
            }
        
        except mysql.connector.errors.DatabaseError as e:
            return {
                "status": "failed",
                "message": f"MySQL database error",
                "error": str(e)
            }
        
        except TimeoutError:
            return {
                "status": "failed",
                "message": f"MySQL connection timeout at {mysql_host}:{mysql_port}",
                "error": "Connection timeout"
            }
        
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Cannot connect to MySQL at {mysql_host}:{mysql_port}",
                "error": str(e)
            }
    
    except ImportError:
        return {
            "status": "failed",
            "message": "mysql-connector-python not installed",
            "error": "pip install mysql-connector-python"
        }
    
    except Exception as e:
        return {
            "status": "failed",
            "message": "MySQL connection check failed",
            "error": str(e)
        }

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
   
def txt_to_markdown(text):
    lines = text.split("\n")
    md_lines = []

    for line in lines:
        line = line.strip()

        # Heading dạng "1. ABC"
        if re.match(r"^\d+\.\s", line):
            title = re.sub(r"^\d+\.\s", "", line)
            md_lines.append(f"## {title}")
            continue

        # Bullet
        if line.startswith("- "):
            md_lines.append(f"- {line[2:]}")
            continue

        # Đoạn văn bình thường
        if line:
            md_lines.append(line)

        # Dòng trống
        else:
            md_lines.append("")
    
    return "\n".join(md_lines)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "service": "Change Data Capture API",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Comprehensive health check - Health check"""
    health = check_health()
    pinecone = check_pinecone_connection()
    cdc = check_cdc_connection()
    mysql = check_mysql_connection()
    
    # Determine overall status
    all_checks = [health, pinecone, cdc, mysql]
    statuses = [check.get("status") for check in all_checks]
    
    if all("connected" in status or "healthy" in status for status in statuses):
        overall_status = "healthy"
    elif any("failed" in status for status in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"
    
    return HealthCheckResponse(
        status=overall_status,
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        service="Change Data Capture API",
        checks={
            "health": health,
            "pinecone": pinecone,
            "cdc": cdc,
            "mysql": mysql
        }
    )


@app.get("/health/pinecone")
async def health_pinecone():
    """Pinecone connection check"""
    result = check_pinecone_connection()
    
    status_code = 200 if result["status"] in ["connected", "warning"] else 503
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/health/cdc")
async def health_cdc():
    """CDC/Kafka connection check"""
    result = check_cdc_connection()
    
    status_code = 200 if result["status"] in ["connected", "warning"] else 503
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/health/mysql")
async def health_mysql():
    """MySQL connection check"""
    result = check_mysql_connection()
    
    status_code = 200 if result["status"] in ["connected", "warning"] else 503
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/health/all")
async def health_all():
    """Get all health checks in detail"""
    return {
        "timestamp": datetime.now().isoformat(),
        "health": check_health(),
        "pinecone": check_pinecone_connection(),
        "cdc": check_cdc_connection(),
        "mysql": check_mysql_connection()
    }


# =============================================================================
# DATABASE MANAGEMENT ENDPOINTS
# =============================================================================

# Initialize database manager
db_manager = DatabaseManager()


@app.post("/api/v1/table/create", tags=["Table Management"])
async def create_table(request: CreateTableRequest):
    """Create a new table"""
    result = db_manager.create_table(request.table_name)
    status_code = 200 if result["status"] == "success" else 400
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/table/list", tags=["Table Management"])
async def list_tables():
    """Get list of all tables in database"""
    result = db_manager.get_tables()
    status_code = 200 if result["status"] == "success" else 500
    return {
        "status_code": status_code,
        "result": result
    }


@app.delete("/api/v1/table/{table_name}", tags=["Table Management"])
async def delete_table(table_name: str):
    """Delete a table"""
    result = db_manager.delete_table(table_name)
    status_code = 200 if result["status"] == "success" else 400
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/table/{table_name}/columns", tags=["Table Management"])
async def get_table_columns(table_name: str):
    """Get all columns in a table"""
    result = db_manager.get_table_columns(table_name)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 500
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.post("/api/v1/document/{table_name}/add", tags=["Document Management"])
async def add_document(table_name: str, request: AddDocumentRequest):
    """Add new document to table (auto-generate id)"""
    result = db_manager.add_document(table_name, request.content, request.metadata)
    status_code = 201 if result["status"] == "success" else 400
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/document/{table_name}/all", tags=["Document Management"])
async def get_all_documents(table_name: str):
    """Get all documents from table (SELECT *)"""
    result = db_manager.get_all_documents(table_name, limit=999999, offset=0)
    status_code = 200 if result["status"] == "success" else 500
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/document/{table_name}", tags=["Document Management"])
async def list_documents(table_name: str, limit: int = 100, offset: int = 0):
    """Get all documents from table with pagination"""
    result = db_manager.get_all_documents(table_name, limit, offset)
    status_code = 200 if result["status"] == "success" else 500
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/document/{table_name}/{doc_id:int}", tags=["Document Management"])
async def show_document(table_name: str, doc_id: int = Path(...)):
    """Show document content by id"""
    result = db_manager.get_document(table_name, doc_id)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 500
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.get("/api/v1/document/{table_name}/{doc_id}", tags=["Document Management"])
async def show_document_fallback(table_name: str, doc_id: int):
    """Show document content by id"""
    result = db_manager.get_document(table_name, doc_id)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 500
    
    return {
        "status_code": status_code,
        "result": result
    }

# curl -X PUT "http://localhost:8000/api/v1/row/rag/1" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "updates": {
#       "content": "New content here",
#       "metadata": {"category": "automotive", "status": "updated"}
#     }
#   }'
@app.put("/api/v1/document/{table_name}/{doc_id}", tags=["Document Management"])
async def update_document(table_name: str, doc_id: int, request: UpdateDocumentRequest):
    """Update document content"""
    result = db_manager.update_document(table_name, doc_id, request.content)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 500
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.put("/api/v1/row/{table_name}/{row_id}", tags=["Document Management"])
async def update_row(table_name: str, row_id: int, request: UpdateRowRequest):
    """Update specific columns in a row"""
    result = db_manager.update_row_by_columns(table_name, row_id, request.updates)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 400
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.patch("/api/v1/document/{table_name}/{doc_id}/change", tags=["Document Management"])
async def change_document(table_name: str, doc_id: int, request: ChangeDocumentRequest):
    """Change document content (replace from index to index)"""
    result = db_manager.change_document(
        table_name, 
        doc_id, 
        request.from_index, 
        request.to_index, 
        request.content
    )
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 400
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.delete("/api/v1/document/{table_name}/{doc_id}", tags=["Document Management"])
async def delete_document(table_name: str, doc_id: int):
    """Delete document by id"""
    result = db_manager.delete_document(table_name, doc_id)
    
    if result["status"] == "success":
        status_code = 200
    elif result["status"] == "not_found":
        status_code = 404
    else:
        status_code = 500
    
    return {
        "status_code": status_code,
        "result": result
    }


@app.post("/api/v1/document/{table_name}/upload", tags=["Document Management"])
async def upload_document(table_name: str, file: UploadFile = File(...), category: Optional[str] = None):
    """Upload document from file (handles special characters better)"""
    try:
        # Read file content
        content = await file.read()
        text_content = content.decode('utf-8')
        
        # Add to database with metadata
        metadata = {
            "file_name": file.filename,
            "file_size": len(content),
            "content_type": file.content_type,
            "category": category
        }
        result = db_manager.add_document(table_name, text_content, metadata)
        
        if result["status"] == "success":
            status_code = 201
        else:
            status_code = 400
        
        return {
            "status_code": status_code,
            "result": result
        }
    
    except Exception as e:
        return {
            "status_code": 400,
            "result": {
                "status": "failed",
                "message": "Error uploading file",
                "error": str(e)
            }
        }


@app.put("/api/v1/document/{table_name}/{doc_id}/upload", tags=["Document Management"])
async def update_document_with_file(table_name: str, doc_id: int, file: UploadFile = File(...)):
    """Update document content by uploading a new file"""
    try:
        # Read file content
        content = await file.read()
        text_content = content.decode('utf-8')
        
        # Update document with new content
        result = db_manager.update_document(table_name, doc_id, text_content)
        
        if result["status"] == "success":
            status_code = 200
            result["uploaded_file"] = {
                "filename": file.filename,
                "file_size": len(content),
                "content_type": file.content_type
            }
        else:
            status_code = 404 if result["status"] == "not_found" else 400
        
        return {
            "status_code": status_code,
            "result": result
        }
    
    except Exception as e:
        return {
            "status_code": 400,
            "result": {
                "status": "failed",
                "message": "Error updating document with file",
                "error": str(e)
            }
        }


@app.post("/api/v1/document/{table_name}/chunking", tags=["Chunking"])
async def chunking(table_name: str, request: ChunkingRequest):
    """Chunk documents by markdown sections"""
    try:
        # Get documents from table
        if request.all:
            # Get all documents
            result = db_manager.get_all_documents(table_name, limit=999999, offset=0)
        else:
            # Get documents by index range
            if request.from_idx is None or request.to_idx is None:
                return {
                    "status_code": 400,
                    "result": {
                        "status": "failed",
                        "message": "from_idx and to_idx are required when all=false",
                        "error": "Missing parameters"
                    }
                }
            
            # Get documents in range
            result = db_manager.get_all_documents(
                table_name, 
                limit=request.to_idx - request.from_idx + 1,
                offset=request.from_idx
            )
        
        if result["status"] != "success":
            return {
                "status_code": 500,
                "result": result
            }
        
        documents = result["data"]
        all_chunks = []
        
        # Chunk each document
        for doc in documents:
            chunks = chunk_by_sections(doc["content"])
            
            for idx, chunk in enumerate(chunks):
                chunked_item = {
                    "doc_id": doc["id"],
                    "section_title": chunk["section"],
                    "chunk_index": idx,
                    "chunk_size": chunk["size"],
                    "content": chunk["content"],
                    "start_index": chunk["start_index"],
                    "end_index": chunk["end_index"],
                    "original_metadata": doc["metadata"]
                }
                all_chunks.append(chunked_item)
        
        # Generate summary
        summary = {
            "total_documents": len(documents),
            "total_chunks": len(all_chunks),
            "avg_chunk_size": sum(c["chunk_size"] for c in all_chunks) / len(all_chunks) if all_chunks else 0
        }
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Chunking completed: {len(all_chunks)} chunks from {len(documents)} documents",
                "summary": summary,
                "chunks": all_chunks
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error during chunking",
                "error": str(e)
            }
        }

@app.post("/api/v1/document/{table_name}/chunkingEmbPinecone", tags=["Chunking"])
async def chunkingEmbPinecone(table_name: str, request: ChunkingRequest):
    """Chunk documents by markdown sections and embed to Pinecone"""
    try:
        import uuid
        import time
        
        # Get documents from table
        if request.all:
            # Get all documents
            result = db_manager.get_all_documents(table_name, limit=999999, offset=0)
        else:
            # Get documents by index range
            if request.from_idx is None or request.to_idx is None:
                return {
                    "status_code": 400,
                    "result": {
                        "status": "failed",
                        "message": "from_idx and to_idx are required when all=false",
                        "error": "Missing parameters"
                    }
                }
            
            # Get documents in range
            result = db_manager.get_all_documents(
                table_name, 
                limit=request.to_idx - request.from_idx + 1,
                offset=request.from_idx
            )
        
        if result["status"] != "success":
            return {
                "status_code": 500,
                "result": result
            }
        
        documents = result["data"]
        all_chunks = []
        vectors_to_upsert = []
        
        # Chunk each document
        for doc in documents:
            chunks = chunk_by_sections(doc["content"])
            
            for idx, chunk in enumerate(chunks):
                chunked_item = {
                    "doc_id": doc["id"],
                    "section_title": chunk["section"],
                    "chunk_index": idx,
                    "chunk_size": chunk["size"],
                    "content": chunk["content"],
                    "start_index": chunk["start_index"],
                    "end_index": chunk["end_index"],
                    "original_metadata": doc["metadata"]
                }
                all_chunks.append(chunked_item)
                
                # Generate embedding for this chunk
                try:
                    embedding = embeddings.embed_query(chunk["content"])
                    vector_id = str(uuid.uuid4())
                    
                    vectors_to_upsert.append({
                        "id": vector_id,
                        "values": embedding,
                        "metadata": {
                            "doc_id": str(doc["id"]),
                            "section_title": chunk["section"],
                            "chunk_index": idx,
                            "start_index": chunk["start_index"],
                            "end_index": chunk["end_index"],
                            "content": chunk["content"][:500],  # Store first 500 chars
                            "category": doc.get("metadata", {}).get("category", "unknown") if doc.get("metadata") else "unknown"
                        }
                    })
                except Exception as emb_err:
                    print(f"Error embedding chunk {idx}: {str(emb_err)}")
                    continue
        
        # Batch upsert to Pinecone
        batch_size = 50
        upserted_count = 0
        
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            try:
                index_pc.upsert(vectors=batch)
                upserted_count += len(batch)
            except Exception as upsert_err:
                print(f"Error upserting batch: {str(upsert_err)}")
                continue
        
        # Generate summary
        summary = {
            "total_documents": len(documents),
            "total_chunks": len(all_chunks),
            "avg_chunk_size": sum(c["chunk_size"] for c in all_chunks) / len(all_chunks) if all_chunks else 0,
            "vectors_upserted": upserted_count,
            "pinecone_index": PINECONE_INDEX_NAME
        }
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Chunking & embedding completed: {len(all_chunks)} chunks from {len(documents)} documents, {upserted_count} vectors added to Pinecone",
                "summary": summary,
                "chunks": all_chunks
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error during chunking and embedding",
                "error": str(e)
            }
        }
    

@app.post("/api/v1/document/{table_name}/{doc_id}/chunking", tags=["Chunking"])
async def chunking_by_id(table_name: str, doc_id: int):
    """Chunk a specific document by ID"""
    try:
        # Get single document
        result = db_manager.get_document(table_name, doc_id)
        
        if result["status"] != "success":
            return {
                "status_code": 404 if result["status"] == "not_found" else 500,
                "result": result
            }
        
        doc = result["data"]
        all_chunks = []
        
        # Chunk the document
        chunks = chunk_by_sections(doc["content"])
        
        for idx, chunk in enumerate(chunks):
            chunked_item = {
                "doc_id": doc["id"],
                "section_title": chunk["section"],
                "chunk_index": idx,
                "chunk_size": chunk["size"],
                "content": chunk["content"],
                "start_index": chunk["start_index"],
                "end_index": chunk["end_index"],
                "original_metadata": doc["metadata"]
            }
            all_chunks.append(chunked_item)
        
        # Generate summary
        summary = {
            "doc_id": doc["id"],
            "total_chunks": len(all_chunks),
            "avg_chunk_size": sum(c["chunk_size"] for c in all_chunks) / len(all_chunks) if all_chunks else 0
        }
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Chunking completed: {len(all_chunks)} chunks from document {doc_id}",
                "summary": summary,
                "chunks": all_chunks
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error during chunking",
                "error": str(e)
            }
        }


@app.post("/api/v1/document/{table_name}/{doc_id}/chunkingEmbPinecone", tags=["Chunking"])
async def chunking_emb_pinecone_by_id(table_name: str, doc_id: int):
    """Chunk a specific document by ID and embed to Pinecone"""
    try:
        import uuid
        
        # Initialize embeddings
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Get single document
        result = db_manager.get_document(table_name, doc_id)
        
        if result["status"] != "success":
            return {
                "status_code": 404 if result["status"] == "not_found" else 500,
                "result": result
            }
        
        doc = result["data"]
        all_chunks = []
        vectors_to_upsert = []
        
        # Chunk the document
        chunks = chunk_by_sections(doc["content"])
        
        for idx, chunk in enumerate(chunks):
            chunked_item = {
                "doc_id": doc["id"],
                "section_title": chunk["section"],
                "chunk_index": idx,
                "chunk_size": chunk["size"],
                "content": chunk["content"],
                "start_index": chunk["start_index"],
                "end_index": chunk["end_index"],
                "original_metadata": doc["metadata"]
            }
            all_chunks.append(chunked_item)
            
            # Generate embedding for this chunk
            try:
                embedding = embeddings.embed_query(chunk["content"])
                vector_id = f"{doc['id']}_chunk_{idx}_{uuid.uuid4().hex[:8]}"
                
                vectors_to_upsert.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {
                        "doc_id": str(doc["id"]),
                        "section_title": chunk["section"],
                        "chunk_index": idx,
                        "start_index": chunk["start_index"],
                        "end_index": chunk["end_index"],
                        "content": chunk["content"][:500],
                        "category": doc.get("metadata", {}).get("category", "unknown") if doc.get("metadata") else "unknown"
                    }
                })
            except Exception as emb_err:
                print(f"Error embedding chunk {idx}: {str(emb_err)}")
                continue
        
        # Batch upsert to Pinecone
        batch_size = 50
        upserted_count = 0
        
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            try:
                index_pc.upsert(vectors=batch)
                upserted_count += len(batch)
            except Exception as upsert_err:
                print(f"Error upserting batch: {str(upsert_err)}")
                continue
        
        # Generate summary
        summary = {
            "doc_id": doc["id"],
            "total_chunks": len(all_chunks),
            "avg_chunk_size": sum(c["chunk_size"] for c in all_chunks) / len(all_chunks) if all_chunks else 0,
            "vectors_upserted": upserted_count,
            "pinecone_index": PINECONE_INDEX_NAME
        }
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Chunking & embedding completed: {len(all_chunks)} chunks from document {doc_id}, {upserted_count} vectors added to Pinecone",
                "summary": summary,
                "chunks": all_chunks
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error during chunking and embedding",
                "error": str(e)
            }
        }
    

@app.delete("/api/v1/pinecone/clean", tags=["Pinecone"])
async def clean_pinecone():
    """Clean all vectors from Pinecone index"""
    try:
        # Delete all vectors by deleting the index and recreating it
        index_name = PINECONE_INDEX_NAME
        
        # Delete existing index
        try:
            pc.delete_index(index_name)
            print(f"Index {index_name} deleted successfully")
        except Exception as delete_err:
            print(f"Error deleting index: {str(delete_err)}")
        
        # Wait a moment for deletion to complete
        import time
        time.sleep(2)
        
        # Recreate the index
        from pinecone import ServerlessSpec
        
        pc.create_index(
            name=index_name,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        
        # Wait for index to be ready
        time.sleep(5)
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Pinecone index '{index_name}' cleaned and recreated successfully",
                "index_name": index_name
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error cleaning Pinecone index",
                "error": str(e)
            }
        }


@app.get("/api/v1/pinecone/stats", tags=["Pinecone"])
async def pinecone_stats():
    """Get Pinecone index statistics"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Get index stats
        stats = index.describe_index_stats()
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "index_name": index_name,
                "stats": {
                    "total_vector_count": stats.get("total_vector_count", 0),
                    "dimension": stats.get("dimension", 384),
                    "metric": "cosine"
                }
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error getting Pinecone stats",
                "error": str(e)
            }
        }


@app.delete("/api/v1/pinecone/vector/{vector_id}", tags=["Pinecone"])
async def delete_pinecone_vector(vector_id: str):
    """Delete a vector from Pinecone by ID"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Delete vector
        index.delete(ids=[vector_id])
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Vector '{vector_id}' deleted successfully",
                "vector_id": vector_id
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error deleting vector from Pinecone",
                "error": str(e)
            }
        }


class AddVectorRequest(BaseModel):
    vector_id: str
    content: str
    metadata: Optional[Dict] = None


@app.post("/api/v1/pinecone/vector", tags=["Pinecone"])
async def add_pinecone_vector(request: AddVectorRequest):
    """Add a single vector to Pinecone"""
    try:
        import uuid
        
        # Initialize embeddings
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Generate embedding
        embedding = embeddings.embed_query(request.content)
        
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Prepare metadata
        metadata = request.metadata or {}
        metadata["content"] = request.content[:500]  # Store first 500 chars
        
        # Upsert vector
        index.upsert(vectors=[{
            "id": request.vector_id,
            "values": embedding,
            "metadata": metadata
        }])
        
        return {
            "status_code": 201,
            "result": {
                "status": "success",
                "message": f"Vector '{request.vector_id}' added to Pinecone successfully",
                "vector_id": request.vector_id,
                "embedding_dimension": len(embedding),
                "metadata": metadata
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error adding vector to Pinecone",
                "error": str(e)
            }
        }


@app.get("/api/v1/pinecone/vector/{vector_id}/metadata", tags=["Pinecone"])
async def get_vector_by_id(vector_id: str):
    """Get vector data by ID including metadata"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Fetch vector with metadata
        result = index.fetch(ids=[vector_id])
        
        vectors = result.get("vectors", {})
        
        if not vectors:
            return {
                "status_code": 404,
                "result": {
                    "status": "not_found",
                    "message": f"Vector '{vector_id}' not found in Pinecone",
                    "vector_id": vector_id
                }
            }
        
        vector_data = vectors.get(vector_id, {})
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "vector_id": vector_id,
                "embedding_dimension": len(vector_data.get("values", [])),
                "metadata": vector_data.get("metadata", {}),
                "values": vector_data.get("values", [])
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error fetching vector from Pinecone",
                "error": str(e)
            }
        }


@app.get("/api/v1/pinecone/filter/category/{category}", tags=["Pinecone"])
async def filter_by_category(category: str, limit: int = 100):
    """Get all vectors filtered by category"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Query with metadata filter for category
        results = index.query(
            vector=[0] * 384,  # Dummy vector for metadata-only query
            filter={"category": {"$eq": category}},
            top_k=limit,
            include_metadata=True
        )
        
        matches = results.get("matches", [])
        
        if not matches:
            return {
                "status_code": 200,
                "result": {
                    "status": "success",
                    "message": f"No vectors found for category '{category}'",
                    "category": category,
                    "total_count": 0,
                    "vectors": []
                }
            }
        
        # Format results
        formatted_vectors = []
        for match in matches:
            formatted_vectors.append({
                "vector_id": match["id"],
                "score": match.get("score", 0),
                "metadata": match.get("metadata", {}),
                "doc_id": match.get("metadata", {}).get("doc_id"),
                "section_title": match.get("metadata", {}).get("section_title"),
                "chunk_index": match.get("metadata", {}).get("chunk_index"),
                "content_preview": match.get("metadata", {}).get("content", "")[:200]
            })
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Found {len(matches)} vectors for category '{category}'",
                "category": category,
                "total_count": len(matches),
                "vectors": formatted_vectors
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error filtering vectors by category",
                "error": str(e)
            }
        }


@app.get("/api/v1/pinecone/filter/doc/{doc_id}", tags=["Pinecone"])
async def filter_by_doc_id(doc_id: int, limit: int = 100):
    """Get all vectors for a specific document"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Query with metadata filter for doc_id
        results = index.query(
            vector=[0] * 384,  # Dummy vector for metadata-only query
            filter={"doc_id": {"$eq": str(doc_id)}},
            top_k=limit,
            include_metadata=True
        )
        
        matches = results.get("matches", [])
        
        if not matches:
            return {
                "status_code": 200,
                "result": {
                    "status": "success",
                    "message": f"No vectors found for doc_id '{doc_id}'",
                    "doc_id": doc_id,
                    "total_count": 0,
                    "vectors": []
                }
            }
        
        # Format results
        formatted_vectors = []
        for match in matches:
            formatted_vectors.append({
                "vector_id": match["id"],
                "score": match.get("score", 0),
                "metadata": match.get("metadata", {}),
                "section_title": match.get("metadata", {}).get("section_title"),
                "chunk_index": match.get("metadata", {}).get("chunk_index"),
                "start_index": match.get("metadata", {}).get("start_index"),
                "end_index": match.get("metadata", {}).get("end_index"),
                "category": match.get("metadata", {}).get("category"),
                "content_preview": match.get("metadata", {}).get("content", "")[:300]
            })
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Found {len(matches)} vectors for doc_id '{doc_id}'",
                "doc_id": doc_id,
                "total_count": len(matches),
                "vectors": formatted_vectors
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error filtering vectors by doc_id",
                "error": str(e)
            }
        }


@app.delete("/api/v1/pinecone/delete/category/{category}", tags=["Pinecone"])
async def delete_by_category(category: str):
    """Delete all vectors with a specific category"""
    try:
        index_name = PINECONE_INDEX_NAME
        index = pc.Index(index_name)
        
        # Query all vectors with this category
        results = index.query(
            vector=[0] * 384,  # Dummy vector for metadata-only query
            filter={"category": {"$eq": category}},
            top_k=10000,
            include_metadata=True
        )
        
        matches = results.get("matches", [])
        
        if not matches:
            return {
                "status_code": 200,
                "result": {
                    "status": "success",
                    "message": f"No vectors found for category '{category}'",
                    "category": category,
                    "deleted_count": 0
                }
            }
        
        # Extract vector IDs
        vector_ids = [match["id"] for match in matches]
        
        # Delete vectors
        index.delete(ids=vector_ids)
        
        return {
            "status_code": 200,
            "result": {
                "status": "success",
                "message": f"Successfully deleted {len(vector_ids)} vectors for category '{category}'",
                "category": category,
                "deleted_count": len(vector_ids),
                "deleted_ids": vector_ids
            }
        }
    
    except Exception as e:
        return {
            "status_code": 500,
            "result": {
                "status": "failed",
                "message": "Error deleting vectors by category",
                "error": str(e)
            }
        }

    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info", reload=True)
    



