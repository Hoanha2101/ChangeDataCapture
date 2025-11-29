# 🚀 CDC + Incremental RAG with FastAPI - Usage Guide

## 📋 Mục Lục

1. [Giới thiệu](#giới-thiệu)
2. [Setup](#setup)
3. [Chạy hệ thống](#chạy-hệ-thống)
4. [API Endpoints](#api-endpoints)
5. [Use Cases](#use-cases)
6. [Monitoring & Debugging](#monitoring--debugging)

---

## 🎯 Giới Thiệu

Đây là một **production-ready** hệ thống kết hợp:

- **FastAPI**: REST API để quản lý ingestion & updates
- **CDC (Change Data Capture)**: Kafka consumer lắng nghe MySQL changes real-time
- **Incremental Updates**: Chỉ update những phần thay đổi vào Pinecone (không re-embed toàn bộ)
- **Local Embeddings**: Dùng HuggingFace (free, không cần API key)
- **Monitoring Dashboard**: Built-in stats & health checks

```
┌────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  MySQL           Debezium        Kafka                    │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐             │
│  │ Changes ├───→│ Capture  ├───→│  CDC    │             │
│  │         │    │          │    │  Topic  │             │
│  └─────────┘    └──────────┘    └────┬────┘             │
│                                        │                  │
│                                        ▼                  │
│                                 ┌─────────────────┐      │
│                                 │  FastAPI Server │      │
│                                 ├─────────────────┤      │
│                                 │ CDC Consumer    │      │
│                                 │ Incremental     │      │
│                                 │ Updater         │      │
│                                 └────────┬────────┘      │
│                                          │               │
│                                          ▼               │
│                                    ┌────────────┐        │
│                                    │  Pinecone  │        │
│                                    │ Vector DB  │        │
│                                    └────────────┘        │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## 🔧 Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Environment Variables

Copy `.env.example` → `.env` và điền các giá trị:

```bash
cp .env.example .env
```

Edit `.env`:
```env
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=store-knowledge
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CDC_TOPIC=mysql-server.rag_db.stores
FASTAPI_PORT=8000
```

### 3. Start CDC Infrastructure

```bash
# Khởi động Docker containers (MySQL, Kafka, Debezium, etc.)
cd ..
docker-compose up -d

# Chờ ~30 giây để services khởi động

# Kiểm tra status
docker-compose ps
```

### 4. Setup Database & Connector

```bash
# Tạo database & table
docker-compose exec -T mysql mysql -uroot -proot -e ^
  "CREATE DATABASE IF NOT EXISTS rag_db; CREATE TABLE IF NOT EXISTS rag_db.stores (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(255), phone VARCHAR(20), address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"

# Tạo Debezium connector
create_connector.bat
```

---

## 🚀 Chạy Hệ Thống

### Option 1: Full Ingestion + CDC Listener

```bash
# Terminal 1: FastAPI Server
cd rag
python -m uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Trigger full ingestion
curl -X POST http://localhost:8000/api/v1/ingest/full \
  -H "Content-Type: application/json" \
  -d '{"data_folder": "./rag", "force_recreate_index": true}'

# Terminal 3: Start CDC Consumer
curl -X POST http://localhost:8000/api/v1/cdc/start

# Terminal 4: Monitor CDC
curl http://localhost:8000/api/v1/cdc/status
```

### Option 2: Just Run the Server

```bash
cd rag
python -m uvicorn fastapi_server:app --host 0.0.0.0 --port 8000
```

Truy cập:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Stats**: http://localhost:8000/api/v1/stats

---

## 📡 API Endpoints

### Health & Status

```bash
# Health check
curl http://localhost:8000/health

# Get all stats
curl http://localhost:8000/api/v1/stats

# Reset stats
curl -X POST http://localhost:8000/api/v1/stats/reset
```

### Full Data Ingestion

```bash
# Trigger full ingestion (background task)
curl -X POST http://localhost:8000/api/v1/ingest/full \
  -H "Content-Type: application/json" \
  -d '{
    "data_folder": "./rag",
    "force_recreate_index": true
  }'

# Get ingestion status
curl http://localhost:8000/api/v1/ingest/status
```

### CDC Consumer Management

```bash
# Start CDC consumer (listen to Kafka)
curl -X POST http://localhost:8000/api/v1/cdc/start

# Stop CDC consumer
curl -X POST http://localhost:8000/api/v1/cdc/stop

# Get CDC status
curl http://localhost:8000/api/v1/cdc/status
```

### Manual CDC Event (Testing)

```bash
# Simulate UPDATE event
curl -X POST http://localhost:8000/api/v1/cdc/event \
  -H "Content-Type: application/json" \
  -d '{
    "op": "u",
    "before": {"id": 1, "phone": "0909 456 123"},
    "after": {"id": 1, "phone": "0909 777 888"},
    "table": "stores"
  }'

# Simulate INSERT event
curl -X POST http://localhost:8000/api/v1/cdc/event \
  -H "Content-Type: application/json" \
  -d '{
    "op": "c",
    "after": {"id": 2, "name": "Store 2", "phone": "0909 999 999"},
    "table": "stores"
  }'

# Simulate DELETE event
curl -X POST http://localhost:8000/api/v1/cdc/event \
  -H "Content-Type: application/json" \
  -d '{
    "op": "d",
    "before": {"id": 2},
    "table": "stores"
  }'
```

### Manual Vector Updates

```bash
# Update/Insert một vector
curl -X POST http://localhost:8000/api/v1/update/single \
  -H "Content-Type: application/json" \
  -d '{
    "content": "GreenLife Mart - Phone: 0909 777 888",
    "record_id": "1",
    "source": "stores"
  }'

# Batch update vectors
curl -X POST http://localhost:8000/api/v1/update/batch \
  -H "Content-Type: application/json" \
  -d '[
    {
      "content": "Store 1 - Updated",
      "metadata": {"record_id": "1", "source": "stores"}
    },
    {
      "content": "Store 2 - New",
      "metadata": {"record_id": "2", "source": "stores"}
    }
  ]'

