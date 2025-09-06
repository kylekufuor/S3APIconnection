# AI CSV Converter

AI-powered CSV to CSV converter using CrewAI agents with high-performance multi-process architecture

## API Endpoints

### `POST /api/v1/train`

**Summary:** Start Training Job

**Description:** Starts a new training job, uploads files to S3, and kicks off the conversion workflow.

**Security:** Requires `X-API-KEY` header.

**Request Body:**

```json
{
  "user_id": "string",
  "input_file": "string",
  "expected_output_file": "string",
  "job_title": "string",
  "description": "string | null",
  "owner": "string",
  "general_instructions": "string | null",
  "column_instructions": {
    "additionalProperties": "string"
  }
}
```

**Responses:**

*   `202 Accepted`: Successful Response (ConversionJobResponse)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `POST /api/v1/inference/run`

**Summary:** Run Inference Job

**Description:** Runs an inference job using a specified trained model and input file.

**Security:** Requires `X-API-KEY` header.

**Request Body:**

```json
{
  "user_id": "string",
  "job_id": "string",
  "input_file": "string"
}
```

**Responses:**

*   `202 Accepted`: Successful Response (ConversionJobResponse)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /api/v1/queue/status`

**Summary:** Get workflow queue status

**Description:** Get the current status of the workflow processing queue and worker utilization.

**Security:** Requires `X-API-KEY` header.

**Responses:**

*   `200 OK`: Queue status with worker utilization metrics
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /api/v1/users/{client_id}/jobs`

**Summary:** List all jobs for a user

**Description:** Get a list of all jobs for a specific user by reading metadata from S3.

**Security:** Requires `X-API-KEY` header.

**Parameters:**

*   `client_id` (path): string

**Responses:**

*   `200 OK`: Successful Response (List of job metadata dictionaries)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /`

**Summary:** Root

**Description:** Root endpoint - redirects to API documentation.

**Responses:**

*   `200 OK`: Successful Response

### `GET /health`

**Summary:** Health Check

**Description:** Health check endpoint.

**Responses:**

*   `200 OK`: Successful Response

## How to Run the Application

1.  **Set up your environment variables:**

    Create a `.env` file in the root directory of the project with the following content:

    ```
    OPENAI_API_KEY=your_openai_api_key
    AWS_ACCESS_KEY_ID=your_aws_access_key_id
    AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
    AWS_BUCKET_NAME=your_s3_bucket_name
    FASTAPI_AND_WEP_APP_SECRET_KEY=your_secret_api_key
    ```

    Replace the placeholder values with your actual keys and bucket name.

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    (Note: You might need to create a `requirements.txt` file first if it doesn't exist. You can generate it using `pip freeze > requirements.txt`)

3.  **Run the application:**

    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    Or, if you are running it from the `main.py` file directly:

    ```bash
    python main.py
    ```

    The API documentation will be available at `http://localhost:8000/docs`.

## Architecture Overview

### Current Multi-Process Architecture (v2.0)

