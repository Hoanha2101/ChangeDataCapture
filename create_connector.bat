@echo off
REM Create Debezium MySQL Connector using CMD

setlocal enabledelayedexpansion

REM Create a temporary JSON file
set "JSON_FILE=%TEMP%\connector_config.json"

REM Write JSON to file
(
echo {
echo   "name": "mysql-connector",
echo   "config": {
echo     "connector.class": "io.debezium.connector.mysql.MySqlConnector",
echo     "database.hostname": "mysql",
echo     "database.port": 3306,
echo     "database.user": "root",
echo     "database.password": "root",
echo     "database.server.id": 1,
echo     "database.server.name": "mysql-server",
echo     "table.include.list": "testdb.users",
echo     "topic.prefix": "mysql-server",
echo     "snapshot.mode": "initial",
echo     "schema.history.internal.kafka.bootstrap.servers": "kafka:29092",
echo     "schema.history.internal.kafka.topic": "schema-changes.mysql"
echo   }
echo }
) > "%JSON_FILE%"

echo Creating Debezium MySQL Connector...
echo.

REM Send the request to Debezium Connect API
curl -X POST http://localhost:8083/connectors ^
  -H "Content-Type: application/json" ^
  -d @"%JSON_FILE%"

echo.
echo Connector creation request sent!
echo.

REM Cleanup
del "%JSON_FILE%"

pause
