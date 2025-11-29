# Change Data Capture (CDC) Demo - Debezium & Kafka

## 📋 Giới thiệu

Đây là một demo về **Change Data Capture (CDC)** - công nghệ bắt lấy những thay đổi dữ liệu từ cơ sở dữ liệu MySQL và phát đi qua Kafka. Bất cứ ứng dụng nào kết nối với Kafka đều có thể nhận được các thay đổi này gần như trong thời gian thực.

---

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                    CHANGE DATA CAPTURE DEMO                 │
└─────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │   MySQL DB   │
                          │   (Source)   │
                          └──────┬───────┘
                                 │
                    (Binary Logs) │ (ROW format)
                                 │
                          ┌──────▼───────┐
                          │  Debezium    │
                          │  Connector   │
                          │  (CDC Agent) │
                          └──────┬───────┘
                                 │
                    (Change Events) │
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
         ┌──────────▼──┐  ┌──────▼───────┐   │
         │   Zookeeper │  │    Kafka     │   │
         │  (Quorum)   │  │ (Message Bus)│   │
         └─────────────┘  └──────┬───────┘   │
                                 │           │
                    ┌────────────┴─────────┐ │
                    │                      │ │
          ┌─────────▼──────┐    ┌──────────▼─┐
          │   Kafka Topics │    │ Kafka-UI   │
          │   (Messages)   │    │(Dashboard) │
          └────────────────┘    └────────────┘
```

---

## 🔧 Các thành phần chính & Khái niệm Kafka

### 🎓 Khái niệm cơ bản

#### **Broker** (Máy chủ Kafka)
Là một **server Kafka** lưu trữ và phục vụ messages. Trong hệ thống CDC của bạn:
- Có **1 broker** (container `kafka`)
- Broker này quản lý tất cả topics và messages
- Nó lưu trữ dữ liệu thay đổi từ Debezium
- Producers (Debezium) gửi messages đến broker
- Consumers (apps) đọc messages từ broker

```
[MySQL] → [Debezium/Producer] → [Broker] → [Consumers/Apps]
                                  ↑
                            Lưu & phục vụ
```

#### **Topic** (Chủ đề/Danh mục)
Là một **danh mục để nhóm messages** theo loại dữ liệu. Ví dụ:
- `mysql-server.testdb.users` ← Topic chứa thay đổi bảng users
- `mysql-server.testdb.products` ← Topic chứa thay đổi bảng products
- `connect-configs` ← Topic cấu hình của Debezium

Mỗi topic có nhiều messages, mỗi message là một sự kiện (INSERT, UPDATE, DELETE).

```
Topic: mysql-server.testdb.users
  ├─ Message 1: {"op":"c", "after":{"id":1, "name":"Alice"}}  (INSERT)
  ├─ Message 2: {"op":"u", "after":{"id":1, "name":"Bob"}}    (UPDATE)
  └─ Message 3: {"op":"d", "before":{"id":1}}                 (DELETE)
```

#### **Consumer** (Người tiêu thụ/Ứng dụng)
Là một **ứng dụng/service đọc messages từ topics**. Ví dụ:
- App sync dữ liệu từ MySQL → Elasticsearch
- App gửi email khi có thay đổi
- App cập nhật cache Redis
- App ghi audit log

**Quan trọng:** Nhiều consumers có thể đọc cùng một topic mà không ảnh hưởng đến nhau!

```
Topic: mysql-server.testdb.users
            ⬇️
    Consumer 1: Elasticsearch sync
    Consumer 2: Email notification
    Consumer 3: Redis cache update
    Consumer 4: Audit logging
```

#### **Offset** (Vị trí đọc)
Là **vị trí hiện tại** của consumer trong topic:
- Consumer 1 đã đọc đến message 1000
- Consumer 2 đã đọc đến message 500
- Khi consumer tắt/bật lại, nó sẽ tiếp tục từ offset đã lưu (không bị mất message)

---

### 1️⃣ **MySQL Database** (Nguồn dữ liệu)
- **Cổng**: 3306
- **Tài khoản**: root / root
- **Vai trò**: Cơ sở dữ liệu gốc cần bắt lấy thay đổi
- **Cấu hình quan trọng**:
  - `log-bin=mysql-bin`: Bật Binary Logging
  - `binlog_format=ROW`: Ghi lại chi tiết từng dòng thay đổi
  - `binlog_row_image=FULL`: Ghi cả giá trị cũ và mới

**Công dụng**: Lưu trữ dữ liệu và tạo nhật ký nhị phân (binary logs) để Debezium có thể theo dõi các thay đổi.

---

### 2️⃣ **Zookeeper** (Quản lý phối hợp - Rất quan trọng!)
- **Cổng**: 2181
- **Vai trò**: Quản lý trạng thái và phối hợp giữa các broker Kafka

#### Zookeeper làm gì?

**1. Bầu chọn Leader (Leader Election)**
- Khi cụm Kafka có nhiều brokers, Zookeeper bầu chọn broker nào là LEADER
- LEADER quản lý toàn bộ, các broker khác là FOLLOWERS
- Nếu LEADER xảy ra sự cố, Zookeeper tự động bầu LEADER mới
- Đảm bảo không có 2 LEADERs cùng lúc (gọi là "Split Brain")

```
Trước khi xảy ra sự cố:
  Broker 1 (LEADER) ← Zookeeper bầu chọn
  Broker 2 (FOLLOWER)
  Broker 3 (FOLLOWER)

