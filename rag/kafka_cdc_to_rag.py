"""
Kafka CDC Consumer → Incremental RAG Embedding Pipeline
Lắng nghe thay đổi từ MySQL qua Kafka, tự động update embeddings
"""

from confluent_kafka import Consumer
import json
import time
from incremental_rag_system import CDCRAGIntegration, DataVersionTracker

# =============================================================================
# KAFKA CDC CONSUMER FOR RAG
# =============================================================================

class KafkaCDCToRAGConsumer:
    """
    Lắng nghe Kafka messages từ CDC events,
    tự động update Incremental RAG
    """
    
    def __init__(self, topic: str = "mysql-server.rag_db.stores"):
        self.conf = {
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'rag-consumer',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True
        }
        
        self.topic = topic
        self.consumer = Consumer(self.conf)
        self.consumer.subscribe([topic])
        
        self.rag_integration = CDCRAGIntegration()
        self.tracker = DataVersionTracker()
        
        self.embedding_queue = []  # Queue for chunks to embed
    
    def start(self, max_messages: int = None):
        """Bắt đầu lắng nghe Kafka"""
        
        print("=" * 80)
        print("CDC → Incremental RAG Pipeline")
        print("=" * 80)
        print(f"Listening on topic: {self.topic}")
        print("=" * 80)
        
        message_count = 0
        
        try:
            while True:
                msg = self.consumer.poll(1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    print(f"Consumer error: {msg.error()}")
                    continue
                
                message_count += 1
                
                # Parse CDC event
                try:
                    cdc_event = json.loads(msg.value())
                    payload = cdc_event.get('payload', {})
                    
                    # Process event through Incremental RAG
                    result = self.rag_integration.process_cdc_event(payload)
                    
                    # Display results
                    self._display_event(message_count, result, payload)
                    
                    # Queue chunks for embedding
                    if result['needs_reembedding']:
                        self.embedding_queue.extend(result['chunks_to_update'])
                    
                    # Display embedding queue status
                    self._display_embedding_queue()
                    
                except json.JSONDecodeError as e:
                    print(f"[Error] Invalid JSON: {e}")
                    continue
                
                if max_messages and message_count >= max_messages:
                    break
        
        except KeyboardInterrupt:
            print("\n[Info] Consumer stopped by user")
        finally:
            self.consumer.close()
    
    def _display_event(self, count: int, result: dict, payload: dict):
        """Hiển thị thông tin CDC event"""
        
        op_map = {
            'c': '➕ CREATE',
            'u': '✏️ UPDATE',
            'd': '🗑️ DELETE'
        }
        
        op = payload.get('op', 'unknown')
        table = result.get('table', 'unknown')
        
        print(f"\n[Message #{count}] {op_map.get(op, op)}")
        print(f"  Table: {table}")
        print(f"  Changes: {len(result.get('changes', []))}")
        
        if result['changes']:
            print("  Changed fields:")
            for change in result['changes']:
                field = change.get('field', 'unknown')
                old_val = change.get('old', 'N/A')
                new_val = change.get('new', 'N/A')
                print(f"    • {field}: '{old_val}' → '{new_val}'")
        
        print(f"  Chunks to embed: {len(result.get('chunks_to_update', []))}")
        print(f"  Needs re-embedding: {'✅ Yes' if result['needs_reembedding'] else '❌ No'}")
    
    def _display_embedding_queue(self):
        """Hiển thị queue chờ embedding"""
        
        if self.embedding_queue:
            print(f"\n  ⏳ Embedding Queue: {len(self.embedding_queue)} chunks waiting")
            print(f"     (Typically embed in batches of 32)")
            
            # Simulate batch embedding
            if len(self.embedding_queue) >= 32:
                self._process_embedding_batch(32)
    
    def _process_embedding_batch(self, batch_size: int):
        """Xử lý embedding cho một batch"""
        
        chunks = self.embedding_queue[:batch_size]
        self.embedding_queue = self.embedding_queue[batch_size:]
        
        print(f"\n  🚀 Processing embedding batch ({len(chunks)} chunks)...")
        print(f"     (In production: send to embedding API - OpenAI, Cohere, local model)")
        
        # TODO: Thay bằng real embedding API
        # embeddings = embedding_model.embed_documents([c['content'] for c in chunks])
        # vector_db.add_vectors(chunks, embeddings)
        
        print(f"     ✅ Embedded {len(chunks)} chunks")
    
    def get_unprocessed_changes_stats(self):
        """Lấy thống kê thay đổi chưa xử lý"""
        
        changes = self.tracker.get_unprocessed_changes()
        
        print("\n" + "=" * 80)
        print("UNPROCESSED CHANGES STATISTICS")
        print("=" * 80)
        
        if not changes:
            print("✅ All changes have been processed!")
            return
        
        # Thống kê theo loại
        change_types = {}
        for change in changes:
            change_type = change['change_type']
            change_types[change_type] = change_types.get(change_type, 0) + 1
        
        print(f"Total unprocessed: {len(changes)}")
        print("\nBreakdown by type:")
        for change_type, count in change_types.items():
            print(f"  • {change_type}: {count}")
        
        # Nguồn thay đổi
        sources = {}
        for change in changes:
            source = change['source']
            sources[source] = sources.get(source, 0) + 1
        
        print("\nBreakdown by source:")
        for source, count in sources.items():
            print(f"  • {source}: {count}")


# =============================================================================
# BATCH EMBEDDING PROCESSOR
# =============================================================================

class BatchEmbeddingProcessor:
    """
    Xử lý embedding chunks theo batch
    Tích hợp với embedding APIs
    """
    
    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self.embedding_queue = []
    
    def add_chunks(self, chunks: list):
        """Thêm chunks vào queue"""
        self.embedding_queue.extend(chunks)
        
        # Process khi đủ batch size
        if len(self.embedding_queue) >= self.batch_size:
            self.process_batch()
    
    def process_batch(self):
        """Xử lý một batch"""
        
        if not self.embedding_queue:
            return
        
        batch = self.embedding_queue[:self.batch_size]
        self.embedding_queue = self.embedding_queue[self.batch_size:]
        
        # TODO: Integrate với embedding API
        # Ví dụ:
        # from openai import OpenAI
        # client = OpenAI()
        # embeddings = client.embeddings.create(
        #     model="text-embedding-3-small",
        #     input=[c['content'] for c in batch]
        # )
        
        print(f"[Batch Processing] Embedded {len(batch)} chunks")
        
        # Update vector database
        # vector_db.add_vectors(batch, embeddings.data)


# =============================================================================
# MAIN - START LISTENING
# =============================================================================

def main():
    """Main entry point"""
    
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                  CDC → INCREMENTAL RAG PIPELINE                            ║
║                                                                            ║
║  This consumer listens to Kafka CDC events and automatically updates       ║
║  RAG embeddings for changed data ONLY (not the entire dataset)             ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Tạo consumer
    consumer = KafkaCDCToRAGConsumer(topic="mysql-server.rag_db.stores")
    
    # Bắt đầu lắng nghe
    try:
        consumer.start()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Hiển thị stats
        consumer.get_unprocessed_changes_stats()


if __name__ == "__main__":
    main()
