# AI CSV Converter

AI-powered CSV to CSV converter using CrewAI agents with high-performance multi-process architecture

## API Endpoints

### `POST /api/v1/train`

**Summary:** Start Training Job

**Description:** Starts a new training job or replaces an existing one. Uploads files to S3 and kicks off the conversion workflow using high-performance multi-process architecture.

**Security:** Requires `X-API-KEY` header.

**Request Body:**

```json
{
  "user_id": "string",
  "job_id": "string | null",
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

**Job ID Behavior:**
- **Without `job_id`**: Creates a new job with auto-generated UUID
- **With `job_id`**: Replaces existing job (deletes S3 folder and recreates)

**Responses:**

*   `202 Accepted`: Successful Response (ConversionJobResponse)
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `POST /api/v1/inference/run`

**Summary:** Run Inference Job

**Description:** Runs an inference job using a specified trained model and input file. Returns the Python script and output CSV as base64 encoded strings.

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

*   `200 OK`: Successful Response (InferenceResponse) - includes base64 encoded Python script and output CSV
*   `500 Internal Server Error`: Failed to run inference job
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /api/v1/queue/status`

**Summary:** Get workflow queue status

**Description:** Get the current status of the workflow processing queue and worker utilization.

**Security:** Requires `X-API-KEY` header.

**Responses:**

*   `200 OK`: Queue status with worker utilization metrics
*   `500 Internal Server Error`: Failed to get queue status
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

**Example Response:**
```json
{
  "status": "healthy",
  "queue_info": {
    "max_workers": 32,
    "active_jobs": 5,
    "available_workers": 27,
    "queue_size": 0
  },
  "capacity_utilization": {
    "workers_busy_percent": 15.625,
    "can_accept_new_jobs": true,
    "estimated_wait_time_minutes": 0
  }
}
```

### `GET /api/v1/{client_id}/{job_id}`

**Summary:** Get specific job metadata

**Description:** Retrieve the complete job metadata JSON for a specific job belonging to a user. Returns metadata from S3 if available, otherwise returns empty JSON {}.

**Security:** Requires `X-API-KEY` header.

**Parameters:**

*   `client_id` (path): string - The user/client ID
*   `job_id` (path): string - The specific job ID

**Responses:**

*   `200 OK`: Job metadata JSON or empty {} if not found in S3
*   `403 Forbidden`: Access denied to job metadata
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

### `DELETE /api/v1/delete/job/{user_id}/{job_id}`

**Summary:** Delete a specific job folder

**Description:** Deletes a specific job folder and all its contents from the S3 bucket.

**Security:** Requires `X-API-KEY` header.

**Parameters:**

*   `user_id` (path): string - The user ID
*   `job_id` (path): string - The job ID to delete

**Responses:**

*   `204 No Content`: Job deleted successfully
*   `500 Internal Server Error`: Failed to delete job folder
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `DELETE /api/v1/delete/user/{user_id}`

**Summary:** Delete a user's entire folder

**Description:** Deletes a user's entire folder and all its contents from the S3 bucket.

**Security:** Requires `X-API-KEY` header.

**Parameters:**

*   `user_id` (path): string - The user ID whose folder to delete

**Responses:**

*   `204 No Content`: User folder deleted successfully
*   `500 Internal Server Error`: Failed to delete user folder
*   `422 Unprocessable Entity`: Validation Error (HTTPValidationError)

### `GET /`

**Summary:** Root

**Description:** Root endpoint - redirects to API documentation.

**Security:** No authentication required.

**Responses:**

*   `200 OK`: Redirects to `/docs`

### `GET /health`

**Summary:** Health Check

**Description:** Health check endpoint for monitoring application status.

**Security:** No authentication required.

**Responses:**

*   `200 OK`: Returns application status, name, and version

**Example Response:**
```json
{
  "status": "healthy",
  "app_name": "AI CSV Converter",
  "version": "1.0.0"
}
```

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

## AI Agents System

This application uses a sophisticated multi-agent system powered by CrewAI to handle CSV transformation tasks. The system employs three specialized AI agents that work together in a coordinated workflow to analyze, plan, code, and validate CSV transformations.

### Agent Overview

The three-agent system follows a sequential workflow with feedback loops:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Planner       │───▶│     Coder       │───▶│     Tester      │
│     Agent       │    │     Agent       │    │     Agent       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                          Feedback Loop
                        (Up to 5 iterations)
