"""Pydantic models for API request/response schemas."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BaseModelWithConfig(BaseModel):
    """Base model with JSON serialization configuration."""

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat() if v else None}, use_enum_values=True)


class JobStatus(str, Enum):
    """Status of a CSV conversion job."""

    PENDING = "pending"
    INITIALIZING = "initializing"
    UPLOADING = "uploading" 
    PROCESSING = "processing"
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationMode(str, Enum):
    """Operation mode for the CSV converter."""

    TRAINING = "training"
    INFERENCE = "inference"


class FileUploadResponse(BaseModel):
    """Response model for file upload."""

    filename: str
    file_size: int
    upload_path: str
    message: str


class ConversionJobRequest(BaseModel):
    """Request model for starting a CSV conversion job."""

    input_filename: str
    expected_output_filename: Optional[str] = None
    job_description: Optional[str] = Field(default=None, description="Optional description of the conversion task")
    general_instructions: Optional[str] = Field(
        default=None, description="General transformation instructions and data processing rules"
    )
    column_instructions: Optional[Dict[str, str]] = Field(
        default=None, description="Column-specific transformation instructions"
    )
    client_id: Optional[str] = Field(default=None, description="Optional client ID for user-specific training")
    mode: OperationMode = Field(default=OperationMode.TRAINING, description="Operation mode: training or inference")
    # New fields for direct file path support
    use_full_paths: Optional[bool] = Field(
        default=False, description="If True, treat filenames as full paths instead of upload_dir relative"
    )
    input_file_path: Optional[str] = Field(
        default=None, description="Full path to input file (when use_full_paths=True)"
    )
    expected_output_file_path: Optional[str] = Field(
        default=None, description="Full path to expected output file (when use_full_paths=True)"
    )


class InferenceJobRequest(BaseModel):
    """Request model for starting an inference job."""

    input_filename: str
    client_id: str = Field(description="Required client ID to identify the user's trained model")
    job_description: Optional[str] = Field(default=None, description="Optional description of the inference task")


class ConversionJobResponse(BaseModelWithConfig):
    """Response model for conversion job creation."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING
    input_file: str
    expected_output_file: Optional[str] = None  # Not required for inference mode
    description: Optional[str] = None
    client_id: str
    mode: OperationMode
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str


class JobStatusResponse(BaseModelWithConfig):
    """Response model for job status queries."""

    job_id: str
    status: JobStatus
    input_file: str
    expected_output_file: Optional[str] = None  # Not required for inference mode
    description: Optional[str] = None
    client_id: str
    mode: OperationMode
    created_at: datetime
    updated_at: datetime
    current_step: Optional[str] = None
    progress_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class AgentExecutionResult(BaseModel):
    """Result from an individual agent execution."""

    agent_name: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class ConversionResult(BaseModelWithConfig):
    """Final result of the CSV conversion process."""

    job_id: str
    status: JobStatus
    success: bool
    generated_script: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    agent_results: List[AgentExecutionResult] = []
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    inference_output: Optional[Dict[str, Any]] = None


class UserScriptInfo(BaseModelWithConfig):
    """Information about a user's generated script."""

    script_name: str
    client_id: str
    created_at: datetime
    file_path: str
    job_id: Optional[str] = None


class ListUsersResponse(BaseModelWithConfig):
    """Response model for listing users."""

    users: List[str]
    total_count: int


class ListUserScriptsResponse(BaseModelWithConfig):
    """Response model for listing user scripts."""

    client_id: str
    scripts: List[UserScriptInfo]
    latest_script: Optional[UserScriptInfo] = None


class ErrorResponse(BaseModelWithConfig):
    """Standard error response model."""

    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingJobRequest(BaseModel):
    """Request model for starting a training job."""

    user_id: str
    input_file: str
    expected_output_file: str
    job_title: str
    description: Optional[str] = None
    owner: str
    general_instructions: Optional[str] = None
    column_instructions: Optional[Dict[str, str]] = None
    job_id: Optional[str] = Field(
        default=None, 
        description="Optional job ID for replacing/updating an existing job. If provided, the existing job will be completely replaced."
    )


class InferenceRequest(BaseModel):
    """Request model for starting an inference job."""

    user_id: str = Field(description="Client ID to identify the user's trained model")
    job_id: str = Field(description="Job ID of the trained model to use for inference")
    input_file: str = Field(description="S3 URI, URL or Base64 file content encoded")


class InferenceResponse(BaseModelWithConfig):
    """Enhanced response model for inference job completion."""

    job_id: str
    status: JobStatus
    input_file: str
    client_id: str
    mode: OperationMode
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    # Enhanced fields with base64 content
    python_script_base64: Optional[str] = Field(
        default=None, description="Base64 encoded Python script content used for inference"
    )
    output_csv_base64: Optional[str] = Field(
        default=None, description="Base64 encoded output CSV file content"
    )
    output_s3_path: Optional[str] = Field(
        default=None, description="S3 path where the output CSV is stored"
    )
    script_s3_path: Optional[str] = Field(
        default=None, description="S3 path where the Python script is stored"
    )


class JobMetadata(BaseModelWithConfig):
    """Metadata for a training job to be saved in S3."""

    user_id: str
    user_name: str
    job_id: str
    job_title: str
    job_description: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    job_status: JobStatus
    script_path: Optional[str] = None
