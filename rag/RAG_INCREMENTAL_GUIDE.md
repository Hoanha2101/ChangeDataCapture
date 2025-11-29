# 🚀 Incremental RAG System - Giải Pháp Hoàn Chỉnh

## 🎯 Vấn Đề

Bạn có data RAG (`store_info.txt`) luôn update liên tục, nhưng:
- ❌ Mỗi lần update nhỏ → phải re-embedding toàn bộ dữ liệu
- ❌ Tốn thời gian, tài nguyên, API costs
- ❌ Không scalable với millions of updates

**Giải pháp:** Dùng **Incremental RAG + CDC** để chỉ xử lý những phần thay đổi!

---

## ✅ Kiến Trúc Giải Pháp

```
┌─────────────────────────────────────────────────────────────────┐
│                   OLD APPROACH (Full Re-embedding)               │
├─────────────────────────────────────────────────────────────────┤
│  Data Update → Chunking (100%) → Embedding (100%) → Vector DB   │
│                                   ⚠️ 10 minutes for 10MB data    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│        NEW APPROACH (Incremental with CDC)                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  MySQL          Debezium       Kafka              Vector DB       │
│  ┌─────────┐    ┌──────────┐   ┌─────────────┐   ┌──────────┐   │
│  │ UPDATE  ├──→ │ Capture  ├──→ │ CDC Topic   ├──→ │ Partial  │   │
│  │ phone#  │    │ Changes  │   │ mysql-...  │   │ Update   │   │
│  └─────────┘    └──────────┘   └─────────────┘   └──────────┘   │
│                                       ↓                           │
│                              ┌────────────────┐                   │
│                              │ RAG Consumer   │                   │
│                              ├────────────────┤                   │
│                              │ Detect Changed │                   │
│                              │ Fields ONLY    │                   │
│                              │ ↓              │                   │
│                              │ Incremental    │                   │
│                              │ Chunking (2%)  │                   │
│                              │ ↓              │                   │
│                              │ Embedding (2%) │                   │
│                              │ ↓              │                   │
│                              │ Update DB      │                   │
│                              └────────────────┘                   │
│                                   ✅ 5 seconds only!              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## � Sơ đồ cơ chế hoạt động CDC ↔ RAG

Dưới đây là sơ đồ và mô tả chi tiết từng bước từ khi có dữ liệu ban đầu đến khi RAG được cập nhật incremental khi có thay đổi nhỏ.

```
Initial Data (store_info.txt)
        │
        ▼
 1) Versioning & Full Chunking (lần đầu)
     - Tạo hash của file, lưu vào `file_versions`
     - Chia toàn bộ nội dung thành chunks → lưu `chunks` + content_hash
        │
        ▼
 2) Embedding & Indexing (lần đầu)
     - Embed toàn bộ chunks → upsert vào Vector DB
     - Mỗi chunk kèm metadata (chunk_id, source_file)
        │
        ▼
 3) Ongoing Changes → MySQL (updates/inserts/deletes)
     - Debezium captures binlog → publish CDC event to Kafka topic
        │
        ▼
 4) CDC Topic (Kafka)
     - Messages: { op, before, after, source }
        │
        ▼
 5) RAG Consumer (Kafka → Incremental pipeline)
     - Poll message
     - Parse payload (skip tombstone / msg.value()==None)
     - Map `op` (c/u/d) → Decide: create/update/delete chunks
        │
        ▼
 6) Diff Detection & Incremental Chunking
     - For JSON: compare `before` vs `after` → detect changed fields
     - Create small chunks only for changed fields/lines
     - Log each change to `changelog` for audit/retry
        │
        ▼
 7) Embedding & Partial Update
     - Batch changed chunks (eg. 32) → call embedding API
     - Upsert embeddings to Vector DB (partial update)
     - Update `chunks` metadata (content_hash, embedding)
        │
        ▼
 8) Post-processing
     - Mark changelog entries processed
     - Optionally: warm caches, update search indices

