# Project: Advanced Microservice for Real-time Data Analytics and Anomaly Detection

## Overall Goal:

Develop a highly scalable, real-time data ingestion, processing, and anomaly detection microservice using Python, FastAPI, and Kafka. The service should be robust, extensible, and capable of handling a high volume of streaming data from various IoT devices. The anomaly detection should employ a configurable machine learning model.

## Core Features:

1.  **Real-time Data Ingestion (Kafka Producer):**
    *   A component responsible for simulating or ingesting data from multiple hypothetical IoT devices.
    *   Each device sends JSON payloads containing sensor readings (temperature, humidity, pressure, device_id, timestamp).
    *   This component acts as a Kafka producer, publishing raw data to a `raw_iot_data` Kafka topic.
    *   Ensure robust error handling and message acknowledgments.
    *   Implement configurable data generation rates (e.g., 100-1000 messages/second).

2.  **Stream Processing and Feature Engineering (Kafka Consumer/Processor):**
    *   A Kafka consumer group that subscribes to the `raw_iot_data` topic.
    *   For each incoming message:
        *   Validate the JSON schema.
        *   Perform basic data cleaning (e.g., handling missing values, type conversions).
        *   Extract relevant features for anomaly detection (e.g., moving averages, standard deviations over a sliding window for each sensor reading, rate of change).
        *   Aggregate data if necessary (e.g., per-device 5-second window statistics).
    *   Publish the processed data (with engineered features) to a `processed_iot_data` Kafka topic.
    *   Implement retry mechanisms for transient processing errors.

3.  **Anomaly Detection Service (FastAPI):**
    *   A FastAPI application with a REST API.
    *   **`/predict` Endpoint (POST):**
        *   Receives a batch of processed sensor data (JSON array of features).
        *   Loads a pre-trained anomaly detection model (e.g., Isolation Forest, One-Class SVM).
        *   Applies the model to predict anomaly scores for each data point.
        *   Returns anomaly scores and binary classification (normal/anomaly) for each input.
    *   **`/train` Endpoint (POST):**
        *   Receives historical "normal" data.
        *   Trains a new anomaly detection model and saves it. This should be an asynchronous operation.
        *   Returns a status indicating training initiated or completed.
    *   **`/model_info` Endpoint (GET):**
        *   Returns metadata about the currently loaded model (e.g., model type, training date, feature names expected).
    *   **Real-time Anomaly Notification (Kafka Consumer):**
        *   Another Kafka consumer subscribes to `processed_iot_data`.
        *   Feeds data in real-time to the `/predict` endpoint (or directly uses the loaded model).
        *   If an anomaly is detected, publish a notification to an `iot_anomalies` Kafka topic, including device_id, timestamp, anomaly_score, and relevant features.

4.  **Data Storage (PostgreSQL):**
    *   A PostgreSQL database to store:
        *   Raw IoT data (for historical analysis/replay).
        *   Processed IoT data (with engineered features).
        *   Anomaly notifications.
        *   Model metadata.
    *   Implement SQLAlchemy ORM for database interactions.
    *   Define schema for each data type.

5.  **Monitoring and Alerting:**
    *   Integrate Prometheus for metrics collection (e.g., message rates, processing latency, anomaly rates, API response times).
    *   Integrate Grafana for dashboard visualization.
    *   Consider Alertmanager for sending notifications (e.g., Slack, PagerDuty) on critical anomalies or service health issues.

6.  **Deployment (Docker & Docker Compose):**
    *   Containerize each component (Kafka, Zookeeper, PostgreSQL, Data Ingestion, Stream Processor, Anomaly Detector).
    *   Use Docker Compose to orchestrate the entire microservice stack.
    *   Ensure proper environment variable injection for configuration (e.g., Kafka broker addresses, database credentials, model paths).

## Technology Stack:

*   **Language:** Python 3.10+
*   **Web Framework:** FastAPI
*   **Asynchronous Tasks:** Celery or FastAPI Background Tasks for model training.
*   **Streaming Platform:** Apache Kafka
*   **Database:** PostgreSQL (via SQLAlchemy)
*   **Monitoring:** Prometheus, Grafana
*   **Containerization:** Docker, Docker Compose
*   **Machine Learning:** Scikit-learn (e.g., IsolationForest, OneClassSVM) for anomaly detection.

