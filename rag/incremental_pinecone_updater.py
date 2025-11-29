"""
Incremental Pinecone Updater - Xử lý partial updates từ CDC events
Thay vì re-ingest toàn bộ, chỉ update những phần thay đổi
"""

import os
import json
import uuid
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import sqlite3

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone

class IncrementalPineconeUpdater:
    """
    Cập nhật Pinecone incrementally dựa trên CDC events
    Không cần re-index toàn bộ data
    """
    
    def __init__(self, pinecone_api_key: str, index_name: str = "store-knowledge"):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index_name = index_name
        self.index = self.pc.Index(index_name)
        
        # Initialize metadata tracking
        self.metadata_db = "rag/update_metadata.db"
        self._init_metadata_db()
    
    def _init_metadata_db(self):
        """Khởi tạo SQLite cho tracking incremental updates"""
        conn = sqlite3.connect(self.metadata_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_metadata (
                id TEXT PRIMARY KEY,
                content_hash TEXT,
                source TEXT,
                timestamp TEXT,
                embedding_model TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS update_log (
                id INTEGER PRIMARY KEY,
                vector_id TEXT,
                operation TEXT,
                timestamp TEXT,
                cdc_source TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _save_metadata(self, vector_id: str, content_hash: str, source: str):
        """Lưu metadata của vector vào SQLite"""
        conn = sqlite3.connect(self.metadata_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO vector_metadata 
            (id, content_hash, source, timestamp, embedding_model)
            VALUES (?, ?, ?, ?, ?)
        """, (
            vector_id,
            content_hash,
            source,
            datetime.now().isoformat(),
            "sentence-transformers/all-MiniLM-L6-v2"
        ))
        
        conn.commit()
        conn.close()
    
    def _log_update(self, vector_id: str, operation: str, cdc_source: str):
        """Ghi log update operation"""
        conn = sqlite3.connect(self.metadata_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO update_log (vector_id, operation, timestamp, cdc_source)
            VALUES (?, ?, ?, ?)
        """, (vector_id, operation, datetime.now().isoformat(), cdc_source))
        
        conn.commit()
        conn.close()
    
    def update_single_chunk(self, content: str, metadata: Dict, 
                           vector_id: Optional[str] = None) -> str:
        """
        Update một chunk duy nhất (cho UPDATE/INSERT)
        
        Args:
            content: Nội dung text cần embedding
            metadata: Metadata để lưu (category, source, etc.)
            vector_id: ID cũ nếu là update; None nếu là insert
        
        Returns:
            vector_id của chunk vừa update/insert
        """
        
        # Tạo embedding
        embedding = self.embeddings.embed_query(content)
        
        # Tạo vector ID nếu chưa có
        if vector_id is None:
            vector_id = str(uuid.uuid4())
            operation = "insert"
        else:
            operation = "update"
        
        # Chuẩn bị metadata
        full_metadata = {
            "content": content,
            "updated_at": datetime.now().isoformat(),
            "operation": operation,
            **metadata
        }
        
        # Upsert vào Pinecone
        self.index.upsert(vectors=[
            {
                "id": vector_id,
                "values": embedding,
                "metadata": full_metadata
            }
        ])
        
        # Lưu metadata locally
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()
        self._save_metadata(
            vector_id,
            content_hash,
            metadata.get("source", "unknown")
        )
        
        # Log operation
        self._log_update(vector_id, operation, "cdc")
        
        return vector_id
    
    def delete_chunk(self, vector_id: str):
        """Xóa một chunk khỏi Pinecone"""
        self.index.delete(ids=[vector_id])
        self._log_update(vector_id, "delete", "cdc")
    
    def batch_update_chunks(self, chunks: List[Dict]) -> List[str]:
        """
        Update nhiều chunks cùng lúc (batch processing)
        
        Args:
            chunks: List of {content, metadata, vector_id (optional)}
        
        Returns:
            List of vector IDs
        """
        
        vectors = []
        vector_ids = []
        
        for chunk in chunks:
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})
            vector_id = chunk.get("vector_id") or str(uuid.uuid4())
            
            # Tạo embedding
            embedding = self.embeddings.embed_query(content)
            
            # Chuẩn bị metadata
            full_metadata = {
                "content": content,
                "updated_at": datetime.now().isoformat(),
                **metadata
            }
            
            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": full_metadata
            })
            
            vector_ids.append(vector_id)
        
        # Batch upsert
        if vectors:
            self.index.upsert(vectors=vectors)
            
            # Log all operations
            for vector_id in vector_ids:
                self._log_update(vector_id, "batch_update", "cdc")
        
        return vector_ids
    
    def process_cdc_event(self, event: Dict) -> Dict:
        """
        Xử lý CDC event từ Kafka
        
        Event format:
        {
            "op": "u|c|d",
            "before": {...},
            "after": {...},
            "source": {"table": "stores", "db": "rag_db"}
        }
        """
        
        op = event.get("op")  # c=create, u=update, d=delete
        before = event.get("before", {})
        after = event.get("after", {})
        source = event.get("source", {})
        
        table = source.get("table", "unknown")
        result = {
            "operation": op,
            "table": table,
            "status": "pending",
            "vector_ids": [],
            "message": ""
        }
        
        try:
            if op == "c":  # CREATE - INSERT mới vào Pinecone
                content = self._format_content(after)
                metadata = {
                    "source": f"{table}",
                    "record_id": after.get("id", "unknown"),
                    "operation": "insert"
                }
                
                vector_id = self.update_single_chunk(content, metadata)
                result["vector_ids"] = [vector_id]
                result["status"] = "success"
                result["message"] = f"Inserted 1 new vector: {vector_id}"
            
            elif op == "u":  # UPDATE - chỉ embed những field thay đổi
                changed_fields = self._detect_changes(before, after)
                
                if changed_fields:
                    # Tạo content chỉ cho những field thay đổi
                    content = self._format_changes(changed_fields)
                    
                    # Query existing vector (dùng record_id)
                    record_id = after.get("id", "unknown")
                    vector_id = self._find_vector_by_record_id(record_id, table)
                    
                    metadata = {
                        "source": f"{table}",
                        "record_id": record_id,
                        "operation": "update",
                        "changed_fields": list(changed_fields.keys())
                    }
                    
                    if vector_id:
                        # Update existing vector
                        self.update_single_chunk(content, metadata, vector_id)
                        result["vector_ids"] = [vector_id]
                        result["message"] = f"Updated vector: {vector_id}"
                    else:
                        # Insert mới nếu vector chưa tồn tại
                        vector_id = self.update_single_chunk(content, metadata)
                        result["vector_ids"] = [vector_id]
                        result["message"] = f"Created new vector (not found): {vector_id}"
                    
                    result["status"] = "success"
                else:
                    result["status"] = "skipped"
                    result["message"] = "No changes detected"
            
            elif op == "d":  # DELETE - xóa khỏi Pinecone
                record_id = before.get("id", "unknown")
                vector_id = self._find_vector_by_record_id(record_id, table)
                
                if vector_id:
                    self.delete_chunk(vector_id)
                    result["vector_ids"] = [vector_id]
                    result["status"] = "success"
                    result["message"] = f"Deleted vector: {vector_id}"
                else:
                    result["status"] = "skipped"
                    result["message"] = f"Vector not found for record {record_id}"
        
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
        
        return result
    
    def _format_content(self, record: Dict) -> str:
        """Chuyển record thành text content"""
        lines = []
        for key, value in record.items():
            if value is not None:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    
    def _format_changes(self, changes: Dict) -> str:
        """Chuyển changes thành text content"""
        lines = [f"[UPDATED FIELDS]"]
        for field, (old_val, new_val) in changes.items():
            lines.append(f"{field}:")
            lines.append(f"  Old: {old_val}")
            lines.append(f"  New: {new_val}")
        return "\n".join(lines)
    
    def _detect_changes(self, before: Dict, after: Dict) -> Dict:
        """Phát hiện những field nào đã thay đổi"""
        changes = {}
        
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            old_val = before.get(key)
            new_val = after.get(key)
            
            if old_val != new_val:
                changes[key] = (old_val, new_val)
        
        return changes
    
    def _find_vector_by_record_id(self, record_id: str, table: str) -> Optional[str]:
        """Tìm vector_id dựa trên record_id"""
        conn = sqlite3.connect(self.metadata_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM vector_metadata
            WHERE source = ? AND id IN (
                SELECT id FROM vector_metadata
                WHERE json_extract(metadata, '$.record_id') = ?
            )
            LIMIT 1
        """, (table, str(record_id)))
        
        result = cursor.fetchone()
        conn.close()
        
        return result["id"] if result else None
    
    def get_update_stats(self) -> Dict:
        """Lấy thống kê updates"""
        conn = sqlite3.connect(self.metadata_db)
        cursor = conn.cursor()
        
        # Count by operation
        cursor.execute("SELECT operation, COUNT(*) FROM update_log GROUP BY operation")
        operations = dict(cursor.fetchall())
        
        # Total vectors
        cursor.execute("SELECT COUNT(*) FROM vector_metadata")
        total_vectors = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_vectors": total_vectors,
            "operations": operations,
            "timestamp": datetime.now().isoformat()
        }