The API now uses a high-performance multi-process architecture to handle concurrent training requests without blocking:

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server (Main Process)            │
├─────────────────────────────────────────────────────────────┤
│  ├── API Endpoints (Async)                                  │
│  ├── Authentication & Validation                            │
│  ├── S3 File Operations (Async)                             │
│  └── Job Management (Async)                                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ ProcessPoolExecutor Queue
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Worker Process Pool (32 Workers Max)           │
├─────────────────────────────────────────────────────────────┤
│  Worker 2: CrewAI Workflow (Planner → Coder → Tester)       │
│  Worker 1: CrewAI Workflow (Planner → Coder → Tester)       │
│  Worker 3: CrewAI Workflow (Planner → Coder → Tester)       │
│  ...                                                        │
│  Worker N: CrewAI Workflow (Planner → Coder → Tester)       │
└─────────────────────────────────────────────────────────────┘
```

### Key Benefits

1. **🚀 True Concurrency**: Training jobs run in isolated processes, never blocking the API
2. **📈 High Throughput**: Multiple training jobs can run simultaneously 
3. **💪 Resource Optimization**: Automatic worker scaling based on CPU cores
4. **🔄 Intelligent Queuing**: Jobs queue automatically when all workers are busy
5. **📀 Real-time Monitoring**: Queue status and worker utilization endpoints
6. **🛡️ Fault Isolation**: Worker crashes don't affect the main API server
7. **🔒 Secure Access**: All workflow endpoints require API key authentication
8. **⚙️ Event Loop Isolation**: Fresh asyncio components per worker prevent event loop conflicts

### Performance Estimates

#### Current Multi-Process Architecture
**Server Specs**: 32 vCPU, 32GB RAM

- **Max Concurrent Training Jobs**: 32 (one per worker)
- **Training Job Duration**: 2-5 minutes average
- **API Response Time**: <100ms (never blocked by training)
- **Throughput**: ~6-15 training jobs per minute
- **Queue Capacity**: Unlimited (memory permitting)
- **Fast Operations**: Health checks, job listings remain <1s always

**Estimated Performance**:
```
Training Requests per Second: 0.1-0.25 RPS sustainable
Peak Burst Handling: Up to 32 simultaneous jobs
API Responsiveness: Always <100ms for non-training endpoints
Memory Usage: ~1GB per active training job (32GB total capacity)
Concurrency: True multiprocess isolation prevents blocking
Event Loop Safety: Fresh asyncio components per worker
```

## Future Architecture: Distributed Worker System

### Planned Enhancement: Celery/Redis Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server Cluster                   │
├─────────────────────────────────────────────────────────────┤
│  ├── Multiple API Instances (Load Balanced)                 │
│  ├── Instant Response (<50ms)                               │
│  └── Job Submission Only                                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ Redis Queue
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  Redis Message Broker                       │
├─────────────────────────────────────────────────────────────┤
│  ├── Job Queue Management                                   │
│  ├── Result Storage                                         │
│  ├── Worker Health Monitoring                               │
│  └── Retry & Error Handling                                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ Multiple Worker Nodes
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Celery Worker Cluster                          │
├─────────────────────────────────────────────────────────────┤
│  Node 1: 32 Workers × CrewAI Workflows                      │
│  Node 2: 32 Workers × CrewAI Workflows                      │
│  Node 3: 32 Workers × CrewAI Workflows                      │
│  ...                                                        │
│  Node N: 32 Workers × CrewAI Workflows                      │
└─────────────────────────────────────────────────────────────┘
```

### Enhanced Performance Estimates
**Distributed Setup**: 4 worker nodes × 32 workers each = 128 concurrent jobs

- **Max Concurrent Training Jobs**: 128+ (horizontal scaling)
- **API Response Time**: <50ms (completely decoupled)
- **Throughput**: ~25-65 training jobs per minute
- **Fault Tolerance**: Individual worker/node failures don't affect system
- **Auto-scaling**: Dynamic worker allocation based on queue depth
- **Geographic Distribution**: Workers can be in different regions

**Estimated Performance**:
```
Training Requests per Second: 0.4-1.0 RPS sustainable  
Peak Burst Handling: 128+ simultaneous jobs
API Responsiveness: Always <50ms for all endpoints
Horizontal Scaling: Add nodes to increase capacity linearly
Fault Tolerance: 99.9% uptime with proper redundancy
```

### Migration Benefits (Current vs Future)

| Metric                | Current (Multi-Process) | Future (Celery/Redis) | Improvement       |
| --------------------- | ----------------------- | --------------------- | ----------------- |
| Max Concurrent Jobs   | 32                      | 128+                  | 4x+               |
| API Response Time     | <100ms                  | <50ms                 | 2x faster         |
| Throughput (jobs/min) | 6-15                    | 25-65                 | 4x+               |
| Fault Tolerance       | Single point of failure | Distributed           | High availability |
| Scaling               | Vertical only           | Horizontal            | Unlimited         |
| Maintenance           | Restart affects all     | Rolling updates       | Zero downtime     |

## How to Run Tests

```bash
pytest
```

### Concurrency Testing

```bash
# Test concurrent request handling
python test_concurrent_requests.py

# Test focused concurrency (pure API performance)
python test_concurrency_focused.py

# Test new multiprocess workflow executor
python test_workflow_executor.py

# Check workflow queue status (requires API key)
curl -H "X-API-KEY: YOUR_API_KEY" http://localhost:8000/api/v1/queue/status
```

(Note: Ensure you have `pytest` installed: `pip install pytest`)