# Delete a vector
curl -X DELETE http://localhost:8000/api/v1/update/vector/uuid-here
```

---

## 🎯 Use Cases

### Use Case 1: Initial Data Setup

```bash
# 1. Insert data vào MySQL
docker-compose exec -T mysql mysql -uroot -proot rag_db -e \
  "INSERT INTO stores (name, phone, address) VALUES ('GreenLife Mart 1', '0909 111 111', '888A Nguyễn Thị Minh Khai');"

# 2. Start server
python -m uvicorn fastapi_server:app --reload

# 3. Trigger full ingestion
curl -X POST http://localhost:8000/api/v1/ingest/full

# 4. Start CDC listener
curl -X POST http://localhost:8000/api/v1/cdc/start

# 5. Check stats
watch -n 1 "curl -s http://localhost:8000/api/v1/stats | jq"
```

### Use Case 2: Real-time Updates via CDC

```bash
# Terminal 1: Watch stats
watch -n 1 "curl -s http://localhost:8000/api/v1/stats | jq .cdc_consumer.stats"

# Terminal 2: Make updates to MySQL
docker-compose exec -T mysql mysql -uroot -proot rag_db -e \
  "UPDATE stores SET phone='0909 222 222' WHERE id=1;"

# → CDC Consumer automatically detects & updates Pinecone!
```

### Use Case 3: Manual Event Testing

```bash
# Test UPDATE → Pinecone incremental update
curl -X POST http://localhost:8000/api/v1/cdc/event \
  -H "Content-Type: application/json" \
  -d '{
    "op": "u",
    "before": {"id": 1, "phone": "0909 111 111"},
    "after": {"id": 1, "phone": "0909 333 333"},
    "table": "stores"
  }'
```

---

## 📊 Monitoring & Debugging

### Check CDC Consumer Status

```bash
curl http://localhost:8000/api/v1/cdc/status | jq
```

Output:
```json
{
  "is_running": true,
  "topic": "mysql-server.rag_db.stores",
  "uptime_seconds": 123.45,
  "stats": {
    "total_messages": 5,
    "successful_updates": 4,
    "failed_updates": 0,
    "skipped_updates": 1
  },
  "pinecone_stats": {
    "total_vectors": 10,
    "operations": {
      "insert": 3,
      "update": 2,
      "delete": 1,
      "batch_update": 4
    }
  }
}
```

### View Kafka Messages Directly

```bash
# View CDC events as they come in
docker-compose exec -T kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic mysql-server.rag_db.stores \
  --from-beginning \
  --max-messages 10
```

### View FastAPI Logs

```bash
# Follow server logs (if running with reload)
tail -f fastapi_server.log
```

### Debug Pinecone Metadata

```bash
# Query SQLite metadata database
sqlite3 rag/update_metadata.db "SELECT * FROM update_log LIMIT 10;"
sqlite3 rag/update_metadata.db "SELECT COUNT(*) FROM vector_metadata;"
```

---

## 💡 Tips & Tricks

### Tip 1: Batch Processing for Performance

Set `CDC_BATCH_SIZE=32` in `.env` để group updates trước khi embedding.

### Tip 2: Custom Embedding Models

```python
# In incremental_pinecone_updater.py
self.embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2"  # Hoặc model khác
)
```

### Tip 3: Enable Auto-Start CDC on Server Startup

```python
# In fastapi_server.py startup_event()
@app.on_event("startup")
async def startup_event():
    ...
    # Auto-start CDC if configured
    if os.getenv("CDC_CONSUMER_AUTO_START", "false").lower() == "true":
        cdc_consumer.start()
```

### Tip 4: Export Stats for Monitoring

```bash
# Export to JSON every 10 seconds
while true; do
  curl -s http://localhost:8000/api/v1/stats | jq . > stats_$(date +%s).json
  sleep 10
done
```

---

## 🐛 Troubleshooting

### Problem: CDC Consumer not getting messages

```bash
# 1. Check Kafka is running
docker-compose ps kafka

# 2. Check topic exists
docker-compose exec -T kafka kafka-topics --list --bootstrap-server localhost:9092

# 3. Check messages in topic
docker-compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mysql-server.rag_db.stores --from-beginning --max-messages 5
```

### Problem: Pinecone connection error

```bash
# 1. Verify API key in .env
cat .env | grep PINECONE_API_KEY

# 2. Test Pinecone connection
python -c "from pinecone import Pinecone; pc = Pinecone(api_key='your-key'); print(pc.list_indexes())"
```

### Problem: Embedding model download slow

```bash
# Pre-download embedding model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

---

## 📚 Advanced Configuration

### Custom Chunking Strategy

```python
# In ingest_data.py
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,    # Increase for longer contexts
    chunk_overlap=100,  # More overlap = better recall
    separators=["\n\n", "\n", " ", ""]
)
```

### Scale to Production

```bash
# Run with Gunicorn (production ASGI server)
gunicorn fastapi_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

---

**Happy RAG-ing! 🎉**
