# CDC Demo - Hướng Dẫn Hoàn Chỉnh

## 🎯 Mục Đích

Đây là một hệ thống **Change Data Capture (CDC)** sử dụng:
- **MySQL**: Nguồn dữ liệu
- **Debezium**: Capture changes từ MySQL Binary Logs
- **Kafka**: Message broker để phân phối changes
- **Zookeeper**: Quản lý cụm Kafka
- **Kafka-UI**: Dashboard để giám sát

## ✅ Các Bước Để Kết Nối & Sử Dụng

### **Bước 1: Khởi Động Hệ Thống**

```bash
docker-compose up -d
```

**`Chờ ~30 giây` để tất cả services khởi động xong**

Kiểm tra status:
```bash
docker-compose ps
```

### **Bước 2: Tạo Debezium Connector**

Chạy script batch để tạo connector:
```cmd
create_connector.bat
```

Hoặc kiểm tra status connector:
```cmd
curl http://localhost:8083/connectors/mysql-connector/status
```

### **Bước 3: Tạo Database & Table**

```cmd
docker-compose exec -T mysql mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS testdb; CREATE TABLE IF NOT EXISTS testdb.users (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(255), email VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
```

### **Bước 4: Thêm Dữ Liệu Test**

```bash
docker-compose exec -T mysql mysql -uroot -proot testdb -e "INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com'); INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com');"
```

### **Bước 5: Xem Messages Trong Kafka**

**Cách 1: Dùng CLI Kafka**
```bash
docker-compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mysql-server.testdb.users --from-beginning
```

**Cách 2: Dùng Python Consumer** ⭐ (Recommended)
```bash
python consumer_demo.py
```

**Cách 3: Dùng Kafka-UI (Web Dashboard)**
```
Mở browser: http://localhost:8080
```

### **Bước 6: Test CDC Với INSERT/UPDATE/DELETE**

```bash
# INSERT
docker-compose exec -T mysql mysql -uroot -proot testdb -e "INSERT INTO users (name, email) VALUES ('Charlie', 'charlie@example.com');"

# UPDATE
docker-compose exec -T mysql mysql -uroot -proot testdb -e "UPDATE users SET name='Alice Updated' WHERE id=1;"

# DELETE
docker-compose exec -T mysql mysql -uroot -proot testdb -e "DELETE FROM users WHERE id=2;"
```

Sau đó chạy consumer lại để xem các changes:
```bash
python consumer_demo.py
```

---

## 📊 Các Endpoints Quan Trọng

| Service | URL/Port | Tác Dụng |
|---------|----------|---------|
| **MySQL** | `localhost:3306` | Database source (user: root, pass: root) |
| **Kafka** | `localhost:9092` | Message broker |
| **Debezium REST API** | `http://localhost:8083` | Manage connectors |
| **Kafka-UI** | `http://localhost:8080` | Web dashboard để giám sát |
| **Zookeeper** | `localhost:2181` | Coordination (internal use) |

---

## 🔧 Các Lệnh Quan Trọng

### Quản Lý Containers

```bash
# Khởi động
docker-compose up -d

# Dừng
docker-compose down

# Xem status
docker-compose ps

# Xem logs
docker-compose logs -f
docker-compose logs -f mysql
docker-compose logs -f connect
docker-compose logs -f kafka
```

### Quản Lý Kafka Topics

```bash
# Danh sách topics
docker-compose exec -T kafka kafka-topics --list --bootstrap-server localhost:9092

# Xem messages từ topic
docker-compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mysql-server.testdb.users --from-beginning

# Xem số messages trong topic
docker-compose exec -T kafka kafka-run-class kafka.tools.JmxTool --object-name kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions
```

### Quản Lý Connectors

```bash
# Liệt kê connectors
curl http://localhost:8083/connectors

# Xem chi tiết connector
curl http://localhost:8083/connectors/mysql-connector

# Xem status
curl http://localhost:8083/connectors/mysql-connector/status

# Tắt connector
curl -X PUT http://localhost:8083/connectors/mysql-connector/pause

# Khởi động lại
curl -X PUT http://localhost:8083/connectors/mysql-connector/resume

# Xóa connector
curl -X DELETE http://localhost:8083/connectors/mysql-connector
```

### Quản Lý MySQL

```bash
# Truy cập MySQL CLI
docker-compose exec mysql mysql -uroot -proot

# Xem databases
docker-compose exec -T mysql mysql -uroot -proot -e "SHOW DATABASES;"

# Xem tables
docker-compose exec -T mysql mysql -uroot -proot -e "SHOW TABLES FROM testdb;"

# Xem dữ liệu
docker-compose exec -T mysql mysql -uroot -proot testdb -e "SELECT * FROM users;"

# Xem binary logs status
docker-compose exec -T mysql mysql -uroot -proot -e "SHOW MASTER STATUS;"
```

---

## 📝 Cấu Trúc Files