Broker 1 bị sự cố (offline):
  Zookeeper phát hiện → bầu chọn Broker 2 hoặc 3 làm LEADER mới
  Broker 2 (LEADER) ← Tự động promote lên
  Broker 3 (FOLLOWER)
```

**2. Lưu trữ Metadata (Thông tin hệ thống)**
Zookeeper lưu trữ tất cả thông tin quan trọng:
- Danh sách tất cả topics và partitions
- Brokers nào đang online
- Partition nào là leader, nào là replica
- Consumer groups và offset của chúng

```
Zookeeper Storage:
  /brokers/ids/1, /brokers/ids/2, /brokers/ids/3
  /brokers/topics/mysql-server.users/partitions/0/state
  /brokers/topics/mysql-server.users/partitions/1/state
  /consumers/app-sync/offsets/mysql-server.users/0
  /consumers/app-sync/offsets/mysql-server.users/1
```

**3. Quản lý Partitions (Phân chia dữ liệu)**
Topic có thể được chia thành nhiều partitions để song song:

```
Topic: mysql-server.users (3 partitions)

Partition 0 → Broker 1 (Leader), Broker 2 (Replica 1), Broker 3 (Replica 2)
Partition 1 → Broker 2 (Leader), Broker 3 (Replica 1), Broker 1 (Replica 2)
Partition 2 → Broker 3 (Leader), Broker 1 (Replica 1), Broker 2 (Replica 2)

Zookeeper quản lý mapping này
→ Khi client ghi/đọc, nó hỏi Zookeeper: "Partition 0 ở broker nào?"
→ Zookeeper: "Broker 1 là leader của partition 0"
```

**4. Kiểm tra Heartbeat (Nhịp tim - Liveness Check)**
Zookeeper định kỳ kiểm tra xem brokers còn sống không:

```
Mỗi giây Zookeeper kiểm tra:
  ✅ Broker 1: Ping → Pong (còn sống)
  ✅ Broker 2: Ping → Pong (còn sống)
  ❌ Broker 3: Ping → Timeout (offline!)
  
  → Zookeeper xoá Broker 3 khỏi danh sách
  → Các clients không gửi requests đến Broker 3 nữa
  → Nếu Broker 3 là LEADER, bầu chọn leader mới
```

**5. Quản lý Consumer Groups**
Zookeeper theo dõi:
- Consumers nào đang subscribe topic nào
- Offset hiện tại của mỗi consumer
- Rebalance consumers khi có consumer mới join/leave

```
Consumer Group: app-sync
  - Consumer 1: offset = 1000
  - Consumer 2: offset = 1000
  - Consumer 3: offset = 1000

Nếu Consumer 4 join:
  → Zookeeper trigger rebalance
  → Rephân chia partitions cho 4 consumers
  → Mỗi consumer tải lại offset từ Zookeeper
```

#### Tại sao cần Zookeeper?
- **Tính nhất quán (Consistency)**: Đảm bảo toàn bộ cụm Kafka luôn đồng bộ
- **Tính khả dụng (Availability)**: Nếu leader xảy ra sự cố, tự động recovery
- **Tính tin cậy (Reliability)**: Không bao giờ mất dữ liệu (với replicas)

**Lưu ý:** Trong hệ thống của bạn chỉ có 1 broker, nhưng Zookeeper vẫn cần để quản lý metadata và lưu offset của consumers.

---

### 3️⃣ **Kafka** (Bus tin nhắn - Message Broker)
- **Cổng**: 9092
- **Bootstrap Server**: kafka:9092
- **Vai trò**: Nơi lưu trữ và phân phối các sự kiện thay đổi dữ liệu
- **Công dụng**:
  - Nhận sự kiện CDC từ Debezium
  - Lưu trữ các topic thay đổi
  - Cho phép các consumer khác nhau subscribe và nhận dữ liệu
  - Đảm bảo tin nhắn không bị mất

**Tại sao cần nó?** Kafka là cầu nối giữa nguồn dữ liệu (MySQL) và các ứng dụng cần sử dụng dữ liệu thay đổi. Nó có thể xử lý hàng triệu thay đổi mỗi giây.

---

### 3️⃣ **Kafka** (Bus tin nhắn - Message Broker)
- **Cổng**: 9092
- **Bootstrap Server**: kafka:9092
- **Vai trò**: Nơi lưu trữ và phân phối các sự kiện thay đổi dữ liệu

#### Kafka làm gì?

**1. Nhận & Lưu trữ Messages**
- Debezium (Producer) gửi messages về thay đổi dữ liệu
- Kafka nhận và lưu trữ vào topics
- Messages được lưu trên disk (không bị mất khi restart)

**2. Phân phối tới Consumers**
- Nhiều consumers có thể đọc cùng một topic
- Mỗi consumer đọc từ offset riêng của nó
- Consumers không ảnh hưởng đến nhau

```
Producer (Debezium) → Kafka Topic → Consumer 1
                                  → Consumer 2
                                  → Consumer 3