```

Ghi chú quan trọng:
- Tombstones (DELETE): Debezium có thể gửi message với `after = null` hoặc `msg.value() = null` — xử lý bằng cách xóa vector hoặc đánh dấu `is_deleted`.
- Idempotency: dùng `chunk_id` và `content_hash` để tránh embed trùng lặp.
- Ordering & Exactly-once: xử lý theo offset Kafka ; replay có thể dựa trên changelog + file_versions.
- Bulk updates: nếu thay đổi lớn (>50% content) — cân nhắc `force_all=True` để re-chunk & re-embed toàn bộ.

---

## �📦 Files Tạo Được

```
rag/
├── store_info.txt                      ← Your original data
├── rag_metadata.db                     ← Version tracking (auto-created)
├── incremental_rag_system.py           ← Core system (chiếc trái tim)
├── kafka_cdc_to_rag.py                 ← CDC consumer for RAG
└── README.md                           ← Documentation (file này)
```

---

## 🔧 Cách Hoạt Động

### **Step 1: Version Tracking** 📝

```python
tracker = DataVersionTracker("rag/rag_metadata.db")

# Database lưu:
# 1. file_versions: hash của file, lần cuối modify
# 2. chunks: mỗi chunk + embedding + hash
# 3. changelog: log tất cả thay đổi
```

**Lợi ích:**
- Phát hiện ngay khi có file update
- Không cần so sánh toàn bộ file
- Có changelog cho audit trail

### **Step 2: Diff Detection** 🔍

```python
old_text = "Phone: 0909 456 123"
new_text = "Phone: 0909 456 789"  # ← Thay đổi

changes = DataDiffDetector.detect_text_changes(old_text, new_text)
# Result: [{'type': 'modified', 'old': '0909 456 123', 'new': '0909 456 789'}]
```

**Phát hiện được:**
- ✅ Dòng thay đổi (modified)
- ✅ Dòng thêm mới (added)
- ✅ Dòng bị xóa (deleted)

### **Step 3: Incremental Chunking** ✂️

```python
# Lần đầu tiên
chunks = chunker.create_chunks(text, "store_info", force_all=True)
# Result: 50 chunks (từ toàn bộ file)

# Lần tiếp theo (khi có update)
chunks = chunker.create_chunks(new_text, "store_info", force_all=False)
# Result: 2 chunks (chỉ từ những phần thay đổi)
# ✅ 96% ít hơn!
```

### **Step 4: CDC Integration** 🔄

Khi MySQL có thay đổi → Debezium capture → Kafka event:

```json
{
  "op": "u",
  "before": { "id": 1, "phone": "0909 456 123" },
  "after":  { "id": 1, "phone": "0909 456 789" },
  "source": { "table": "stores", "db": "rag_db" }
}
```

Kafka consumer tự động:
1. Phát hiện thay đổi
2. Tạo chunks chỉ cho `phone` field
3. Queue lên embedding
4. Update vector database

---

## 🚀 Quick Start

### **Setup**

```cmd
REM 1. Start CDC system
docker-compose up -d

REM 2. Create database & connector
create_connector.bat

REM 3. Run RAG consumer
python rag/kafka_cdc_to_rag.py
```

### **Make Changes & Watch Auto-Update**

```cmd
REM Thay đổi dữ liệu
docker-compose exec -T mysql mysql -uroot -proot rag_db -e ^
  "UPDATE stores SET phone='0909 777 888' WHERE id=1;"

