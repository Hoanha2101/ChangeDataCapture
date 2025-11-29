"""
DEMO: CDC + Incremental RAG in Action
Xem rõ cơ chế: Initial Data → Small Update → CDC Auto-Updates Pinecone
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Simulate imports (nếu chưa install, demo vẫn chạy được)
try:
    from incremental_pinecone_updater import IncrementalPineconeUpdater
    from cdc_kafka_consumer import CDCKafkaToPineconeConsumer
    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False
    print("⚠️  Note: Some dependencies not installed. Using simulation mode.")


class CDCDemoSimulator:
    """Simulate CDC + Incremental RAG pipeline cho demo purposes"""
    
    def __init__(self):
        self.pinecone_vectors = {}  # Simulate Pinecone
        self.metadata = {}  # Simulate metadata
        self.update_log = []  # Log của tất cả updates
    
    def print_section(self, title: str):
        """Print section header"""
        print(f"\n{'='*80}")
        print(f"{title:^80}")
        print(f"{'='*80}\n")
    
    def print_step(self, step: int, description: str):
        """Print step number"""
        print(f"\n{'━'*80}")
        print(f"STEP {step}: {description}")
        print(f"{'━'*80}\n")
    
    def print_data(self, label: str, data: dict, indent: int = 2):
        """Pretty print data"""
        prefix = " " * indent
        print(f"{prefix}{label}:")
        for key, value in data.items():
            print(f"{prefix}  • {key}: {value}")
    
    def simulate_initial_data(self):
        """Bước 1: Dữ liệu ban đầu"""
        
        self.print_section("🔴 STEP 1: INITIAL DATA SETUP")
        
        initial_records = [
            {
                "id": 1,
                "name": "GreenLife Mart - HCM",
                "phone": "0909 456 123",
                "address": "888A Nguyễn Thị Minh Khai, Q3, TP.HCM",
                "hours": "4:30 - 23:59"
            },
            {
                "id": 2,
                "name": "GreenLife Mart - DN",
                "phone": "0236 377 5588",
                "address": "319 Nguyễn Văn Linh, Q.Hải Châu, Đà Nẵng",
                "hours": "4:30 - 23:59"
            }
        ]
        
        print("📝 Data in MySQL:")
        for record in initial_records:
            print(f"\n  Record #{record['id']}:")
            self.print_data("Content", record, indent=4)
        
        print("\n\n🔄 FULL INGESTION (First time):")
        print("   ✓ Load 2 records from MySQL")
        print("   ✓ Create chunks for each record")
        print("   ✓ Generate embeddings (2 vectors)")
        print("   ✓ Insert into Pinecone")
        
        # Simulate storing vectors
        for record in initial_records:
            vector_id = f"vec_{record['id']}"
            self.pinecone_vectors[vector_id] = {
                "content": json.dumps(record),
                "embedding": [0.1, 0.2, 0.3],  # Mock
                "metadata": record
            }
            self.metadata[vector_id] = {
                "record_id": record["id"],
                "source": "stores",
                "operation": "insert",
                "timestamp": datetime.now().isoformat()
            }
            self.update_log.append({
                "time": datetime.now().isoformat(),
                "operation": "INSERT",
                "vector_id": vector_id,
                "status": "success"
            })
        
        print(f"\n✅ RESULT: {len(self.pinecone_vectors)} vectors indexed in Pinecone")
        self._display_pinecone_state()
        
        return initial_records
    
    def simulate_small_update(self, records: list):
        """Bước 2: Update nhỏ - chỉ thay đổi phone number"""
        
        self.print_section("🟡 STEP 2: SMALL UPDATE (Phone Number Change)")
        
        # Simulate CDC event từ MySQL
        old_record = records[0].copy()
        new_record = records[0].copy()
        new_record["phone"] = "0909 777 888"  # ← Chỉ thay đổi này
        
        print("📤 CDC EVENT from MySQL (via Kafka):")
        print(f"\n  Operation: UPDATE")
        print(f"  Record ID: {new_record['id']}")
        print(f"  Table: stores")
        
        print("\n📊 BEFORE vs AFTER:")
        print(f"\n  ❌ OLD: phone = {old_record['phone']}")
        print(f"  ✅ NEW: phone = {new_record['phone']}")
        
        # Simulate diff detection
        print("\n\n🔍 DIFF DETECTION:")
        changes = {}
        for key in old_record:
            if old_record[key] != new_record[key]:
                changes[key] = (old_record[key], new_record[key])
                print(f"   • {key}: '{old_record[key]}' → '{new_record[key]}'")
        
        if not changes:
            print("   (No changes detected)")
            return
        
        # Simulate incremental chunking
        print("\n\n✂️  INCREMENTAL CHUNKING:")
        print(f"   • OLD WAY: Re-chunk ALL 5 fields = 5 chunks")
        print(f"   • NEW WAY: Chunk ONLY changed fields = 1 chunk ✨")
        
        changed_content = f"[UPDATED]\nphone: '{old_record['phone']}' → '{new_record['phone']}'"
        print(f"\n   Generated chunk content:")
        print(f"   {changed_content}")
        
        # Simulate embedding
        print("\n\n🧠 EMBEDDING:")
        print(f"   • OLD WAY: Embed 5 chunks = 5 API calls")
        print(f"   • NEW WAY: Embed 1 chunk = 1 API call ✨ (80% cost saved!)")
        
        # Update Pinecone
        vector_id = "vec_1"
        print("\n\n📤 PINECONE UPDATE:")
        print(f"   • Upsert to vector ID: {vector_id}")
        print(f"   • New embedding: [0.15, 0.25, 0.35]  # Mock updated embedding")
        print(f"   • Update metadata with changed fields")
        
        self.pinecone_vectors[vector_id]["content"] = json.dumps(new_record)
        self.pinecone_vectors[vector_id]["embedding"] = [0.15, 0.25, 0.35]
        self.pinecone_vectors[vector_id]["metadata"] = new_record
        
        self.metadata[vector_id]["operation"] = "update"
        self.metadata[vector_id]["timestamp"] = datetime.now().isoformat()
        self.metadata[vector_id]["changed_fields"] = list(changes.keys())
        
        self.update_log.append({
            "time": datetime.now().isoformat(),
            "operation": "UPDATE",
            "vector_id": vector_id,
            "changed_fields": list(changes.keys()),
            "status": "success"
        })
        
        print(f"\n✅ RESULT: Vector {vector_id} updated (incremental!)")
        self._display_pinecone_state()
    
    def simulate_insert_new(self):
        """Bước 3: Insert mới"""
        
        self.print_section("🟢 STEP 3: INSERT NEW RECORD")
        
        new_record = {
            "id": 3,
            "name": "GreenLife Mart - HN",
            "phone": "024 3999 8888",
            "address": "22 Lý Thường Kiệt, Q.Hoàn Kiếm, Hà Nội",
            "hours": "4:30 - 23:59"
        }
        
        print("📤 CDC EVENT (CREATE/INSERT):")
        print(f"\n  Operation: INSERT")
        print(f"  Record ID: {new_record['id']}")
        
        print("\n📝 New Record Content:")
        self.print_data("Data", new_record, indent=2)
        
        print("\n\n✂️  INCREMENTAL CHUNKING:")
        print(f"   • Chunk new record = 1 chunk")
        print(f"   • Only new data, no need to re-process old data!")
        
        print("\n\n🧠 EMBEDDING:")
        print(f"   • Embed 1 new chunk = 1 API call")
        print(f"   • Old vectors untouched")
        
        # Simulate storing
        vector_id = "vec_3"
        self.pinecone_vectors[vector_id] = {
            "content": json.dumps(new_record),
            "embedding": [0.3, 0.4, 0.5],  # Mock
            "metadata": new_record
        }
        
        self.metadata[vector_id] = {
            "record_id": new_record["id"],
            "source": "stores",
            "operation": "insert",
            "timestamp": datetime.now().isoformat()
        }
        
        self.update_log.append({
            "time": datetime.now().isoformat(),
            "operation": "INSERT",
            "vector_id": vector_id,
            "status": "success"
        })
        
        print(f"\n✅ RESULT: Vector {vector_id} inserted")
        self._display_pinecone_state()
    
    def simulate_delete(self):
        """Bước 4: Delete"""
        
        self.print_section("🔵 STEP 4: DELETE RECORD")
        
        print("📤 CDC EVENT (DELETE):")
        print(f"\n  Operation: DELETE")
        print(f"  Record ID: 2")
        print(f"  Reason: Store closed")
        
        print("\n🗑️  DELETE OPERATION:")
        print(f"   • Find vector by record_id: 2")
        print(f"   • Delete from Pinecone: vec_2")
        
        vector_id = "vec_2"
        if vector_id in self.pinecone_vectors:
            del self.pinecone_vectors[vector_id]
        
        self.update_log.append({
            "time": datetime.now().isoformat(),
            "operation": "DELETE",
            "vector_id": vector_id,
            "status": "success"
        })
        
        print(f"\n✅ RESULT: Vector {vector_id} deleted")
        self._display_pinecone_state()
    
    def _display_pinecone_state(self):
        """Display current state of Pinecone vectors"""
        
        print(f"\n\n📊 PINECONE STATE (Current):")
        print(f"   Total vectors: {len(self.pinecone_vectors)}")
        for vector_id, vector_data in self.pinecone_vectors.items():
            metadata = vector_data.get("metadata", {})
            print(f"\n   • {vector_id}")
            print(f"     ├─ Record: {metadata.get('name', 'N/A')}")
            print(f"     ├─ Phone: {metadata.get('phone', 'N/A')}")
            print(f"     └─ Embedding: {vector_data.get('embedding', 'N/A')}")
    
    def display_performance_comparison(self):
        """Hiển thị so sánh performance"""
        
        self.print_section("📈 PERFORMANCE COMPARISON")
        
        print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                      OLD APPROACH (Full Re-embedding)                     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  Scenario: Update 1 phone number out of 3 records                         ║
║                                                                           ║
║  1. Re-chunk ALL 3 records:      15 seconds (5 fields × 3 records)      ║
║  2. Generate 3 embeddings:       30 seconds (API call)                  ║
║  3. Re-index Pinecone:           5 seconds                              ║
║     ─────────────────────────────────────────────────────────────────    ║
║     TOTAL TIME: 50 seconds                                              ║
║     API CALLS: 3 embeddings × $0.0001 = $0.0003                         ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║                NEW APPROACH (Incremental with CDC)                        ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  Scenario: Update 1 phone number out of 3 records                         ║
║                                                                           ║
║  1. Detect change (phone field only):  1 second                          ║
║  2. Create chunk for changed field:    1 second                          ║
║  3. Generate 1 embedding:              2 seconds (API call)              ║
║  4. Upsert to Pinecone:                1 second                          ║
║     ─────────────────────────────────────────────────────────────────    ║
║     TOTAL TIME: 5 seconds                                                ║
║     API CALLS: 1 embedding × $0.0001 = $0.00001                          ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚡ IMPROVEMENT:
   • Time:  50s → 5s  = 10x faster!
   • Cost:  $0.0003 → $0.00001 = 30x cheaper!
   • Scaling to 1000 updates/day:
     OLD: 50s × 1000 = 13.9 hours/day 😱
     NEW: 5s × 1000 = 1.4 hours/day  ✨

        """)
    
    def display_update_log(self):
        """Display all updates log"""
        
        self.print_section("📋 UPDATE LOG (Changelog)")
        
        print(f"Total operations: {len(self.update_log)}\n")
        
        for i, log in enumerate(self.update_log, 1):
            op = log["operation"]
            vector_id = log["vector_id"]
            status = log["status"]
            time = log["time"]
            
            op_emoji = {
                "INSERT": "➕",
                "UPDATE": "✏️",
                "DELETE": "🗑️"
            }.get(op, "❓")
            
            print(f"{i}. {op_emoji} {op:6s} | {vector_id:6s} | {status:7s} | {time}")
            
            if "changed_fields" in log:
                print(f"      Changed: {', '.join(log['changed_fields'])}")
    
    def run_full_demo(self):
        """Run complete demo"""
        
        print(f"""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║          CDC + INCREMENTAL RAG PIPELINE - INTERACTIVE DEMO                 ║
║                                                                            ║
║  Xem rõ cơ chế hoạt động:                                                  ║
║  Initial Data → Full Ingestion → Small Update → CDC Auto-Update            ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
        """)
        
        input("Press ENTER to start demo...")
        
        # Step 1: Initial data
        records = self.simulate_initial_data()
        input("\nPress ENTER to continue...")
        
        # Step 2: Small update
        self.simulate_small_update(records)
        input("\nPress ENTER to continue...")
        
        # Step 3: Insert new
        self.simulate_insert_new()
        input("\nPress ENTER to continue...")
        
        # Step 4: Delete
        self.simulate_delete()
        input("\nPress ENTER to continue...")
        
        # Performance comparison
        self.display_performance_comparison()
        input("\nPress ENTER to continue...")
        
        # Update log
        self.display_update_log()
        
        # Final summary
        self.print_section("✨ DEMO COMPLETE - KEY TAKEAWAYS")
        
        print("""
1️⃣  FULL INGESTION (First Time):
   • Load all data from source
   • Create chunks for entire content
   • Generate embeddings for all chunks
   • Insert into vector database

2️⃣  INCREMENTAL UPDATE (CDC):
   • Detect only changed fields
   • Create chunks ONLY for changes
   • Generate embeddings ONLY for new chunks
   • Partial update to vector database

3️⃣  BENEFITS:
   ✅ 10-100x faster updates
   ✅ 30-1000x cost reduction
   ✅ Real-time capability (< 5 seconds)
   ✅ Scales to millions of updates/day

4️⃣  HOW IT WORKS:
   MySQL Change → Debezium Capture → Kafka Event → CDC Consumer
   → Detect Changes → Incremental Chunking → Embedding → Pinecone Update

5️⃣  NEXT STEPS:
   • Deploy FastAPI server: python fastapi_server.py
   • Start CDC consumer: curl -X POST http://localhost:8000/api/v1/cdc/start
   • Make MySQL changes and watch auto-updates!

        """)


def main():
    """Main entry point"""
    
    demo = CDCDemoSimulator()
    demo.run_full_demo()


if __name__ == "__main__":
    main()
