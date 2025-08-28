"""API routes for the CSV converter application."""

import asyncio
import uuid
from pathlib import Path
from typing import List
from uuid import UUID

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..core.config import settings
from ..core.workflow import csv_conversion_workflow
from ..models.schemas import (
    ConversionJobRequest,
    ConversionJobResponse,
    ConversionResult,
    FileUploadResponse,
    InferenceJobRequest,
    JobStatus,
    JobStatusResponse,
    ListUserScriptsResponse,
    ListUsersResponse,
    OperationMode,
    UserScriptInfo,
)
from ..utils.file_handlers import validate_csv_file
from ..utils.job_manager import job_manager

router = APIRouter()

# Note: Job storage is now handled by the JobManager


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV file",
    description="Upload an input CSV or expected output CSV file for processing",
)
async def upload_file(
    file: UploadFile = File(..., description="CSV file to upload"),
    file_type: str = Form(..., description="Type of file: 'input' or 'expected_output'"),
) -> FileUploadResponse:
    """Upload a CSV file for processing."""

    if file_type not in ["input", "expected_output"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="file_type must be 'input' or 'expected_output'"
        )

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV file")

    if file.size and file.size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes",
        )

    # Create unique filename
    file_id = str(uuid.uuid4())
    filename = f"{file_type}_{file_id}_{file.filename}"
    file_path = settings.upload_dir / filename

    try:
        # Save the file
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        # Validate CSV content
        is_valid, error_msg = await validate_csv_file(file_path)
        if not is_valid:
            file_path.unlink()  # Clean up invalid file
            raise ValueError(error_msg)

        return FileUploadResponse(
            filename=filename,
            file_size=len(content),
            upload_path=str(file_path),
            message=f"Successfully uploaded {file_type} CSV file",
        )

    except Exception as e:
        # Clean up file if validation failed
        if file_path.exists():
            file_path.unlink()

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process CSV file: {str(e)}")


@router.post(
    "/convert",
    response_model=ConversionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start CSV conversion job",
    description="Start a new CSV conversion job with uploaded input and expected output files",
)
async def start_conversion_job(request: ConversionJobRequest) -> ConversionJobResponse:
    """Start a new CSV conversion job."""

    # Validate that files exist - support both upload_dir relative and full paths
    if request.use_full_paths:
        # Use full paths directly
        input_path = Path(request.input_file_path) if request.input_file_path else None
        expected_output_path = Path(request.expected_output_file_path) if request.expected_output_file_path else None

        if not input_path or not input_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Input file not found: {request.input_file_path}"
            )

        if request.mode == OperationMode.TRAINING:
            if not expected_output_path or not expected_output_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Expected output file not found: {request.expected_output_file_path}",
                )
    else:
        # Use upload_dir relative paths (legacy behavior)
        input_path = settings.upload_dir / request.input_filename

        if not input_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Input file not found: {request.input_filename}"
            )

        # For training mode, expected output file is required
        expected_output_path = None
        if request.mode == OperationMode.TRAINING:
            expected_output_path = settings.upload_dir / request.expected_output_filename
            if not expected_output_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Expected output file not found: {request.expected_output_filename}",
                )

    # Create new job
    job_id = uuid.uuid4()

    # Create job in job manager
    job_data = await job_manager.create_job(
        job_id=job_id,
        input_file=request.input_filename,
        expected_output_file=request.expected_output_filename,
        description=request.job_description,
        general_instructions=request.general_instructions,
        column_instructions=request.column_instructions,
        client_id=request.client_id,
        mode=request.mode,
    )

    # Start the CrewAI workflow in the background
    # Pass appropriate file identifiers based on mode
    if request.use_full_paths:
        input_file_identifier = request.input_file_path
        expected_output_identifier = request.expected_output_file_path
    else:
        input_file_identifier = request.input_filename
        expected_output_identifier = request.expected_output_filename

    asyncio.create_task(
        csv_conversion_workflow.execute_conversion_job(
            job_id,
            input_file_identifier,
            expected_output_identifier,
            request.job_description,
            request.general_instructions,
            request.column_instructions,
            request.use_full_paths,
        )
    )

    return ConversionJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        input_file=request.input_filename,
        expected_output_file=request.expected_output_filename,
        description=request.job_description,
        client_id=UUID(job_data["client_id"]),
        mode=request.mode,
        message=f"{request.mode.value.title()} job created successfully. Processing will begin shortly.",
    )


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Get the current status and progress of a conversion job",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get the status of a conversion job."""

    job_data = await job_manager.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    return JobStatusResponse(
        job_id=uuid.UUID(job_id),
        status=job_data["status"],
        input_file=job_data["input_file"],
        expected_output_file=job_data.get("expected_output_file"),
        description=job_data.get("description"),
        client_id=UUID(job_data["client_id"]),
        mode=OperationMode(job_data["mode"]),
        created_at=job_data["created_at"],
        updated_at=job_data.get("updated_at", job_data["created_at"]),
        current_step=job_data.get("current_step"),
        progress_details=job_data.get("progress_details"),
        error_message=job_data.get("error_message"),
    )


