from confluent_kafka import Consumer
import json

conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'demo-consumer',
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(conf)
consumer.subscribe(['mysql-server.testdb.users'])

print("=" * 80)
print("CDC DEMO - Kafka Consumer")
print("=" * 80)

message_count = 0
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Consumer error: {}".format(msg.error()))
        continue

    message_count += 1
    
    # Handle None value
    if msg.value() is None:
        print(f"\n[Message #{message_count}] ⚠️ Empty message (tombstone record)")
        continue
    
    payload = json.loads(msg.value())
    payload = payload.get('payload', {})

    op = payload.get('op')
    before = payload.get('before')
    after  = payload.get('after')
    source = payload.get('source', {})

    op_map = {
        'c': '➕ CREATE (INSERT)',
        'r': '📖 READ (Snapshot)',
        'u': '✏️ UPDATE',
        'd': '🗑️ DELETE',
    }

    print(f"\n[Message #{message_count}] {op_map.get(op)}")
    print(f"  Table: {source.get('table')}")
    print(f"  Database: {source.get('db')}")
    print(f"  File: {source.get('file')}, Pos: {source.get('pos')}")

    if op in ['c', 'r']:
        print("  ➜ After:", after)
    elif op == 'u':
        print("  ➜ Before:", before)