```

**3. Partitioning (Phân chia để song song hóa)**
- Một topic có thể chia thành nhiều partitions
- Messages được hash vào partitions dựa trên key
- Mỗi partition có thể xử lý bởi broker/consumer khác nhau
- Tăng throughput (xử lý được nhiều messages hơn)

```
Topic: mysql-server.users (3 partitions)

Message 1 (id=1) → Partition 0
Message 2 (id=2) → Partition 1
Message 3 (id=3) → Partition 2
Message 4 (id=1) → Partition 0 (cùng key id=1)

Consumer 1 xử lý Partition 0
Consumer 2 xử lý Partition 1
Consumer 3 xử lý Partition 2

→ Xử lý song song, tăng tốc độ!
```

**4. Replication (Sao chép để đảm bảo an toàn)**
- Mỗi partition được sao chép thành nhiều replicas
- Nếu leader partition bị xảy ra sự cố, replica khác trở thành leader
- Đảm bảo dữ liệu không bị mất

```
Partition 0:
  Leader (Broker 1) - nhận ghi
  Replica (Broker 2) - backup
  Replica (Broker 3) - backup

Nếu Broker 1 offline:
  Broker 2 trở thành leader
  Dữ liệu vẫn an toàn
```

**5. Retention Policy (Chính sách giữ lại)**
- Kafka giữ messages theo thời gian hoặc dung lượng
- Có thể cấu hình giữ messages bao lâu
- Consumers có thể replay từ đầu (nếu offset còn tồn tại)

#### Tại sao cần Kafka?
- **Decoupling**: Tách biệt MySQL khỏi consumers
  - MySQL không cần biết ai đang đọc dữ liệu
  - Consumers không cần biết MySQL là gì
  
- **Buffering**: Xử lý spike traffic
  - MySQL gửi 10,000 changes/giây
  - Consumer xử lý 1,000/giây
  - Kafka buffer các messages, consumer lấy theo tốc độ của nó
  
- **Replay**: Có thể xử lý lại từ đầu
  - Consumer có thể seek đến offset cũ
  - Reprocess dữ liệu nếu cần
  
- **Multiple subscribers**: Một messages cho nhiều consumers
  - Không cần MySQL replication
  - Tiết kiệm resources

---

### 4️⃣ **Debezium Connector** (Agent bắt lấy thay đổi - CDC Engine)
- **Cổng**: 8083 (REST API)
- **Vai trò**: Kết nối với MySQL, đọc binary logs, chuyển đổi thành sự kiện Kafka
- **Công dụng**:
  - Theo dõi MySQL binary logs
  - Phát hiện INSERT, UPDATE, DELETE trên các bảng
  - Chuyển đổi thay đổi thành JSON messages
  - Gửi messages đến Kafka topics

**Tại sao cần nó?** Debezium là "translator" - nó hiểu được format binary logs của MySQL và chuyển đổi chúng thành Kafka messages mà các ứng dụng dễ dàng đọc được.

---

### 4️⃣ **Debezium Connector** (Agent bắt lấy thay đổi - CDC Engine)
- **Cổng**: 8083 (REST API)
- **Vai trò**: Kết nối với MySQL, đọc binary logs, chuyển đổi thành sự kiện Kafka

#### Debezium làm gì?

**1. Kết nối với MySQL**
- Dùng MySQL protocol để kết nối như một MySQL client
- Đọc binary logs từ MySQL
- Không cần cài gì trên MySQL, không xâm phạm dữ liệu

```
Debezium → (MySQL Protocol) → MySQL
           ↓
           Đọc Binary Logs
           ↓
           Phát hiện INSERT, UPDATE, DELETE
```

**2. Đọc Binary Logs**
- MySQL ghi tất cả thay đổi vào binary logs
- Cấu hình: `log-bin=mysql-bin`, `binlog_format=ROW`
- Debezium theo dõi binary logs từ vị trí cuối cùng
- Mỗi lần MySQL restart, Debezium tìm vị trí tiếp theo để đọc

```
Binary Log File:
  mysql-bin.000001
  ├─ Position 0-100: INSERT into users values (1, 'Alice')
  ├─ Position 100-200: UPDATE users set name='Bob' where id=1
  ├─ Position 200-300: DELETE from users where id=1
  └─ Position 300-400: INSERT into users values (2, 'Charlie')

