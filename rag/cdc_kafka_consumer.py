"""
CDC Kafka Consumer → Pinecone Incremental Update Pipeline
Lắng nghe CDC events từ Kafka và tự động update Pinecone
"""

import os
import json
import asyncio
from typing import Optional
from datetime import datetime
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv
import threading
from typing import Dict

from incremental_pinecone_updater import IncrementalPineconeUpdater

load_dotenv()


class CDCKafkaToPineconeConsumer:
    """
    Consumer lắng nghe Kafka CDC events và update Pinecone incrementally
    Chạy trong background thread
    """
    
    def __init__(self, 
                 kafka_topic: str = "mysql-server.rag_db.stores",
                 pinecone_index: str = "store-knowledge"):
        """
        Args:
            kafka_topic: Kafka topic để lắng nghe (format: mysql-server.{db}.{table})
            pinecone_index: Pinecone index name
        """
        
        # Kafka consumer config
        self.kafka_config = {
            'bootstrap.servers': os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            'group.id': os.getenv("KAFKA_GROUP_ID", "pinecone-rag-consumer"),
            'auto.offset.reset': 'latest',  # Chỉ xử lý messages mới
            'enable.auto.commit': True,
            'session.timeout.ms': 6000
        }
        
        self.kafka_topic = kafka_topic
        self.consumer = Consumer(self.kafka_config)
        self.consumer.subscribe([kafka_topic])
        
        # Pinecone updater
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.updater = IncrementalPineconeUpdater(pinecone_api_key, pinecone_index)
        
        # Running state
        self.is_running = False
        self.consumer_thread = None
        
        # Stats
        self.stats = {
            "total_messages": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "skipped_updates": 0,
            "start_time": None,
            "last_message_time": None
        }
    
    def start(self):
        """Bắt đầu consumer trong background thread"""
        if self.is_running:
            return {"status": "already_running"}
        
        self.is_running = True
        self.stats["start_time"] = datetime.now().isoformat()
        
        self.consumer_thread = threading.Thread(
            target=self._consume_loop,
            daemon=True
        )
        self.consumer_thread.start()
        
        return {
            "status": "started",
            "topic": self.kafka_topic,
            "message": f"CDC Consumer started, listening to {self.kafka_topic}"
        }
    
    def stop(self):
        """Dừng consumer"""
        if not self.is_running:
            return {"status": "not_running"}
        
        self.is_running = False
        self.consumer.close()
        
        return {
            "status": "stopped",
            "message": "CDC Consumer stopped"
        }
    
    def _consume_loop(self):
        """Main loop để poll messages từ Kafka"""
        
        print(f"[CDC Consumer] Bắt đầu lắng nghe {self.kafka_topic}...")
        
        while self.is_running:
            try:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f"[CDC Consumer] Kafka error: {msg.error()}")
                        continue
                
                # Parse CDC event
                self._process_message(msg)
                
            except Exception as e:
                print(f"[CDC Consumer] Error in consume loop: {e}")
                continue
    
    def _process_message(self, msg):
        """Xử lý một Kafka message"""
        
        self.stats["total_messages"] += 1
        self.stats["last_message_time"] = datetime.now().isoformat()
        
        try:
            # Parse JSON payload
            if msg.value() is None:
                # Tombstone (delete marker) - bỏ qua
                print(f"[CDC] Received tombstone message (skip)")
                self.stats["skipped_updates"] += 1
                return
            
            cdc_event = json.loads(msg.value())
            payload = cdc_event.get("payload", {})
            
            # Process through incremental updater
            result = self.updater.process_cdc_event(payload)
            
            # Update stats
            if result["status"] == "success":
                self.stats["successful_updates"] += 1
                print(f"[CDC ✓] {result['operation'].upper()} | {result['table']} | {result['message']}")
            elif result["status"] == "skipped":
                self.stats["skipped_updates"] += 1
                print(f"[CDC ~] SKIPPED | {result['table']} | {result['message']}")
            else:
                self.stats["failed_updates"] += 1
                print(f"[CDC ✗] ERROR | {result['table']} | {result['message']}")
        
        except json.JSONDecodeError as e:
            print(f"[CDC ✗] JSON decode error: {e}")
            self.stats["failed_updates"] += 1
        except Exception as e:
            print(f"[CDC ✗] Processing error: {e}")
            self.stats["failed_updates"] += 1
    
    def get_status(self) -> Dict:
        """Lấy status hiện tại"""
        
        uptime_seconds = 0
        if self.stats["start_time"]:
            start = datetime.fromisoformat(self.stats["start_time"])
            uptime_seconds = (datetime.now() - start).total_seconds()
        
        return {
            "is_running": self.is_running,
            "topic": self.kafka_topic,
            "uptime_seconds": uptime_seconds,
            "stats": self.stats,
            "pinecone_stats": self.updater.get_update_stats()
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            "total_messages": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "skipped_updates": 0,
            "start_time": self.stats["start_time"],
            "last_message_time": None
        }
        return {"status": "stats_reset"}


# Global instance
_global_consumer: Optional[CDCKafkaToPineconeConsumer] = None


def get_consumer() -> CDCKafkaToPineconeConsumer:
    """Get or create global consumer instance"""
    global _global_consumer
    
    if _global_consumer is None:
        _global_consumer = CDCKafkaToPineconeConsumer(
            kafka_topic=os.getenv("KAFKA_CDC_TOPIC", "mysql-server.rag_db.stores"),
            pinecone_index=os.getenv("PINECONE_INDEX_NAME", "store-knowledge")
        )
    
    return _global_consumer
