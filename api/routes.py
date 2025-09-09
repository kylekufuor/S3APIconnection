"""API routes for the CSV converter application."""

import asyncio
import logging
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

from core.workflow_executor import workflow_executor
from models.schemas import (
    ConversionJobResponse,
    InferenceRequest,
    InferenceResponse,
    JobStatus,
    OperationMode,
    TrainingJobRequest,
)
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
        # Check if this is a job replacement request
        if request.job_id:
            logger.info(f"🔄 Job replacement request for job: {request.job_id}")
        else:
            logger.info(f"⚡ New training job creation request")
            
        # ⚡ SONIC SPEED: Create job record instantly (no S3 operations)
        job_data = await job_manager.create_training_job_fast(request)
        job_id = job_data["job_id"]
        
        # 🚀 Submit to worker process (includes S3 setup + CrewAI workflow)
        workflow_submitted = await workflow_executor.submit_workflow(
            job_id,
            request_data=request,  # Pass full request for S3 operations
            input_file_path=job_data["input_file"],  # Original S3 paths
            expected_output_file_path=job_data["expected_output_file"],
            job_description=request.description,
            general_instructions=request.general_instructions,
            column_instructions=request.column_instructions,
            use_full_paths=True,
            perform_s3_setup=True,  # Flag to handle S3 in worker
        )
        
        if not workflow_submitted:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to submit workflow job. Server may be overloaded.",
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


@router.post(
    "/inference/run",
    response_model=InferenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Inference Job",
    description="Runs an inference job using a specified trained model and input file. Returns the Python script and output CSV as base64 encoded strings.",
)
async def run_inference_job(request: InferenceRequest) -> InferenceResponse:
    """
    Runs an inference job and waits for completion:
    1. Creates a new job with a unique ID for tracking.
    2. Executes the inference workflow synchronously.
    3. Returns the job information along with base64 encoded Python script and output CSV.
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

        # Execute the inference workflow and wait for completion
        from core.workflow import csv_conversion_workflow
        
        # Run inference job synchronously to get the results
        inference_result = await csv_conversion_workflow.run_inference_job(
            inference_job_id=inference_job_id,
            user_id=request.user_id,
            training_job_id=request.job_id,
            input_file=request.input_file,
        )

        if inference_result["success"]:
            return InferenceResponse(
                job_id=inference_job_id,
                status=JobStatus.COMPLETED,
                input_file=request.input_file,
                client_id=request.user_id,
                mode=OperationMode.INFERENCE,
                message="Inference job completed successfully.",
                python_script_base64=inference_result.get("python_script_base64"),
                output_csv_base64=inference_result.get("output_csv_base64"),
                output_s3_path=inference_result.get("output_s3_path"),
                script_s3_path=inference_result.get("script_s3_path"),
            )
        else:
            # Return failed response but include script content if available
            return InferenceResponse(
                job_id=inference_job_id,
                status=JobStatus.FAILED,
                input_file=request.input_file,
                client_id=request.user_id,
                mode=OperationMode.INFERENCE,
                message=f"Inference job failed: {inference_result.get('error', 'Unknown error')}",
                python_script_base64=inference_result.get("python_script_base64"),
                output_csv_base64=inference_result.get("output_csv_base64"),
                output_s3_path=inference_result.get("output_s3_path"),
                script_s3_path=inference_result.get("script_s3_path"),
            )
    except Exception as e:
        logger.error(f"Failed to start inference job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start inference job: {str(e)}",
        )


@router.get(
    "/{client_id}/{job_id}",
    response_model=Dict[str, Any],
    summary="Get specific job metadata",
    description="Retrieve the complete job metadata JSON for a specific job belonging to a user.",
)
async def get_job_metadata(client_id: str, job_id: str) -> Dict[str, Any]:
    """
    Get detailed metadata for a specific job.
    
    Retrieves the complete job_metadata.json file from S3. If the metadata
    file doesn't exist in S3, returns an empty JSON object {}.
    
    Returns either:
    - Complete job metadata from S3 containing job details, status, processing history, etc.
    - Empty JSON object {} if metadata file not found in S3
    
    Raises HTTPException for other errors (access denied, server errors, etc.)
    """
    try:
        logger.info(f"📄 Retrieving job metadata for {client_id}/{job_id}")
        
        # First, try to get metadata from S3 (most complete)
        try:
            from utils.file_handlers import get_job_metadata_from_s3
            logger.info(f"Calling get_job_metadata_from_s3 for {client_id}/{job_id}")
            job_metadata = await get_job_metadata_from_s3(client_id, job_id)
            logger.info(f"✅ Retrieved metadata from S3 for job {job_id}")
            return job_metadata
            
        except HTTPException as s3_error:
            # If S3 metadata not found, return empty JSON
            if s3_error.status_code == 404:
                logger.info(f"📂 S3 metadata not found for {client_id}/{job_id}, returning empty JSON")
                return {}
            else:
                # Re-raise other S3 errors (access denied, server errors, etc.)
                raise s3_error
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting job metadata: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job metadata"
        )


@router.get(
    "/users/{client_id}/jobs",
    response_model=List[Dict[str, Any]],
    summary="List all jobs for a user",
    description="Get a list of all jobs for a specific user by reading metadata from S3.",
)
async def list_user_jobs(client_id: str) -> List[Dict[str, Any]]:
    """
    List all jobs for a specific user.
    """
    try:
        from utils.file_handlers import get_user_jobs_from_s3
        jobs = await get_user_jobs_from_s3(client_id)
        return jobs
    except Exception as e:
        logger.error(f"Failed to list jobs for user {client_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs for user {client_id}: {str(e)}",
        )


@router.delete(
    "/delete/job/{user_id}/{job_id}",
    summary="Delete a specific job folder",
    description="Deletes a specific job folder and all its contents from the S3 bucket.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job_folder(user_id: str, job_id: str):
    """
    Deletes a specific job folder from S3.
    """
    try:
        from utils.file_handlers import delete_s3_job_folder
        await delete_s3_job_folder(user_id, job_id)
        return {"message": f"Job {job_id} for user {user_id} deleted successfully."}
    except Exception as e:
        logger.error(f"Failed to delete job {job_id} for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job folder: {str(e)}",
        )


@router.delete(
    "/delete/user/{user_id}",
    summary="Delete a user's entire folder",
    description="Deletes a user's entire folder and all its contents from the S3 bucket.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_folder(user_id: str):
    """
    Deletes a user's entire folder from S3.
    """
    try:
        from utils.file_handlers import delete_s3_user_folder
        await delete_s3_user_folder(user_id)
        return {"message": f"User folder {user_id} deleted successfully."}
    except Exception as e:
        logger.error(f"Failed to delete user folder {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user folder: {str(e)}",
        )


@router.get(
    "/queue/status",
    summary="Get workflow queue status",
    description="Get the current status of the workflow processing queue and worker utilization.",
)
async def get_queue_status():
    """
    Get current workflow queue status and worker information.
    """
    try:
        status = await workflow_executor.get_queue_status()
        return {
            "status": "healthy",
            "queue_info": status,
            "capacity_utilization": {
                "workers_busy_percent": (status["active_jobs"] / status["max_workers"]) * 100,
                "can_accept_new_jobs": status["available_workers"] > 0,
                "estimated_wait_time_minutes": max(0, (status["queue_size"] / max(1, status["max_workers"])) * 3)  # Assuming 3 min average per job
            }
        }
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue status: {str(e)}",
        )