Debezium:
  Lần 1: Đọc từ position 0 → 400
  Lần 2 (restart): Tiếp tục từ position 400 → (updates mới)
  → Không bao giờ bỏ lỡ updates
```

**3. Chuyển đổi thành JSON Events**
- Đọc binary logs (format nhị phân)
- Chuyển đổi thành JSON messages dễ đọc

```
Binary Log (raw):
  TABLE_MAP mysql-bin.000001:100 ...
  WRITE_ROWS mysql-bin.000001:150 ...

JSON Event (by Debezium):
{
  "before": null,
  "after": {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com"
  },
  "source": {
    "version": "2.6.0",
    "connector": "mysql",
    "name": "mysql-server",
    "ts_ms": 1700000000000,
    "db": "testdb",
    "table": "users",
    "server_id": 1,
    "file": "mysql-bin.000001",
    "pos": 150
  },
  "op": "c",  ← "c"=CREATE(INSERT), "u"=UPDATE, "d"=DELETE
  "ts_ms": 1700000000000
}
```

**4. Gửi tới Kafka Topics**
- Mỗi bảng MySQL → Một Kafka topic
- Topic name: `{server.name}.{database}.{table}`
- Ví dụ: `mysql-server.testdb.users`

```
MySQL Table: users      → Kafka Topic: mysql-server.testdb.users
MySQL Table: products  → Kafka Topic: mysql-server.testdb.products
MySQL Table: orders    → Kafka Topic: mysql-server.testdb.orders
```

**5. Tracking Position (Theo dõi vị trí)**
- Debezium lưu trữ position hiện tại vào Kafka
- Topic: `connect-offsets`
- Nếu Debezium crash, nó sẽ resume từ position đã lưu
- Đảm bảo không bỏ lỡ hoặc duplicate events

```
connect-offsets Topic:
  {
    "source_partition": {
      "server": "mysql-server"
    },
    "source_offset": {
      "file": "mysql-bin.000001",
      "pos": 154,
      "snapshot": false
    }
  }
```

#### Tại sao cần Debezium?
- **Agentless**: Không cần cài gì trên MySQL
- **Change Capture**: Bắt tất cả thay đổi, không bỏ lỡ
- **Near Real-time**: Độ trễ chỉ vài milliseconds
- **Transformation**: Chuyển binary logs → JSON messages
- **Reliable**: Có tracking, không duplicate/lose events

#### Debezium vs Replication
```
MySQL Replication:
  - Sao chép dữ liệu
  - Cần cài thêm Replica instance
  - Chỉ sao chép toàn bộ, không dễ lọc

Debezium (CDC):
  - Capture changes
  - Không cần thêm instance
  - Có thể lọc bảng/cột
  - Có thể transform data
  - Gửi đến multiple endpoints
```

---

### 5️⃣ **Kafka-UI** (Dashboard giám sát)
- **Cổng**: 8080
- **URL**: http://localhost:8080
- **Vai trò**: Giao diện web để xem topics, messages, và producers/consumers

#### Kafka-UI cho phép:

**1. Xem Topics**
```
Topics:
  ├─ mysql-server.testdb.users
  │  ├─ Partitions: 3
  │  ├─ Replication Factor: 1
  │  └─ Messages: 1,234
  ├─ mysql-server.testdb.products
  │  └─ Messages: 567
  └─ connect-offsets
     └─ Messages: 42
```

**2. Xem Messages & Content**
- Xem payload của mỗi message
- Xem schema của message
- Xem timestamp, offset, partition
- Xem message key/value

```
Message Detail:
  Offset: 1000
  Partition: 0
  Timestamp: 2025-11-26 10:30:45
  Key: "1"
  Value: {
    "before": null,
    "after": {"id": 1, "name": "Alice"},
    "op": "c"
  }
```

**3. Giám sát Producers/Consumers**
- Xem client nào đang gửi data
- Xem client nào đang tiêu thụ data
- Xem lag (độ trễ) của consumers

```
Consumer Groups:
  app-sync:
    ├─ Status: Active
    ├─ Members: 2
    ├─ Topic: mysql-server.testdb.users
    ├─ Lag: 0 messages
    └─ Offset: 1234

  app-notify:
    ├─ Status: Active
    ├─ Members: 1
    ├─ Topic: mysql-server.testdb.users
    ├─ Lag: 45 messages (đang xử lý chậm)
    └─ Offset: 1189
```

**4. Xem Cluster Health**
- Số brokers online
- Leader distribution
- Broker resource usage

**5. Debug Issues**
- Xem sao một consumer lại lag?
- Xem topic có messages không?
- Xem producer có gửi data không?
- Xem message có lỗi không?

#### Tại sao cần Kafka-UI?
- **Visibility**: Nhìn thấy dữ liệu chảy hay không
- **Debugging**: Tìm nguyên nhân consumer lag
- **Monitoring**: Theo dõi health của toàn bộ hệ thống
- **Inspection**: Xem nội dung messages
- **Management**: Quản lý topics/partitions

---

## 🔄 Luồng dữ liệu (Data Flow)

### Ví dụ chi tiết từng bước

**Scenario: User thêm khách hàng mới vào MySQL**

```
Step 1: Người dùng INSERT vào MySQL
├─ SQL: INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')
└─ Kết quả: Khách hàng được thêm vào MySQL

