"""
Database operations for CDC application
"""

import os
import mysql.connector
from mysql.connector import Error
from typing import List, Dict, Any, Optional
from datetime import datetime


class DatabaseManager:
    """Manage MySQL database operations"""
    
    def __init__(self):
        """Initialize database connection parameters"""
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.port = int(os.getenv("MYSQL_PORT", "3306"))
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "root")
        self.database = os.getenv("MYSQL_DATABASE", "testdb")
    
    def get_connection(self):
        """Get database connection"""
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            return connection
        except Error as e:
            raise Exception(f"Database connection error: {e}")
    
    def create_table(self, table_name: str) -> Dict[str, Any]:
        """Create a new table with id, content, and metadata columns"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Validate table name (prevent SQL injection)
            if not table_name.isidentifier():
                return {
                    "status": "failed",
                    "message": f"Invalid table name: {table_name}",
                    "error": "Table name must be alphanumeric with underscores"
                }
            
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS `{table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content LONGTEXT NOT NULL,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            
            cursor.execute(create_table_query)
            connection.commit()
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": f"Table '{table_name}' created successfully",
                "table_name": table_name
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": f"Error creating table",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Unexpected error",
                "error": str(e)
            }
    
    def get_tables(self) -> Dict[str, Any]:
        """Get list of all tables in database"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            cursor.execute(f"SHOW TABLES FROM `{self.database}`")
            tables = cursor.fetchall()
            table_list = [table[0] for table in tables]
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": f"Found {len(table_list)} tables",
                "tables": table_list,
                "count": len(table_list)
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error retrieving tables",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def delete_table(self, table_name: str) -> Dict[str, Any]:
        """Delete a table"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Validate table name (prevent SQL injection)
            if not table_name.isidentifier():
                return {
                    "status": "failed",
                    "message": f"Invalid table name: {table_name}",
                    "error": "Table name must be alphanumeric with underscores"
                }
            
            drop_table_query = f"DROP TABLE IF EXISTS `{table_name}`"
            cursor.execute(drop_table_query)
            connection.commit()
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": f"Table '{table_name}' deleted successfully",
                "table_name": table_name
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": f"Error deleting table",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Unexpected error",
                "error": str(e)
            }
    
    def get_table_columns(self, table_name: str) -> Dict[str, Any]:
        """Get all columns in a table"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Validate table name (prevent SQL injection)
            if not table_name.isidentifier():
                return {
                    "status": "failed",
                    "message": f"Invalid table name: {table_name}",
                    "error": "Table name must be alphanumeric with underscores"
                }
            
            # Get columns information
            query = f"DESCRIBE `{table_name}`"
            cursor.execute(query)
            results = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            if not results:
                return {
                    "status": "not_found",
                    "message": f"Table '{table_name}' not found",
                    "table_name": table_name
                }
            
            columns = []
            for row in results:
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "null": row[2],
                    "key": row[3],
                    "default": row[4],
                    "extra": row[5]
                })
            
            return {
                "status": "success",
                "table_name": table_name,
                "columns": columns,
                "count": len(columns)
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error retrieving table columns",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def add_document(self, table_name: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Add new document (auto-generate id)"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            import json
            metadata_json = json.dumps(metadata) if metadata else None
            
            insert_query = f"INSERT INTO `{table_name}` (content, metadata) VALUES (%s, %s)"
            cursor.execute(insert_query, (content, metadata_json))
            connection.commit()
            
            doc_id = cursor.lastrowid
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": "Document added successfully",
                "id": doc_id,
                "table_name": table_name
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": f"Error adding document",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Unexpected error",
                "error": str(e)
            }
    
    def get_document(self, table_name: str, doc_id: int) -> Dict[str, Any]:
        """Show document content by id"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = f"SELECT id, content, metadata, created_at, updated_at FROM `{table_name}` WHERE id = %s"
            cursor.execute(query, (doc_id,))
            result = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            if not result:
                return {
                    "status": "not_found",
                    "message": f"Document with id {doc_id} not found",
                    "id": doc_id
                }
            
            import json
            metadata = json.loads(result[2]) if result[2] else None
            
            return {
                "status": "success",
                "data": {
                    "id": result[0],
                    "content": result[1],
                    "metadata": metadata,
                    "created_at": result[3].isoformat() if result[3] else None,
                    "updated_at": result[4].isoformat() if result[4] else None
                }
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error retrieving document",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def update_document(self, table_name: str, doc_id: int, content: str) -> Dict[str, Any]:
        """Update document content"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = f"UPDATE `{table_name}` SET content = %s WHERE id = %s"
            cursor.execute(query, (content, doc_id))
            connection.commit()
            
            if cursor.rowcount == 0:
                cursor.close()
                connection.close()
                return {
                    "status": "not_found",
                    "message": f"Document with id {doc_id} not found"
                }
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": "Document updated successfully",
                "id": doc_id
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error updating document",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def update_row_by_columns(self, table_name: str, row_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update specific columns in a row"""
        try:
            if not updates:
                return {
                    "status": "failed",
                    "message": "No updates provided",
                    "error": "updates dictionary is empty"
                }
            
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Build SET clause
            set_clauses = []
            values = []
            
            for column, value in updates.items():
                # Validate column name (prevent SQL injection)
                if not column.isidentifier():
                    cursor.close()
                    connection.close()
                    return {
                        "status": "failed",
                        "message": f"Invalid column name: {column}",
                        "error": "Column name must be alphanumeric with underscores"
                    }
                
                set_clauses.append(f"`{column}` = %s")
                
                # Handle JSON metadata specially
                if column == "metadata" and isinstance(value, dict):
                    import json
                    values.append(json.dumps(value, ensure_ascii=False))
                else:
                    values.append(value)
            
            values.append(row_id)
            
            # Build query
            set_str = ", ".join(set_clauses)
            query = f"UPDATE `{table_name}` SET {set_str} WHERE id = %s"
            
            cursor.execute(query, values)
            connection.commit()
            
            if cursor.rowcount == 0:
                cursor.close()
                connection.close()
                return {
                    "status": "not_found",
                    "message": f"Row with id {row_id} not found in table '{table_name}'"
                }
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": "Row updated successfully",
                "table_name": table_name,
                "id": row_id,
                "updated_columns": list(updates.keys())
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error updating row",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def change_document(self, table_name: str, doc_id: int, from_index: int, to_index: int, content: str) -> Dict[str, Any]:
        """Change content from index to index (substring replacement)"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Get current content
            query = f"SELECT content FROM `{table_name}` WHERE id = %s"
            cursor.execute(query, (doc_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                connection.close()
                return {
                    "status": "not_found",
                    "message": f"Document with id {doc_id} not found"
                }
            
            current_content = result[0]
            
            # Validate indices
            if from_index < 0 or to_index < 0 or from_index > to_index or to_index > len(current_content):
                cursor.close()
                connection.close()
                return {
                    "status": "failed",
                    "message": "Invalid indices",
                    "error": f"from_index: {from_index}, to_index: {to_index}, content_length: {len(current_content)}"
                }
            
            # Replace substring
            new_content = current_content[:from_index] + content + current_content[to_index:]
            
            # Update document
            update_query = f"UPDATE `{table_name}` SET content = %s WHERE id = %s"
            cursor.execute(update_query, (new_content, doc_id))
            connection.commit()
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": "Document content changed successfully",
                "id": doc_id,
                "original_length": len(current_content),
                "new_length": len(new_content)
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error changing document content",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def delete_document(self, table_name: str, doc_id: int) -> Dict[str, Any]:
        """Delete document by id"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = f"DELETE FROM `{table_name}` WHERE id = %s"
            cursor.execute(query, (doc_id,))
            connection.commit()
            
            if cursor.rowcount == 0:
                cursor.close()
                connection.close()
                return {
                    "status": "not_found",
                    "message": f"Document with id {doc_id} not found"
                }
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "message": "Document deleted successfully",
                "id": doc_id
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error deleting document",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
    
    def get_all_documents(self, table_name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get all documents from table with pagination"""
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM `{table_name}`"
            cursor.execute(count_query)
            total = cursor.fetchone()[0]
            
            # Get documents
            query = f"SELECT id, content, metadata, created_at, updated_at FROM `{table_name}` ORDER BY id DESC LIMIT %s OFFSET %s"
            cursor.execute(query, (limit, offset))
            results = cursor.fetchall()
            
            import json
            documents = []
            for result in results:
                metadata = json.loads(result[2]) if result[2] else None
                documents.append({
                    "id": result[0],
                    "content": result[1],
                    "metadata": metadata,
                    "created_at": result[3].isoformat() if result[3] else None,
                    "updated_at": result[4].isoformat() if result[4] else None
                })
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "data": documents,
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": len(documents)
            }
        
        except Error as e:
            return {
                "status": "failed",
                "message": "Error retrieving documents",
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": "Unexpected error",
                "error": str(e)
            }