@router.get(
    "/jobs/{job_id}/result",
    response_model=ConversionResult,
    summary="Get job result",
    description="Get the final result of a completed conversion job",
)
async def get_job_result(job_id: str) -> ConversionResult:
    """Get the result of a conversion job."""

    job_data = await job_manager.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    if job_data["status"] not in [JobStatus.COMPLETED, JobStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job_data['status']}",
        )

    return ConversionResult(
        job_id=uuid.UUID(job_id),
        status=job_data["status"],
        success=job_data["status"] == JobStatus.COMPLETED,
        generated_script=job_data.get("generated_script"),
        test_results=job_data.get("test_results"),
        agent_results=job_data.get("agent_results", []),
        created_at=job_data["created_at"],
        completed_at=job_data.get("completed_at"),
        error_message=job_data.get("error_message"),
    )


@router.get(
    "/jobs",
    response_model=List[JobStatusResponse],
    summary="List all jobs",
    description="Get a list of all conversion jobs",
)
async def list_jobs() -> List[JobStatusResponse]:
    """Get a list of all conversion jobs."""

    all_jobs = await job_manager.list_jobs()
    jobs = []

    for job_id, job_data in all_jobs.items():
        jobs.append(
            JobStatusResponse(
                job_id=uuid.UUID(job_id),
                status=job_data["status"],
                input_file=job_data["input_file"],
                expected_output_file=job_data.get("expected_output_file"),
                description=job_data.get("description"),
                client_id=UUID(job_data["client_id"]),
                mode=OperationMode(job_data["mode"]),
                created_at=job_data["created_at"],
                updated_at=job_data.get("updated_at", job_data["created_at"]),
                current_step=job_data.get("current_step"),
                progress_details=job_data.get("progress_details"),
                error_message=job_data.get("error_message"),
            )
        )

    return jobs


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a job",
    description="Delete a conversion job and its associated files",
)
async def delete_job(job_id: str) -> None:
    """Delete a conversion job."""

    job_exists = await job_manager.delete_job(job_id)
    if not job_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    # Clean up temporary files
    from ..utils.file_handlers import cleanup_temp_files

    cleanup_temp_files(job_id)


# New endpoints for inference mode and user management


@router.post(
    "/inference",
    response_model=ConversionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start inference job",
    description="Start an inference job using a previously trained model for a client",
)
async def start_inference_job(request: InferenceJobRequest) -> ConversionJobResponse:
    """Start a new inference job using the latest trained model for a client."""

    # Validate that input file exists
    input_path = settings.upload_dir / request.input_filename
    if not input_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Input file not found: {request.input_filename}"
        )

    # Check if client has any trained models
    from ..utils.file_handlers import get_latest_user_script

    latest_script_path = get_latest_user_script(request.client_id)

    if not latest_script_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trained model found for client {request.client_id}. Please train a model first.",
        )

    # Create new inference job
    job_id = uuid.uuid4()

    job_data = await job_manager.create_job(
        job_id=job_id,
        input_file=request.input_filename,
        expected_output_file=None,  # Not needed for inference
        description=request.job_description,
        client_id=request.client_id,
        mode=OperationMode.INFERENCE,
    )

    # Start the inference workflow in the background
    asyncio.create_task(
        csv_conversion_workflow.execute_inference_job(
            job_id, request.input_filename, str(request.client_id), request.job_description
        )
    )

    return ConversionJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        input_file=request.input_filename,
        expected_output_file=None,
        description=request.job_description,
        client_id=request.client_id,
        mode=OperationMode.INFERENCE,
        message="Inference job created successfully. Processing will begin shortly.",
    )


@router.get(
    "/users",
    response_model=ListUsersResponse,
    summary="List all users",
    description="Get a list of all users who have trained models",
)
async def list_users() -> ListUsersResponse:
    """List all users who have generated scripts."""

    from ..utils.file_handlers import list_all_users

    users = list_all_users()

    return ListUsersResponse(users=users, total_count=len(users))


@router.get(
    "/users/{client_id}/scripts",
    response_model=ListUserScriptsResponse,
    summary="List user scripts",
    description="Get all scripts for a specific user, sorted by creation time",
)
async def list_user_scripts(client_id: UUID) -> ListUserScriptsResponse:
    """List all scripts for a specific user."""

    from datetime import datetime, timezone

    from ..utils.file_handlers import get_user_scripts

    scripts_data = get_user_scripts(client_id)

    # Convert to UserScriptInfo objects
    scripts = []
    for script_data in scripts_data:
        script_info = UserScriptInfo(
            script_name=script_data["script_name"],
            client_id=client_id,
            created_at=datetime.fromtimestamp(script_data["created_at"], tz=timezone.utc),
            file_path=script_data["file_path"],
        )
        scripts.append(script_info)

    latest_script = scripts[0] if scripts else None

    return ListUserScriptsResponse(client_id=client_id, scripts=scripts, latest_script=latest_script)


@router.get(
    "/jobs/{job_id}/inference-result",
    response_model=ConversionResult,
    summary="Get inference result",
    description="Get the final result of a completed inference job including output CSV",
)
async def get_inference_result(job_id: str) -> ConversionResult:
    """Get the result of an inference job."""

    job_data = await job_manager.get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    if job_data["status"] not in [JobStatus.COMPLETED, JobStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job_data['status']}",
        )

    # Get inference output if available
    inference_output = await job_manager.get_inference_output(job_id)

    return ConversionResult(
        job_id=uuid.UUID(job_id),
        status=job_data["status"],
        success=job_data["status"] == JobStatus.COMPLETED,
        generated_script=job_data.get("generated_script"),
        test_results=job_data.get("test_results"),
        agent_results=job_data.get("agent_results", []),
        created_at=job_data["created_at"],
        completed_at=job_data.get("completed_at"),
        error_message=job_data.get("error_message"),
        inference_output=inference_output,
    )