Step 2: MySQL ghi vào Binary Log
├─ MySQL tự động ghi sự kiện vào binary log
├─ Format: ROW (chi tiết từng cột thay đổi)
└─ File: mysql-bin.000001 position 100

Step 3: Debezium phát hiện thay đổi
├─ Debezium đọc binary logs
├─ Phát hiện: INSERT vào table 'users'
└─ Trích xuất: id=1, name=Alice, email=alice@example.com

Step 4: Debezium chuyển đổi thành JSON
└─ Tạo event JSON:
   {
     "op": "c",  (create/insert)
     "before": null,
     "after": {
       "id": 1,
       "name": "Alice",
       "email": "alice@example.com"
     },
     "source": {
       "db": "testdb",
       "table": "users",
       "file": "mysql-bin.000001",
       "pos": 100
     }
   }

Step 5: Debezium gửi vào Kafka
├─ Topic: mysql-server.testdb.users
├─ Partition: 0 (tính toán từ key)
├─ Offset: 1000 (vị trí message tiếp theo)
└─ Message: Event JSON ở trên

Step 6: Zookeeper ghi nhận
├─ Zookeeper cập nhật offset của Debezium
└─ Lưu: "Debezium đã gửi đến offset 1000"

Step 7: Consumers đọc từ Kafka
├─ Consumer 1 (app-sync):
│  ├─ Đọc message từ offset 1000
│  ├─ Gửi data tới Elasticsearch
│  └─ Cập nhật offset → 1001
│
├─ Consumer 2 (app-notify):
│  ├─ Đọc message từ offset 1000
│  ├─ Gửi email: "Customer Alice added"
│  └─ Cập nhật offset → 1001
│
└─ Consumer 3 (app-log):
   ├─ Đọc message từ offset 1000
   ├─ Ghi vào audit table
   └─ Cập nhật offset → 1001

Step 8: Applications xử lý dữ liệu
├─ Elasticsearch: Bây giờ có thể search "Alice"
├─ Email service: "Alice" đã được thông báo
└─ Audit log: "New customer Alice - 2025-11-26 10:30"
```

---

### Timeline theo thời gian

```
Time     Event
────────────────────────────────────────────────
T0ms     INSERT execute trong MySQL
T1ms     MySQL ghi binary log
T5ms     Debezium phát hiện change
T10ms    Debezium gửi tới Kafka
T15ms    Consumer 1 nhận & xử lý
T20ms    Consumer 2 nhận & xử lý
T25ms    Consumer 3 nhận & xử lý
T30ms    Elasticsearch cập nhật
T40ms    Email được gửi
T50ms    Audit log ghi xong

→ Tổng latency: ~50ms (không mất dữ liệu!)
```

---

## 🚀 Quản lý các thành phần

### Bắt đầu toàn bộ hệ thống
```bash
docker-compose up -d
```

**Chuyên có gì xảy ra:**
1. Zookeeper khởi động (port 2181)
2. Kafka khởi động & kết nối Zookeeper (port 9092)
3. MySQL khởi động với binary logging (port 3306)
4. Debezium Connect khởi động & sẵn sàng nhận cấu hình (port 8083)
5. Kafka-UI khởi động (port 8080)

**Kiểm tra xem mọi thứ đã ready:**
```bash
# Xem tất cả containers
docker-compose ps

# Output mong muốn:
# NAME      STATUS
# zookeeper Up ... (healthy)
# kafka     Up ... (healthy)
# mysql     Up ... (healthy)
# connect   Up ... (healthy)
# kafka-ui  Up ... (healthy)
```

### Xem trạng thái containers
```bash
docker-compose ps
```

### Xem logs chi tiết
```bash
# Xem logs tất cả services (real-time)
docker-compose logs -f

# Xem logs của một service
docker-compose logs -f mysql        # MySQL logs
docker-compose logs -f connect      # Debezium logs
docker-compose logs -f kafka        # Kafka logs

# Xem logs của 100 dòng cuối
docker-compose logs --tail=100 mysql

# Xem logs từ 5 phút trước
docker-compose logs --since 5m connect
```

**Logs quan trọng:**
- MySQL: Xem binary logging, errors
- Kafka: Broker startup, topic creation
- Debezium: Connector initialization, source reading
- Kafka-UI: Web server startup

### Dừng toàn bộ hệ thống (giữ dữ liệu)
```bash
docker-compose stop
# Hoặc
docker-compose down
```

**Khác nhau:**
- `stop`: Dừng containers, giữ data & volumes
- `down`: Xóa containers, giữ data & volumes

### Xóa toàn bộ (bao gồm volumes & data)
```bash
docker-compose down -v
```

**Cảnh báo:** Lệnh này xóa tất cả MySQL data, Kafka topics, v.v. Chỉ dùng khi muốn clean slate!

### Khởi động lại một service
```bash
docker-compose restart mysql     # Restart MySQL
docker-compose restart connect   # Restart Debezium
```

### Xem resource usage
```bash
docker stats
```

### Truy cập container shell
```bash
# Vào bash của MySQL container
docker-compose exec mysql bash