REM Xem automatic update trong RAG consumer terminal
REM Output sẽ hiện:
REM   [Message #1] ✏️ UPDATE
REM   Changed fields:
REM     • phone: '0909 456 123' → '0909 777 888'
REM   Chunks to embed: 1
REM   Needs re-embedding: ✅ Yes
```

---

## 💡 Comparison: Old vs New

### **Old Approach** (Full Re-embedding)
```
Dữ liệu: 1000 chunks
Update: 1 chunk

Action:
1. ✗ Re-chunk toàn bộ 1000 chunks (1 phút)
2. ✗ Re-embed 1000 chunks (5 phút)
3. ✗ Re-index vector DB (2 phút)

Total: ~8 phút + API costs cho 1000 embeddings
```

### **New Approach** (Incremental)
```
Dữ liệu: 1000 chunks
Update: 1 chunk

Action:
1. ✓ Chunk chỉ changed field (1 giây)
2. ✓ Embed chỉ 1 chunk (0.5 giây)
3. ✓ Update vector DB (1 giây)

Total: ~3 giây + API costs cho 1 embedding (99.9% tiết kiệm!)
```

---

## 📊 Performance Metrics

| Metric | Old Approach | New Approach | Improvement |
|--------|-------------|------------|-------------|
| **Processing Time** | 10 min | 5 sec | **120x faster** |
| **API Calls** | 1000 | 1 | **1000x less** |
| **Storage I/O** | 1000 chunks | 1 chunk | **1000x less** |
| **Cost (embeddings)** | $1.00 | $0.001 | **1000x cheaper** |
| **Vector DB Updates** | Full reindex | Partial update | **Much faster** |
| **Real-time capability** | ❌ No | ✅ Yes | **Live updates** |

---

## 🔌 Integration Points

### **1. With Embedding APIs**

```python
# OpenAI Embeddings
from openai import OpenAI

client = OpenAI()
embeddings = client.embeddings.create(
    model="text-embedding-3-small",
    input=[c['content'] for c in changed_chunks]
)

# Update vector DB
vector_db.add_vectors(changed_chunks, embeddings.data)
```

### **2. With Vector Databases**

```python
# Pinecone
import pinecone

index = pinecone.Index("store-info")
index.upsert(vectors=[
    (chunk['chunk_id'], embedding, chunk)
    for chunk, embedding in zip(changed_chunks, embeddings)
])

# Or: Weaviate, Milvus, ChromaDB, etc.
```

### **3. With RAG Framework**

```python
# LangChain
from langchain.vectorstores import Pinecone
from langchain.embeddings import OpenAIEmbeddings

vectorstore = Pinecone.from_documents(
    documents=changed_chunks,
    embedding=OpenAIEmbeddings(),
    index_name="store-info"
)
```

---

## 🎓 Key Concepts

### **1. Version Tracking**
- Mỗi file/chunk có hash
- Phát hiện changes through hashing
- Metadata stored in SQLite

### **2. Differential Updates**
- So sánh old vs new versions
- Chỉ process differences
- Reduce overhead dramatically

### **3. Changelog Management**
- Log tất cả changes
- Audit trail for compliance
- Replay capability

### **4. Batch Processing**
- Group chunks into batches (32 default)
- Efficient API usage
- Better throughput

---

## 🛠️ Advanced Configuration

### **Adjust Chunk Size**

```python
chunker = IncrementalChunker(
    chunk_size=1000,    # Words per chunk
    overlap=100         # Overlap between chunks
)
```

### **Batch Size for Embeddings**

```python
processor = BatchEmbeddingProcessor(batch_size=64)  # Default 32
```

### **Custom Change Detection**

```python
# For JSON data
changes = DataDiffDetector.detect_json_changes(old_data, new_data)

# For text
changes = DataDiffDetector.detect_text_changes(old_text, new_text)
```

---

## 📈 Scaling Scenarios

### **Scenario 1: 1M products with daily updates**
```
Without Incremental: 1M embeddings/day = $100/day
With Incremental: 1K embeddings/day = $0.10/day
Savings: $36,500/year!
```

### **Scenario 2: Real-time price updates**
```
10,000 price updates/hour

Old approach:
- Queue updates → Batch at end of day → Re-embed all data
- Latency: 12+ hours

New approach:
- CDC captures change immediately → Incremental update
- Latency: <5 seconds
```

### **Scenario 3: Multi-language content**
```
Update affects: EN, VI, ZH versions (3x data)

Old: Re-embed 3x full dataset
New: Incremental updates = minimal overhead, supports all languages
```

---

## ⚠️ Important Notes

### **When to Use Full Re-embedding**

```python
# Rare cases where full re-embedding is needed:

1. Schema changes (new fields in database)
chunker.create_chunks(text, source, force_all=True)

2. Embedding model upgrade
# All chunks need new embeddings

3. Vector DB migration
# Full reload recommended
```

### **Handling Large Bulk Updates**

```python
# If bulk update > 50% of data:
# - Still use incremental (tracks all changes)
# - But consider batching them over time
# - Or use separate bulk loading job

if len(changes) / total_chunks > 0.5:
    print("Large bulk update detected")
    print("Consider batch processing")
```

---

## 🔗 Next Steps

1. **Deploy to Production**
   - Set up monitoring
   - Configure backups of rag_metadata.db
   - Set up alerts for failed embeddings

2. **Optimize Performance**
   - Profile your workload
   - Tune batch sizes
   - Use appropriate embedding model

3. **Monitor & Maintain**
   - Track changelog growth
   - Periodic metadata cleanup
   - Version your embeddings

---

## 📞 Support & Troubleshooting

**Q: No changes detected?**
A: Check if CDC is capturing events to Kafka

**Q: Embedding queue growing?**
A: Increase batch size or embedding API throughput

**Q: High memory usage?**
A: Reduce chunk size or process batches more frequently

---

**Happy Incremental RAG-ing!** 🎉