```

### 1. Planner Agent (`agents/planner_agent.py`)

**Purpose**: Analyzes input and expected output CSV files to create detailed transformation plans.

**Key Responsibilities**:
- **CSV Structure Analysis**: Examines column names, data types, and sample data
- **Transformation Planning**: Creates step-by-step transformation instructions
- **Pattern Recognition**: Identifies data cleaning, formatting, and mapping requirements
- **DateTime Handling Planning**: Plans robust datetime transformations with timezone handling
- **Column Instruction Processing**: Incorporates user-provided column-specific instructions
- **Data Quality Assessment**: Identifies potential data issues and transformation challenges

**Specialized Capabilities**:
- **Mixed Date Format Detection**: Plans for handling various date formats within the same column
- **Timezone Normalization**: Plans UTC conversion and timezone-aware processing
- **Data Type Inference**: Determines appropriate data types for transformation
- **Missing Value Strategy**: Plans handling of null, empty, and invalid values
- **Column Mapping Logic**: Maps input columns to output columns with transformations

**Output**: Detailed transformation plan with specific steps, data type conversions, and implementation guidance.

**Example Plan Output**:
```python
{
    "transformation_steps": [
        {
            "step": 1,
            "action": "datetime_conversion",
            "column": "order_date",
            "details": "Convert mixed date formats to YYYY-MM-DD using pd.to_datetime with utc=True"
        },
        {
            "step": 2,
            "action": "column_mapping",
            "source": "customer_name",
            "target": "client_name",
            "transformation": "title_case_formatting"
        }
    ],
    "data_quality_checks": [...],
    "expected_challenges": [...]
}
```

### 2. Coder Agent (`agents/coder_agent.py`)

**Purpose**: Generates Python scripts to implement the transformation plan created by the Planner Agent.

**Key Responsibilities**:
- **Script Generation**: Creates complete Python transformation scripts
- **Pandas Implementation**: Uses pandas for efficient data manipulation
- **Error Handling**: Implements robust error handling and data validation
- **DateTime Processing**: Implements datetime conversions with proper timezone handling
- **Data Type Enforcement**: Ensures proper data type conversions and validations
- **Performance Optimization**: Generates efficient, vectorized pandas operations

**Specialized Code Patterns**:
- **Robust DateTime Handling**:
  ```python
  # Always uses utc=True for timezone safety
  df['date_column'] = pd.to_datetime(df['date_column'], errors='coerce', utc=True)
  df['date_column'] = df['date_column'].dt.strftime('%Y-%m-%d')
  ```
- **Mixed Format Handling**: Implements fallback parsing for multiple date formats
- **Data Validation**: Adds comprehensive data quality checks
- **Memory Efficiency**: Optimizes for large CSV file processing
- **Error Recovery**: Implements graceful handling of data conversion errors

**Code Quality Features**:
- **Type Safety**: Proper data type handling and conversion
- **Error Logging**: Detailed error reporting and logging
- **Performance Monitoring**: Execution time tracking
- **Data Integrity Checks**: Validation of transformation results
- **Modular Design**: Clean, maintainable code structure

**Output**: Complete Python script ready for execution with error handling and logging.

### 3. Tester Agent (`agents/tester_agent.py`)

**Purpose**: Validates the generated code by executing it and comparing results with expected output.

**Key Responsibilities**:
- **Script Execution**: Safely runs the generated Python code
- **Result Validation**: Compares actual output with expected CSV
- **Error Detection**: Identifies runtime errors, data mismatches, and quality issues
- **Performance Monitoring**: Tracks execution time and resource usage
- **Detailed Reporting**: Provides comprehensive test results and feedback
- **Improvement Suggestions**: Recommends fixes for failed tests

**Validation Checks**:
- **Structure Validation**: Column names, count, and order verification
- **Data Type Verification**: Ensures correct data types in output
- **Content Accuracy**: Cell-by-cell comparison with expected results
- **Data Quality Metrics**: Checks for null values, duplicates, and anomalies
- **Format Compliance**: Validates date formats, string formatting, etc.
- **Statistical Validation**: Compares data distributions and summary statistics

**Safety Features**:
- **Sandboxed Execution**: Secure code execution environment
- **Timeout Protection**: Prevents infinite loops (5-minute timeout)
- **Resource Monitoring**: Memory and CPU usage tracking
- **Error Isolation**: Prevents test failures from affecting the system

**Feedback Mechanism**:
```python
{
    "test_passed": False,
    "errors_found": [
        {
            "type": "datetime_format_error",
            "column": "order_date",
            "issue": "Mixed date formats causing conversion errors",
            "suggestion": "Use pd.to_datetime with mixed format handling"
        }
    ],
    "performance_metrics": {
        "execution_time": "2.3 seconds",
        "memory_usage": "45MB",
        "rows_processed": 10000
    }
}
```

### Agent Workflow & Feedback Loop

#### Standard Workflow:
1. **Planner Agent** analyzes input/output CSVs and creates transformation plan
2. **Coder Agent** generates Python script based on the plan
3. **Tester Agent** executes the script and validates results

#### Feedback & Improvement Cycle:
If the Tester Agent finds issues, the system initiates improvement cycles:

1. **Error Analysis**: Tester provides detailed feedback about failures
2. **Plan Refinement**: Planner adjusts strategy based on test results
3. **Code Improvement**: Coder generates improved script
4. **Re-testing**: Tester validates the improved solution

**Maximum Iterations**: Up to 5 improvement cycles per job to ensure quality

#### Agent Communication Protocol:
```python
# Agents communicate through structured feedback dictionaries
agent_feedback = {
    "previous_attempts": [...],  # History of attempts
    "current_errors": [...],     # Current issues to address
    "suggestions": [...],        # Specific improvement recommendations
    "context": {...}             # Additional context and metadata
}
```

### Agent Factory (`agents/agent_factory.py`)

**Purpose**: Singleton pattern for efficient agent creation and management.

**Features**:
- **Singleton Design**: Ensures consistent agent instances across the application
- **Agent Caching**: Reuses agent instances for better performance
- **Configuration Management**: Centralizes agent configuration and settings
- **Process Safety**: Creates fresh instances per worker process to avoid asyncio conflicts

**Usage**:
```python
from agents.agent_factory import agent_factory