# Chạy MySQL CLI
docker-compose exec mysql mysql -uroot -proot

# Vào bash của Kafka container
docker-compose exec kafka bash
```

---

## 📊 Các Endpoints quan trọng & cách kết nối

| Thành phần | Endpoint | Công dụng | Cách kết nối |
|-----------|----------|----------|-------------|
| **MySQL** | localhost:3306 | Database source | `mysql -h localhost -u root -p` |
| **Kafka** | localhost:9092 | Message broker | Bootstrap server cho producers/consumers |
| **Zookeeper** | localhost:2181 | Coordination | Internal (không cần kết nối trực tiếp) |
| **Debezium REST API** | http://localhost:8083 | Manage connectors | `curl http://localhost:8083/connectors` |
| **Kafka-UI** | http://localhost:8080 | Monitor & debug | Mở browser: http://localhost:8080 |

### Cách kiểm tra kết nối

**1. Kiểm tra MySQL**
```bash
docker-compose exec mysql mysql -uroot -proot -e "SELECT 1"
# Output: 1
```

**2. Kiểm tra Kafka**
```bash
docker-compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092
# Output: ApiVersion(api_key: ..., min_version: ..., max_version: ...)
```

**3. Kiểm tra Debezium**
```bash
curl http://localhost:8083
# Output: {"version":"2.6.0","commit":"..."}
```

**4. Kiểm tra Zookeeper**
```bash
docker-compose exec zookeeper zookeeper-shell localhost:2181 ls /
# Output: [brokers, cluster, ...]
```

---

## 🔗 Quan hệ & Giao tiếp giữa các thành phần

### Sơ đồ kết nối chi tiết

```
┌─────────────────────────────────────────────────────────────────┐
│           CHANGE DATA CAPTURE ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      MySQL (Source DB)                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Table: users, products, orders, ...                     │   │
│  │ Binary Logging: ON                                      │   │
│  │ Binary Logs: mysql-bin.000001, mysql-bin.000002, ...   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                      ⬆️ ⬇️ (reads)                              │
│              MySQL Protocol Port 3306                           │
└─────────────────────────────────────────────────────────────────┘

                           ⬇️ ⬆️
                      (3306 connection)

┌─────────────────────────────────────────────────────────────────┐
│              Debezium Connect (CDC Engine)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ MySQL Connector                                         │   │
│  │ - Reads binary logs                                     │   │
│  │ - Parses changes (INSERT/UPDATE/DELETE)               │   │
│  │ - Converts to JSON events                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                      ⬇️ (publishes)                            │
│              REST API Port 8083                                 │
└─────────────────────────────────────────────────────────────────┘

                           ⬇️
                    (Kafka Protocol)

┌─────────────────────────────────────────────────────────────────┐
│                  Zookeeper (Coordinator)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ - Manages Kafka cluster state                           │   │
│  │ - Stores metadata (topics, partitions, brokers)        │   │
│  │ - Tracks consumer offsets                              │   │
│  │ - Handles leader election                              │   │
│  │ - Monitors broker health (heartbeats)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                Port 2181 (internal use)                         │
└─────────────────────────────────────────────────────────────────┘

                ⬆️ (coordinates) ⬇️
                           
┌─────────────────────────────────────────────────────────────────┐
│              Kafka Broker (Message Bus)                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Topics (auto-created by Debezium):                     │   │
│  │  ├─ mysql-server.db.users          [1000 messages]    │   │
│  │  ├─ mysql-server.db.products       [500 messages]     │   │
│  │  ├─ connect-configs                [42 messages]      │   │
│  │  ├─ connect-offsets                [1000 messages]    │   │
│  │  └─ connect-status                 [100 messages]     │   │
│  │                                                         │   │
│  │ Brokers: 1 (localhost:9092)                            │   │
│  │ Replicas: 1 (single broker)                            │   │
│  │ Partitions: configurable per topic                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                Port 9092 (client access)                        │
│                Port 29092 (internal access)                     │
└─────────────────────────────────────────────────────────────────┘

      ⬇️ (consumers subscribe)     ⬆️ (producers publish)

┌────────────────────────────────────────────────────────────┐
│         Consumers (Applications)                            │
├────────────────────────────────────────────────────────────┤
│                                                              │
│ Consumer Group 1: app-sync                                  │
│  ├─ Consumer 1: Elasticsearch sync                          │
│  ├─ Consumer 2: MongoDB sync                                │
│  └─ Offset: 1000 (for each consumer)                        │
│                                                              │
│ Consumer Group 2: app-notify                                │
│  ├─ Consumer 1: Email service                               │
│  ├─ Consumer 2: SMS service                                 │
│  └─ Offset: 950 (lagging behind)                            │
│                                                              │
│ Consumer Group 3: app-analytics                             │
│  └─ Consumer 1: Data warehouse ETL                          │
│                                                              │
└────────────────────────────────────────────────────────────┘

                ⬇️ (monitors all)

┌────────────────────────────────────────────────────────────┐
│         Kafka-UI (Dashboard)                                │
│  - Visualize topics, messages, consumers                    │
│  - Monitor lag, throughput, health                          │
│  - Port 8080                                                │
└────────────────────────────────────────────────────────────┘
```