## Project Structure (Proposed):

```
.
├── docker-compose.yaml
├── Dockerfile.ingestor
├── Dockerfile.processor
├── Dockerfile.api
├── README.md
├── requirements.txt
├── scripts/
│   ├── start_dev.sh
│   └── setup_topics.sh
├── src/
│   ├── __init__.py
│   ├── config.py             # Centralized configuration management
│   ├── database.py           # SQLAlchemy engine, session, Base
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── iot_data.py
│   │   ├── processed_data.py
│   │   └── anomaly_alerts.py
│   ├── kafka/
│   │   ├── __init__.py
│   │   ├── producer.py       # Data ingestion producer
│   │   └── consumer.py       # Base consumer class
│   ├── services/
│   │   ├── __init__.py
│   │   ├── data_ingestion.py # Main ingestion logic
│   │   ├── stream_processor.py # Main stream processing logic
│   │   └── anomaly_detector.py # Model loading, prediction, notification logic
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app instance
│   │   ├── routers/          # API endpoints
│   │   │   ├── __init__.py
│   │   │   ├── predict.py
│   │   │   └── train.py
│   │   └── schemas.py        # Pydantic models for API
│   ├── ml/                   # Machine learning model handling
│   │   ├── __init__.py
│   │   ├── models/           # Stored trained models (e.g., .pkl files)
│   │   └── utils.py          # Model loading/saving utilities
│   └── utils/
│       ├── __init__.py
│       └── logger.py         # Centralized logging setup
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_ingestion.py
│   │   ├── test_processor.py
│   │   └── test_detector.py
│   └── integration/
│       ├── test_kafka_pipeline.py
│       └── test_api_endpoints.py
└── .env                      # Environment variables for local development
```

## Detailed Requirements for Each Component:

### 1. Data Ingestion (Python Script / Dockerfile.ingestor)
*   **Input:** Simulated sensor data.
*   **Output:** Messages to `raw_iot_data` Kafka topic.
*   **Logic:**
    *   Generate random sensor readings within reasonable ranges for `temperature`, `humidity`, `pressure`.
    *   Assign a unique `device_id` (e.g., `device_001` to `device_100`).
    *   Include a `timestamp` (ISO 8601 format).
    *   Use `confluent-kafka-python` or `kafka-python` client.
    *   Handle Kafka producer configuration (bootstrap servers, security if needed).
    *   Implement graceful shutdown.
    *   Metrics: messages produced/sec, errors.

### 2. Stream Processing (Python Script / Dockerfile.processor)
*   **Input:** `raw_iot_data` Kafka topic.
*   **Output:** Messages to `processed_iot_data` Kafka topic, insertions to `raw_iot_data` table in PostgreSQL.
*   **Logic:**
    *   Consume messages in batches (e.g., 100 messages).
    *   Validate each JSON payload against a Pydantic schema for `RawIoTData`.
    *   Use a sliding window (e.g., 5 minutes) to calculate moving averages and standard deviations for `temperature`, `humidity`, `pressure` per `device_id`.
    *   Features to engineer: `temp_ma_5min`, `temp_std_5min`, `humidity_ma_5min`, `humidity_std_5min`, `pressure_ma_5min`, `pressure_std_5min`, `temp_roc`, `humidity_roc`, `pressure_roc`.
    *   Persist raw data to `raw_iot_data` table and processed data to `processed_iot_data` table.
    *   Metrics: messages consumed/sec, processing latency, feature engineering errors, DB insertion rates.

