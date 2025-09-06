# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is an AI-powered CSV to CSV converter using CrewAI agents. The system converts input CSV files to specific output formats using a multi-agent workflow with planning, code generation, and testing phases. It supports both training mode (learning from examples) and inference mode (applying learned transformations).

## Core Architecture

### High-Performance Multi-Process System (v2.0)
The application now uses a sophisticated multi-process architecture to handle concurrent training requests:

- **FastAPI Server** (Main Process): Handles all API requests, authentication, and S3 operations
- **ProcessPoolExecutor** (`core/workflow_executor.py`): Manages worker processes with intelligent queuing
- **Worker Processes** (Up to 32): Isolated processes running CrewAI workflows
- **Queue Management**: Automatic queuing when all workers are busy

### Multi-Agent System
Each worker process runs a three-agent CrewAI workflow:

- **Planner Agent** (`agents/planner_agent.py`): Analyzes input/output CSV files and creates transformation plans
- **Coder Agent** (`agents/coder_agent.py`): Generates Python scripts based on the plan
- **Tester Agent** (`agents/tester_agent.py`): Validates generated scripts against expected output

The agents communicate through feedback loops, allowing up to 5 improvement cycles per job.

### Key Components

- **Workflow Executor** (`core/workflow_executor.py`): High-performance process pool manager for CrewAI workflows
- **Workflow Orchestration** (`core/workflow.py`): Main orchestrator that manages the multi-agent workflow
- **Job Management** (`utils/job_manager.py`): Persistent job state management with JSON storage
- **File Handling** (`utils/file_handlers.py`): S3 integration for file storage and retrieval
- **Agent Factory** (`agents/agent_factory.py`): Singleton pattern for agent creation and management

### API Structure
FastAPI application with:
- **Training Endpoint**: `/api/v1/train` - Creates training jobs from input/expected output pairs
- **Inference Endpoint**: `/api/v1/inference/run` - Runs inference using trained models
- **Queue Status**: `/api/v1/queue/status` - Monitor workflow queue and worker utilization
- **Job Management**: User job listing and deletion endpoints
- **Security**: All API endpoints require `X-API-KEY` authentication (except `/health`)

## Development Commands

### Setup and Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Or use uv (recommended for script execution)
pip install uv
```

### Running the Application
```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
python main.py

# Access API documentation
# http://localhost:8000/docs
```

### Testing
```bash
# Run the test suite
pytest

# Run specific test file
python test_api.py

# Test individual endpoints
python -c "from test_api import test_training_endpoint; test_training_endpoint()"

# Test concurrent request handling
python test_concurrent_requests.py

# Test new workflow executor (multiprocess concurrency)
python test_workflow_executor.py
```

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy .
```

## Environment Configuration

Required environment variables in `.env`:
```
OPENAI_API_KEY=your_openai_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_BUCKET_NAME=your_s3_bucket_name
FASTAPI_AND_WEP_APP_SECRET_KEY=your_secret_api_key
```

Optional configuration:
```
OPENAI_MODEL=gpt-4  # Default model
OPENAI_TEMPERATURE=0.1  # Default temperature
LOG_LEVEL=INFO  # Logging level
DEBUG=true  # Debug mode
```

## Key Patterns and Conventions

### Agent Communication
- Agents pass structured feedback through `agent_feedback` dictionaries
- Previous attempt results are stored for learning in subsequent cycles
- Each agent has standardized `execute_task()` method returning success/error status

### File Path Handling
- Uses `use_full_paths` parameter to distinguish between local uploads and S3 paths
- S3 paths follow pattern: `{user_id}/{job_id}/{type}/{filename}`
- Local temporary files are cleaned up automatically

### Job Lifecycle
1. Job creation with unique UUID
2. File upload to S3 (training mode)
3. Multi-agent workflow execution with feedback loops
4. Script storage and metadata persistence
5. Job completion or failure handling

### Error Handling
- Comprehensive exception handling with structured error responses
- Agent-specific error feedback for improvement cycles
- Timeout protection for script execution (5 minutes)

### Persistent Storage
- Jobs persisted to `temp/jobs.json` with datetime serialization
- S3 metadata stored alongside files
- Generated scripts saved both locally and in S3

## Development Tips

### Adding New Agents
1. Extend `BaseCSVAgent` in `agents/base_agent.py`
2. Implement `execute_task()` method
3. Add factory method in `AgentFactory`
4. Update workflow orchestration in `core/workflow.py`

### Testing New Endpoints
Use `test_api.py` as template for API testing. The file includes examples for:
- Training job creation with S3 files
- Inference job execution  
- Base64 encoded file handling
- User job management

### Working with S3 Integration
- Files support S3 URIs, URLs, and Base64 encoding
- Use `utils/file_handlers.py` for S3 operations
- Temporary directories are automatically cleaned up

### Debugging Workflow Issues
- Set `DEBUG=true` for verbose CrewAI agent logs
- Check `temp/jobs.json` for job state persistence
- Monitor agent feedback loops in workflow execution
- Use structured logging with loguru for component-specific logs
- **Multiprocess Debugging**:
  - Monitor worker processes: `ps aux | grep python`
  - Check queue status: `curl -H "X-API-KEY: YOUR_KEY" http://localhost:8000/api/v1/queue/status`
  - Worker logs include process IDs for isolation tracking
  - Each worker creates fresh event loops to prevent asyncio conflicts

### Performance and Concurrency
- **True Multi-Process Concurrency**: Training jobs run in isolated processes, never blocking the API
- **Intelligent Queuing**: ProcessPoolExecutor with up to 32 workers and automatic queuing
- **Event Loop Isolation**: Each worker process creates fresh asyncio components to prevent event loop conflicts
- **Process-Safe Instances**: Fresh `JobManager` and `AgentFactory` instances per worker to avoid shared asyncio objects
- **All S3 operations are async** using `run_in_executor()` to prevent blocking
- **File I/O operations use `aiofiles`** for async file handling
- **JobManager uses separate read/write locks** for better concurrency
- **Read operations** (get_job, list_jobs) don't block write operations
- **Worker Process Isolation**: Individual worker crashes don't affect the main API
- **Real-time Monitoring**: Queue status endpoint (`/api/v1/queue/status`) for monitoring
- **Secure Authentication**: All workflow management endpoints require API key authentication

## Common Operations

### Manual Job Creation
```python
from utils.job_manager import job_manager
job_data = await job_manager.create_job(
    job_id="test-job",
    input_file="input.csv", 
    client_id="test-user"
)
```

### Submitting Training Workflow
```python
from core.workflow_executor import workflow_executor
success = await workflow_executor.submit_workflow(
    job_id="training-job",
    input_file_path="path/to/input.csv",
    expected_output_file_path="path/to/expected.csv"
)
```

### Monitoring Queue Status
```python
from core.workflow_executor import workflow_executor
status = await workflow_executor.get_queue_status()
print(f"Active workers: {status['active_jobs']}/{status['max_workers']}")
```

### Running Inference
```python
from core.workflow import csv_conversion_workflow
result = await csv_conversion_workflow.execute_inference_job(
    job_id="inference-job",
    input_file_path="path/to/input.csv",
    client_id="user-id"
)
```

### Agent Testing
```python
from agents.agent_factory import agent_factory
planner = agent_factory.get_planner_agent()
result = await planner.execute_task(task_data)
```