### Luồng giao tiếp

**1. Debezium ↔ MySQL**
```
Debezium: "Give me binary logs since position 100"
MySQL: "Here are the binary logs from position 100 to 500"
Debezium: "Ok, I'll remember position 500 next time"
MySQL: (ghi dữ liệu vào binary logs tiếp theo)
```

**2. Debezium ↔ Kafka**
```
Debezium: "I have a change event for topic 'mysql-server.users'"
Kafka: "Ok, I'll store it at offset 1000"
Zookeeper: (cập nhật metadata)
Debezium: "Message sent, next offset will be 1001"
```

**3. Kafka ↔ Consumers**
```
Consumer 1: "Give me messages from topic 'mysql-server.users' from offset 1000"
Kafka: "Here's message at offset 1000"
Consumer 1: "I processed it, update my offset to 1001"
Zookeeper: (lưu offset 1001 cho consumer 1)
```

**4. Zookeeper ↔ All**
```
Zookeeper: "Broker 1 is the leader for partition 0"
Zookeeper: "Consumer 1 has offset 1000, Consumer 2 has offset 950"
Zookeeper: "Broker 2 is down, rebalancing..."
All: (nhận updates)
```

---

## 💡 Trường hợp sử dụng thực tế

✅ **Real-time Data Sync**: Đồng bộ dữ liệu từ MySQL sang Elasticsearch, MongoDB, etc.

✅ **Event Streaming**: Bắn sự kiện khi dữ liệu thay đổi cho các microservices

✅ **Data Warehouse**: ETL dữ liệu từ MySQL vào Data Warehouse gần như real-time

✅ **Cache Invalidation**: Cập nhật cache khi dữ liệu thay đổi

✅ **Audit Logging**: Ghi lại lịch sử thay đổi dữ liệu chi tiết

✅ **Analytics**: Phân tích dữ liệu thay đổi trong thời gian thực

---

## 📝 Cấu hình Debezium Connector - Chi tiết

### Tạo MySQL Connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mysql-connector",
    "config": {
      "connector.class": "io.debezium.connector.mysql.MySqlConnector",
      "database.hostname": "mysql",
      "database.port": 3306,
      "database.user": "root",
      "database.password": "root",
      "database.server.id": 1,
      "database.server.name": "mysql-server",
      "table.include.list": "testdb.users,testdb.products",
      "key.converter": "org.apache.kafka.connect.json.JsonConverter",
      "value.converter": "org.apache.kafka.connect.json.JsonConverter"
    }
  }'
```

### Giải thích chi tiết các tham số

#### **Cơ bản (Must-have)**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `connector.class` | `io.debezium.connector.mysql.MySqlConnector` | Loại connector (MySQL) |
| `name` | `mysql-connector` | Tên duy nhất cho connector này |
| `database.hostname` | `mysql` | Hostname MySQL (trong Docker: service name) |
| `database.port` | `3306` | Port MySQL |
| `database.user` | `root` | User kết nối MySQL |
| `database.password` | `root` | Password MySQL |

#### **Định danh (Identification)**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `database.server.id` | `1` | Unique ID cho MySQL server (phải khác 0, phải duy nhất) |
| `database.server.name` | `mysql-server` | Tên logic cho server, dùng trong topic naming |

**Ví dụ:** Topic sẽ được đặt tên: `mysql-server.testdb.users`

#### **Lọc dữ liệu (Filtering)**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `table.include.list` | `testdb.users,testdb.products` | **Chỉ** bắt lấy các bảng này |
| `table.exclude.list` | `testdb.tmp_*` | **Không** bắt lấy các bảng này |
| `column.include.list` | `testdb.users.id,testdb.users.name` | Chỉ bắt lấy các cột này |
| `column.exclude.list` | `testdb.users.password,testdb.users.salt` | Không bắt lấy các cột này |

**Ví dụ:** Nếu bạn chỉ muốn public data, bạn có thể exclude password, token, v.v.:
```json
"column.exclude.list": "testdb.users.password,testdb.users.secret_token"
```

#### **Converters (Format dữ liệu)**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `key.converter` | `org.apache.kafka.connect.json.JsonConverter` | Key format: JSON |
| `value.converter` | `org.apache.kafka.connect.json.JsonConverter` | Value format: JSON |

**Khác nhau:**
```
Key: Dùng để partitioning, thường là ID
Value: Nội dung message (before, after, operation, v.v.)