```
d:\langCG\ChangeDataCapture\
├── docker-compose.yml          ← Cấu hình các services
├── create_connector.bat         ← Script batch tạo connector
├── consumer_demo.py             ← Python consumer để xem messages
├── README.md                    ← Tài liệu chi tiết
├── QUICK_START.md               ← Hướng dẫn nhanh này
└── mysql-data/                  ← Volume lưu MySQL data
```

---

## 🚀 Workflow Demo Hoàn Chỉnh (Step-by-Step)

### **Session 1: Setup (Lần đầu)**

```cmd
REM 1. Khởi động
docker-compose up -d
timeout 30

REM 2. Tạo database & table
docker-compose exec -T mysql mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS testdb; CREATE TABLE IF NOT EXISTS testdb.users (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(255), email VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"

REM 3. Tạo connector
create_connector.bat
timeout 10

REM 4. Thêm dữ liệu
docker-compose exec -T mysql mysql -uroot -proot testdb -e "INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com'), ('Bob', 'bob@example.com');"

REM 5. Xem messages
python consumer_demo.py
```

### **Session 2: Test Changes**

```cmd
REM 1. INSERT mới
docker-compose exec -T mysql mysql -uroot -proot testdb -e "INSERT INTO users (name, email) VALUES ('Charlie', 'charlie@example.com');"

REM 2. Xem message
python consumer_demo.py

REM 3. UPDATE dữ liệu
docker-compose exec -T mysql mysql -uroot -proot testdb -e "UPDATE users SET name='Alice v2' WHERE id=1;"

REM 4. Xem message
python consumer_demo.py

REM 5. DELETE dữ liệu
docker-compose exec -T mysql mysql -uroot -proot testdb -e "DELETE FROM users WHERE id=2;"

REM 6. Xem message
python consumer_demo.py
```

### **Session 3: Monitoring (Giám Sát)**

```cmd
REM 1. Mở Kafka-UI trong browser
REM    Browser: http://localhost:8080
REM    → Xem topics, messages, consumers

REM 2. Hoặc xem via CLI
docker-compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mysql-server.testdb.users --from-beginning

REM 3. Check connector status
curl http://localhost:8083/connectors/mysql-connector/status
```

---

## 💡 Message Format (Kafka Message Structure)

Mỗi message trong Kafka có cấu trúc:

```json
{
  "schema": { /* Schema definition */ },
  "payload": {
    "before": { /* Giá trị trước (NULL nếu INSERT) */ },
    "after": { /* Giá trị sau (NULL nếu DELETE) */ },
    "source": {
      "version": "2.6.2.Final",
      "connector": "mysql",
      "name": "mysql-server",
      "ts_ms": 1764176609000,
      "snapshot": "first",
      "db": "testdb",
      "table": "users",
      "server_id": 0,
      "file": "mysql-bin.000005",
      "pos": 1315,
      "row": 0
    },
    "op": "c",  /* 'c'=CREATE, 'u'=UPDATE, 'd'=DELETE, 'r'=READ */
    "ts_ms": 1764176609474,
    "transaction": null
  }
}
```

**Operation Types:**
- `r` = READ (Snapshot data)
- `c` = CREATE (INSERT)
- `u` = UPDATE
- `d` = DELETE
- `t` = TRUNCATE

---

## 🐛 Troubleshooting

### **1. Debezium không kết nối Kafka**
```bash
# Kiểm tra logs
docker-compose logs connect

# Giải pháp: Restart services
docker-compose down
docker-compose up -d
timeout 30
```

### **2. Connector task failed**
```cmd
REM Kiểm tra status
curl http://localhost:8083/connectors/mysql-connector/status

REM Xóa & tạo lại connector
curl -X DELETE http://localhost:8083/connectors/mysql-connector
create_connector.bat
```

### **3. Không thấy messages trong topic**
```cmd
REM Kiểm tra connector status
curl http://localhost:8083/connectors/mysql-connector/status

REM Kiểm tra topics
docker-compose exec -T kafka kafka-topics --list --bootstrap-server localhost:9092

REM Nếu topic chưa có, restart connector
curl -X DELETE http://localhost:8083/connectors/mysql-connector
timeout 5
create_connector.bat
```

### **4. Python consumer lỗi**
```bash
# Cài lại package
pip install confluent-kafka

# Hoặc dùng CLI
docker-compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mysql-server.testdb.users --max-messages 5
```

---

## 📚 Tài Liệu Tham Khảo

- [Debezium MySQL Connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Confluent Platform](https://docs.confluent.io/)
- [CDC Best Practices](https://www.confluent.io/learn/change-data-capture/)

---

## 🎓 Tiếp Theo?

Sau khi CDC hoạt động, bạn có thể:

1. **Sync dữ liệu real-time** vào Elasticsearch, MongoDB, v.v.
2. **Gửi notifications** khi có changes
3. **Cập nhật cache** (Redis, Memcached)
4. **ETL vào Data Warehouse** (BigQuery, Redshift)
5. **Audit logging** - ghi lại tất cả changes
6. **Event Streaming** - phát events cho microservices

---

**Happy CDC-ing!** 🚀
