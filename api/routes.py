"""API routes for the CSV converter application."""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import List

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from core.config import settings
from core.workflow import csv_conversion_workflow
from models.schemas import (
    ConversionJobRequest,
    ConversionJobResponse,
    ConversionResult,
    FileUploadResponse,
    InferenceJobRequest,
    InferenceRequest,
    JobStatus,
    JobStatusResponse,
    ListUserScriptsResponse,
    ListUsersResponse,
    OperationMode,
    UserScriptInfo,
    TrainingJobRequest,
)
from utils.file_handlers import validate_csv_file
from utils.job_manager import job_manager

router = APIRouter()
logger = logging.getLogger(__name__)
# Note: Job storage is now handled by the JobManager


@router.post(
    "/train",
    response_model=ConversionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Training Job",
    description="Starts a new training job, uploads files to S3, and kicks off the conversion workflow.",
)
async def start_training_job(request: TrainingJobRequest) -> ConversionJobResponse:
    """
    Starts a new training job:
    1. Creates a job with a unique ID.
    2. Sets up the necessary folder structure in S3.
    3. Uploads the input and expected output files to S3.
    4. Kicks off the background processing workflow.
    5. Returns the job information.
    """
    try:
        # Create and manage the job using the job manager
        job_data = await job_manager.create_training_job(request)
        job_id = job_data["job_id"]

        # Start the CrewAI workflow in the background
        asyncio.create_task(
            csv_conversion_workflow.execute_conversion_job(
                job_id,
                input_file_path=job_data["input_file"],
                expected_output_file_path=job_data["expected_output_file"],
                job_description=request.description,
                general_instructions=request.general_instructions,
                column_instructions=request.column_instructions,
                use_full_paths=True,  # We are using full S3 paths
            )
        )

        return ConversionJobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            input_file=job_data["input_file"],
            expected_output_file=job_data["expected_output_file"],
            description=request.description,
            client_id=job_data["client_id"],
            mode=OperationMode.TRAINING,
            message="Training job created successfully. Processing will begin shortly.",
        )
    except Exception as e:
        logger.error(f"Failed to start training job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training job: {str(e)}",
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
        job_id=job_id,
        status=job_data["status"],
        input_file=job_data["input_file"],
        expected_output_file=job_data.get("expected_output_file"),
        description=job_data.get("description"),
        client_id=job_data["client_id"],
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
        job_id=job_id,
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
                job_id=job_id,
                status=job_data["status"],
                input_file=job_data["input_file"],
                expected_output_file=job_data.get("expected_output_file"),
                description=job_data.get("description"),
                client_id=job_data["client_id"],
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
    from utils.file_handlers import cleanup_temp_files

    cleanup_temp_files(job_id)


# New endpoints for inference mode and user management





@router.post(
    "/inference/run",
    response_model=ConversionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Inference Job",
    description="Runs an inference job using a specified trained model and input file.",
)
async def run_inference_job(request: InferenceRequest) -> ConversionJobResponse:
    """
    Starts a new inference job:
    1. Creates a new job with a unique ID for tracking.
    2. Kicks off the background processing workflow for inference.
    3. Returns the job information.
    """
    try:
        # Create a new job for this inference task
        inference_job_id = str(uuid.uuid4())

        job_data = await job_manager.create_job(
            job_id=inference_job_id,
            input_file=request.input_file,
            client_id=request.user_id,
            mode=OperationMode.INFERENCE,
            description=f"Inference for job {request.job_id}",
        )

        # Start the inference workflow in the background
        asyncio.create_task(
            csv_conversion_workflow.run_inference_job(
                inference_job_id=inference_job_id,
                user_id=request.user_id,
                training_job_id=request.job_id,
                input_file=request.input_file,
            )
        )

        return ConversionJobResponse(
            job_id=inference_job_id,
            status=JobStatus.PENDING,
            input_file=request.input_file,
            client_id=request.user_id,
            mode=OperationMode.INFERENCE,
            message="Inference job created successfully. Processing will begin shortly.",
        )
    except Exception as e:
        logger.error(f"Failed to start inference job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start inference job: {str(e)}",
        )


@router.get(
    "/users",
    response_model=ListUsersResponse,
    summary="List all users",
    description="Get a list of all users who have trained models",
)
async def list_users() -> ListUsersResponse:
    """List all users who have generated scripts."""

    from utils.file_handlers import list_all_users

    users = list_all_users()

    return ListUsersResponse(users=users, total_count=len(users))


@router.get(
    "/users/{client_id}/scripts",
    response_model=ListUserScriptsResponse,
    summary="List user scripts",
    description="Get all scripts for a specific user, sorted by creation time",
)
async def list_user_scripts(client_id: str) -> ListUserScriptsResponse:
    """List all scripts for a specific user."""

    from datetime import datetime, timezone

    from utils.file_handlers import get_user_scripts

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