Key: "1"
Value: {
  "op": "u",
  "before": {"name": "Alice"},
  "after": {"name": "Bob"},
  ...
}
```

**Các converter khác:**
```
- AvroConverter (compact nhưng cần Schema Registry)
- ProtobufConverter (Google Protocol Buffers)
- StringConverter (plain text, không recommend)
```

#### **Snapshot (Khởi tạo toàn bộ dữ liệu)**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `snapshot.mode` | `initial` | Đọc toàn bộ dữ liệu hiện có trước khi bắt lấy changes |
| | `when_needed` | Chỉ snapshot nếu không có offset history |
| | `never` | Không snapshot, chỉ bắt lấy changes sau này |
| | `initial_only` | Snapshot rồi stop (không bắt lấy changes tiếp theo) |

```json
"snapshot.mode": "initial"
→ Lần đầu tiên, Debezium sẽ:
  1. Lock table users
  2. Đọc toàn bộ dữ liệu (SELECT * FROM users)
  3. Gửi mỗi dòng đến Kafka như CREATE events
  4. Unlock table
  5. Bắt đầu bắt lấy changes từ binary logs
```

#### **Transformation & SMTs (Single Message Transform)**

```json
"transforms": "route",
"transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
"transforms.route.regex": "([^.]+)\\.([^.]+)\\.([^.]+)",
"transforms.route.replacement": "$3"
```

**Ví dụ:** Nếu muốn chỉ lấy tên bảng, bỏ database name:
```
mysql-server.testdb.users → users
mysql-server.testdb.products → products
```

#### **Handling Errors**

| Tham số | Giá trị | Công dụng |
|--------|--------|----------|
| `errors.tolerance` | `none` | Dừng khi gặp lỗi (default) |
| | `all` | Tiếp tục bỏ qua lỗi |
| `errors.log.enable` | `true` | Ghi log các lỗi bỏ qua |
| `errors.log.include.original` | `true` | Ghi lại message gốc trong log |

### Xem Connector Status

```bash
# Danh sách tất cả connectors
curl http://localhost:8083/connectors

# Chi tiết về connector
curl http://localhost:8083/connectors/mysql-connector

# Status (running/paused/failed)
curl http://localhost:8083/connectors/mysql-connector/status

# Task status
curl http://localhost:8083/connectors/mysql-connector/tasks
```

### Kiểm tra Topics được tạo

```bash
# Xem tất cả topics
docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Output:
# connect-configs
# connect-offsets
# connect-status
# mysql-server.testdb.users
# mysql-server.testdb.products
```

### Xem Messages trong Topic

```bash
# Xem 10 messages mới nhất từ topic
docker-compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic mysql-server.testdb.users \
  --from-beginning \
  --max-messages 10
```

### Tắt/Khởi động Connector

```bash
# Tắt
curl -X PUT http://localhost:8083/connectors/mysql-connector/pause

# Khởi động lại
curl -X PUT http://localhost:8083/connectors/mysql-connector/resume

# Xóa (thận trọng!)
curl -X DELETE http://localhost:8083/connectors/mysql-connector
```

---

## ✅ Quy trình thiết lập

1. **Bắt đầu services**
   ```bash
   docker-compose up -d
   ```

2. **Kiểm tra MySQL đã sẵn sàng**
   ```bash
   docker-compose exec mysql mysql -uroot -proot -e "SELECT 1"
   ```

3. **Tạo database và table** (nếu cần)
   ```bash
   docker-compose exec mysql mysql -uroot -proot -e "CREATE DATABASE testdb; CREATE TABLE testdb.users (id INT PRIMARY KEY, name VARCHAR(255));"
   ```

4. **Tạo Debezium Connector** (xem mã ở trên)

5. **Xem các topics trong Kafka**
   ```bash
   docker exec <kafka-container-id> kafka-topics --list --bootstrap-server localhost:9092
   ```

6. **Monitor messages**
   - Truy cập http://localhost:8080 (Kafka UI)
   - Hoặc dùng command line consumer

---

## 🎓 Kết luận

| Thành phần | Vai trò chính |
|-----------|--------------|
| **MySQL** | 📦 Lưu trữ dữ liệu gốc |
| **Zookeeper** | 🎛️ Phối hợp & quản lý trạng thái |
| **Kafka** | 🚚 Vận chuyển & lưu trữ sự kiện |
| **Debezium** | 🔄 Bắt & chuyển đổi thay đổi |
| **Kafka-UI** | 👁️ Giám sát & debug |

Khi mọi thứ hoạt động, bất cứ thay đổi nào trong MySQL sẽ được Debezium tự động phát hiện và gửi qua Kafka, cho phép các ứng dụng khác nhận và xử lý dữ liệu gần như real-time!