### 3. Anomaly Detection Service (FastAPI / Dockerfile.api)
*   **Input:** Processed data for `/predict`, training data for `/train`, health checks for `/health`.
*   **Output:** Anomaly predictions for `/predict`, training status for `/train`, anomaly notifications to `iot_anomalies` Kafka topic, insertions to `anomaly_alerts` table.
*   **Logic:**
    *   **`/predict`:**
        *   Request body: `List[ProcessedDataSchema]`
        *   Response: `List[AnomalyPredictionSchema]` (containing `device_id`, `timestamp`, `anomaly_score`, `is_anomaly`).
        *   Model: Load a pre-trained `IsolationForest` or `OneClassSVM` model from `ml/models/anomaly_model.pkl`.
        *   Preprocessing: Ensure input data matches features expected by the model.
    *   **`/train`:**
        *   Request body: `List[ProcessedDataSchema]` (normal data for training).
        *   Asynchronous execution (e.g., using `BackgroundTasks` or Celery).
        *   Train a new model and save it to `ml/models/new_anomaly_model.pkl`.
        *   Update `ml/models/anomaly_model.pkl` after successful training.
        *   Log training progress.
    *   **`/model_info`:**
        *   Return current model's type, version, last training timestamp, expected features.
    *   **Kafka Consumer for Anomaly Notification:**
        *   Consumes from `processed_iot_data`.
        *   Calls the loaded ML model for real-time prediction.
        *   If `is_anomaly` is true, publishes a message to `iot_anomalies` topic and stores in `anomaly_alerts` table.
    *   Metrics: prediction latency, training duration, anomaly detection rate, Kafka publish errors.

### 4. Data Storage (PostgreSQL)
*   **Models:**
    *   `RawIoTData` (id, device_id, timestamp, temperature, humidity, pressure)
    *   `ProcessedIoTData` (id, device_id, timestamp, temp_ma_5min, temp_std_5min, humidity_ma_5min, humidity_std_5min, pressure_ma_5min, pressure_std_5min, temp_roc, humidity_roc, pressure_roc)
    *   `AnomalyAlert` (id, device_id, timestamp, anomaly_score, detected_features, model_version)
*   **Operations:** CRUD operations via SQLAlchemy.

### 5. Monitoring
*   **Prometheus:**
    *   Expose metrics from FastAPI app (`/metrics` endpoint).
    *   Custom metrics for Kafka producers/consumers (message rates, lag).
    *   Custom metrics for ML model (prediction latency, model reloads).
*   **Grafana:**
    *   Dashboards for visualizing all collected metrics.
    *   Alerts configuration based on thresholds.

### 6. Deployment (Docker & Docker Compose)
*   **`docker-compose.yaml`:**
    *   Define services for `zookeeper`, `kafka`, `postgresql`, `pgadmin` (optional), `ingestor`, `processor`, `api`, `prometheus`, `grafana`.
    *   Network configuration, volume mounts for persistence.
    *   Environment variables for inter-service communication (e.g., Kafka broker address for producers/consumers, DB connection string for Python apps).
*   **`Dockerfile`s:** Minimal, multi-stage builds for each Python service.

## Security Considerations:

*   **API Keys/Credentials:** Store securely using environment variables.
*   **Network Segmentation:** Use Docker networks to isolate services.
*   **Input Validation:** Strict Pydantic models for all API endpoints and Kafka message schemas.
*   **Error Handling:** Prevent information leakage in error responses.

## Performance Considerations:

*   **Asynchronous I/O:** Leverage FastAPI's async capabilities and `asyncio` for Kafka and DB operations.
*   **Batch Processing:** Process Kafka messages in batches where appropriate.
*   **Efficient Feature Engineering:** NumPy/Pandas for numerical operations.
*   **Kafka Tuning:** Optimize consumer/producer configurations (batch size, acks).

## Deliverables:

*   Fully functional microservice implemented as described.
*   Dockerfiles and `docker-compose.yaml` for complete deployment.
*   Comprehensive README.md for setup, usage, and API documentation.
*   Unit and integration tests.
*   Prometheus/Grafana configuration examples.
*   A clear explanation of how this architecture addresses scalability, real-time processing, and extensibility.

---

This task description is intentionally verbose and detailed, aiming to provide a complex scenario that will thoroughly test the LLM's ability to process and reason over a large context window. It describes multiple components, technologies, and interactions, requiring the LLM to maintain a consistent understanding across different parts of the problem.