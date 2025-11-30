# -*- coding: utf-8 -*-
from confluent_kafka import Consumer
import json
import os
import dotenv
from pinecone import Pinecone
import requests
import difflib

dotenv.load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "store-knowledge")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = PINECONE_INDEX_NAME
index = pc.Index(index_name)
print(f"🌲 Pinecone index đã sẵn sàng: {index_name}")

conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'demo-consumer',
    'auto.offset.reset': 'earliest'
}
consumer = Consumer(conf)
consumer.subscribe(['mysql-server.testdb.rag'])


# -------------------------------------------------------------
# 📌 HÀM TRÍCH XUẤT THÔNG TIN CHÍNH
# -------------------------------------------------------------
def extract_info(message):
    payload = message.get("payload", {})

    # 1. Operation: c/u/d/r
    op = payload.get("op")

    # 2. Database & Table
    db = payload.get("source", {}).get("db")
    table = payload.get("source", {}).get("table")

    # 3. Lấy dữ liệu after (hoặc before nếu delete)
    after = payload.get("after", {})
    before = payload.get("before", {})

    record = after if after else before
    record_id = record.get("id")

    # 4. Parse metadata JSON string
    metadata_raw = record.get("metadata")
    metadata = {}
    category = None

    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
            category = metadata.get("category")
        except Exception as e:
            print("⚠️ Metadata không phải JSON hợp lệ:", e)

    return {
        "op": op,
        "db": db,
        "table": table,
        "id": record_id,
        "metadata": metadata,
        "category": category,
        "record": record
    }


# -------------------------------------------------------------
# 📌 API CALLS
# -------------------------------------------------------------
def call_chunking_embedding_api(table_name: str, doc_id: int):
    """Call API to chunk and embed document, then add to Pinecone"""
    try:
        url = f"{API_BASE_URL}/api/v1/document/{table_name}/{doc_id}/chunkingEmbPinecone"
        
        print(f"🔗 Calling: POST {url}")
        
        response = requests.post(
            url,
            timeout=300  # 5 minutes timeout for embedding
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Chunking & Embedding successful!")
            print(f"   Summary: {result.get('result', {}).get('summary', {})}")
            return True
        else:
            print(f"❌ API Error: Status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    except requests.exceptions.Timeout:
        print(f"❌ API Timeout: Request took too long")
        return False
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return False


def call_delete_by_category_api(category: str):
    """Call API to delete all vectors by category"""
    try:
        url = f"{API_BASE_URL}/api/v1/pinecone/delete/category/{category}"
        
        print(f"🔗 Calling: DELETE {url}")
        
        response = requests.delete(
            url,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            deleted_count = result.get('result', {}).get('deleted_count', 0)
            print(f"✅ Delete successful!")
            print(f"   Deleted {deleted_count} vectors for category '{category}'")
            return True
        else:
            print(f"❌ API Error: Status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return False


# -------------------------------------------------------------
# 📌 MAIN LOOP
# -------------------------------------------------------------
message_count = 0
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Consumer error:", msg.error())
        continue

    message_count += 1

    if msg.value() is None:
        print(f"[Message #{message_count}] ⚠️ Empty (tombstone)")
        continue

    raw = json.loads(msg.value())

    # ---- Extract thông tin cần thiết ----
    info = extract_info(raw)

    print(f"\n📌 Message #{message_count} Extracted Info:")
    print(json.dumps(info, indent=4, ensure_ascii=False))

    op = info["op"]

    # -------------------------------------------------------------
    # 📌 XỬ LÝ THEO TỪNG OP
    # -------------------------------------------------------------
    if op == "c":
        print(f"➕ INSERT db={info['db']} table={info['table']} row id={info['id']} (category={info['category']})")
        
        # Call API to chunk, embed and add to Pinecone
        table_name = info['table']
        doc_id = info['id']
        print(f"📤 Calling chunking & embedding API for doc_id={doc_id}...")
        call_chunking_embedding_api(table_name, doc_id)
    
    elif op == "u":
        print(f"♻ UPDATE db={info['db']} table={info['table']} row id={info['id']} (category={info['category']})")
        
        # Get update information
        table_name = info['table']
        doc_id = info['id']
        category = info['category']
        
        if category:
            # Step 1: Delete all vectors by category
            print(f"🗑️  Deleting old vectors for category '{category}'...")
            call_delete_by_category_api(category)
            
            # Step 2: Re-chunk and re-embed the updated document
            print(f"📤 Re-chunking and re-embedding document for doc_id={doc_id}...")
            call_chunking_embedding_api(table_name, doc_id)
        else:
            print(f"⚠️ No category found, skipping update")
    
    elif op == "d":
        print(f"❌ DELETE db={info['db']} table={info['table']} row id={info['id']} (category={info['category']})")
        
        # Call API to delete vectors by category
        category = info['category']
        if category:
            print(f"🗑️  Calling delete API for category='{category}'...")
            call_delete_by_category_api(category)
        else:
            print(f"⚠️ No category found, skipping delete")
    
    elif op == "r":
        print(f"📄 SNAPSHOT db={info['db']} table={info['table']} row id={info['id']}")
    
    else:
        print("⚠️ OP không xác định:", op)