# Get agent instances
planner = agent_factory.get_planner_agent()
coder = agent_factory.get_coder_agent() 
tester = agent_factory.get_tester_agent()
```

### Column Instructions Processing

**Overview**: The system supports user-provided column-specific instructions that guide the transformation process.

#### Input Format:
```json
{
  "column_instructions": {
    "customer_name": "Convert to title case",
    "order_date": "Convert to YYYY-MM-DD format",
    "price": "Round to 2 decimal places",
    "status": ""  // Empty instruction
  }
}
```

#### Default Value Handling:
When a column instruction is empty or null, the system automatically applies the default instruction:
**"SAME AS INPUT"** - indicating the column should be preserved as-is.

#### Agent Integration:

**Planner Agent**:
- Incorporates column instructions into the transformation plan
- Applies default "SAME AS INPUT" for empty instructions
- Validates instructions against column availability
- Plans complex transformations based on specific column requirements

**Coder Agent**:
- Implements column-specific transformations in the generated Python script
- Handles "SAME AS INPUT" by preserving original column data
- Creates conditional logic for different column transformation types
- Ensures proper error handling for column-specific operations

**Tester Agent**:
- Validates that column instructions were properly implemented
- Verifies "SAME AS INPUT" columns remain unchanged
- Tests column-specific transformation accuracy
- Reports instruction compliance in test results

#### Example Processing:
```python
# Input column_instructions processing
column_instructions = {
    "name": "Convert to uppercase",
    "date": "",  # Will become "SAME AS INPUT"
    "amount": "Round to nearest integer"
}

# After default processing
processed_instructions = {
    "name": "Convert to uppercase",
    "date": "SAME AS INPUT",  # Default applied
    "amount": "Round to nearest integer"
}
```

### Training vs Inference Modes

#### Training Mode:
- Uses all three agents in the feedback loop
- Learns from input/output examples
- Generates and saves transformation scripts
- Validates against expected output
- Stores successful transformations for future use

#### Inference Mode:
- Reuses previously generated and validated transformation scripts
- Applies learned transformations to new input data
- Faster execution (no planning or coding phase)
- Consistent results based on training

### Performance Characteristics

**Agent Execution Times**:
- **Planner Agent**: 30-60 seconds (analysis and planning)
- **Coder Agent**: 45-90 seconds (script generation)
- **Tester Agent**: 15-30 seconds (execution and validation)
- **Total Cycle**: 2-5 minutes (including feedback loops)

**Resource Usage**:
- **Memory**: ~1GB per active workflow
- **CPU**: Intensive during agent reasoning phases
- **I/O**: Heavy S3 operations for file handling

**Scalability**:
- **Concurrent Workflows**: Up to 32 simultaneous agent workflows
- **Process Isolation**: Each workflow runs in a separate worker process
- **Queue Management**: Automatic queuing when all workers are busy

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
