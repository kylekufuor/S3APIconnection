"""Job management utilities for handling conversion jobs."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import aiofiles
from asyncio import Lock
from loguru import logger

from core.config import settings
from models.schemas import JobMetadata, JobStatus, OperationMode, TrainingJobRequest
from utils.file_handlers import create_s3_folders, save_job_metadata_to_s3, update_job_metadata_to_s3, upload_to_s3


class JobManager:
    """Manages conversion jobs and their state."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._write_lock = Lock()  # Write lock for modifying jobs
        self._read_lock = Lock()   # Read lock for accessing jobs
        self._jobs_file = Path("temp/jobs.json")
        self._load_jobs()

    def _load_jobs(self) -> None:
        """Load jobs from persistent storage."""
        try:
            if self._jobs_file.exists():
                with open(self._jobs_file, "r") as f:
                    jobs_data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    for job_id, job_data in jobs_data.items():
                        if "created_at" in job_data:
                            job_data["created_at"] = datetime.fromisoformat(job_data["created_at"])
                        if "updated_at" in job_data:
                            job_data["updated_at"] = datetime.fromisoformat(job_data["updated_at"])
                        if "completed_at" in job_data and job_data["completed_at"]:
                            job_data["completed_at"] = datetime.fromisoformat(job_data["completed_at"])
                    self._jobs = jobs_data
                    logger.info(f"Loaded {len(self._jobs)} jobs from persistent storage")
        except Exception as e:
            logger.error(f"Error loading jobs: {e}")
            self._jobs = {}

    async def _save_jobs(self) -> None:
        """Save jobs to persistent storage."""
        try:
            # Ensure temp directory exists
            self._jobs_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert datetime objects to ISO strings for JSON serialization
            jobs_data = {}
            for job_id, job_data in self._jobs.items():
                job_copy = job_data.copy()
                if "created_at" in job_copy:
                    job_copy["created_at"] = job_copy["created_at"].isoformat()
                if "updated_at" in job_copy:
                    job_copy["updated_at"] = job_copy["updated_at"].isoformat()
                if "completed_at" in job_copy and job_copy["completed_at"]:
                    job_copy["completed_at"] = job_copy["completed_at"].isoformat()
                jobs_data[job_id] = job_copy

            async with aiofiles.open(self._jobs_file, "w") as f:
                await f.write(json.dumps(jobs_data, indent=2))
        except Exception as e:
            logger.error(f"Error saving jobs: {e}")

    async def create_job(
        self,
        job_id: str,
        input_file: str,
        expected_output_file: Optional[str] = None,
        description: Optional[str] = None,
        general_instructions: Optional[str] = None,
        column_instructions: Optional[Dict[str, str]] = None,
        client_id: Optional[str] = None,
        mode: OperationMode = OperationMode.TRAINING,
    ) -> Dict[str, Any]:
        """Create a new conversion job."""
        async with self._write_lock:
            # Generate client_id if not provided
            if client_id is None:
                client_id = str(uuid4())

            job_data: Dict[str, Any] = {
                "job_id": job_id,
                "status": JobStatus.PENDING,
                "input_file": input_file,
                "expected_output_file": expected_output_file,
                "description": description,
                "general_instructions": general_instructions,
                "column_instructions": column_instructions,
                "client_id": client_id,
                "mode": mode.value,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "current_step": None,
                "progress_details": {},
                "error_message": None,
                "generated_script": None,
                "generated_script_path": None,
                "test_results": None,
                "agent_results": [],
            }

            self._jobs[job_id] = job_data
            await self._save_jobs()  # Save to persistent storage
            logger.info(f"Created {mode.value} job: {job_id} for client: {client_id}")
            return job_data

    async def create_training_job(
        self,
        request: TrainingJobRequest,
    ) -> Dict[str, Any]:
        """Create a new training job."""
        async with self._write_lock:
            job_id = str(uuid4())
            user_id = request.user_id
            bucket_name = settings.aws_bucket_name

            # 1. Create S3 folder structure
            await create_s3_folders(user_id, job_id)

            # 2. Create and save job metadata
            metadata = JobMetadata(
                user_id=user_id,
                user_name=request.owner,
                job_id=job_id,
                job_title=request.job_title,
                job_description=request.description,
                created_at=datetime.now(timezone.utc),
                job_status=JobStatus.PENDING,
            )
            await save_job_metadata_to_s3(metadata, user_id, job_id)

            # 3. Upload files to S3
            input_file_key = f"{user_id}/{job_id}/input/input.csv"
            await upload_to_s3(request.input_file, input_file_key)
            input_file_path = f"s3://{bucket_name}/{input_file_key}"

            expected_output_file_key = f"{user_id}/{job_id}/input/expected_output.csv"
            await upload_to_s3(request.expected_output_file, expected_output_file_key)
            expected_output_file_path = f"s3://{bucket_name}/{expected_output_file_key}"

            # 4. Create job in JobManager
            job_data: Dict[str, Any] = {
                "job_id": job_id,
                "status": JobStatus.PENDING,
                "input_file": input_file_path,
                "expected_output_file": expected_output_file_path,
                "description": request.description,
                "general_instructions": request.general_instructions,
                "column_instructions": request.column_instructions,
                "client_id": user_id,
                "mode": OperationMode.TRAINING.value,
                "created_at": metadata.created_at,
                "updated_at": metadata.created_at,
                "current_step": "Job created",
                "progress_details": {},
                "error_message": None,
                "generated_script": None,
                "generated_script_path": None,
                "test_results": None,
                "agent_results": [],
            }

            self._jobs[job_id] = job_data
            await self._save_jobs()  # Save to persistent storage
            logger.info(f"Created training job: {job_id} for user: {user_id}")
            return job_data

    async def create_training_job_fast(
        self,
        request: TrainingJobRequest,
    ) -> Dict[str, Any]:
        """Create a training job record INSTANTLY without S3 operations.
        
        S3 operations will be handled by the background worker process.
        This enables sonic-speed API responses (<100ms).
        """
        async with self._write_lock:
            # Handle job replacement if job_id is provided
            if request.job_id:
                job_id = request.job_id
                logger.info(f"🔄 Job replacement requested for existing job: {job_id}")
                
                # Delete existing job folder for replacement
                try:
                    from utils.file_handlers import delete_and_replace_job_folder
                    await delete_and_replace_job_folder(request.user_id, job_id)
                    logger.info(f"✅ Existing job {job_id} folder deleted - ready for replacement")
                except Exception as e:
                    logger.error(f"❌ Failed to delete existing job folder: {e}")
                    raise Exception(f"Failed to replace existing job: {e}")
            else:
                job_id = str(uuid4())
                
            user_id = request.user_id
            bucket_name = settings.aws_bucket_name
            
            # Fast job record creation - NO S3 operations!
            job_data: Dict[str, Any] = {
                "job_id": job_id,
                "status": JobStatus.INITIALIZING,  # Will be updated by worker
                "input_file": request.input_file,  # Original S3 path
                "expected_output_file": request.expected_output_file,  # Original S3 path
                "description": request.description,
                "general_instructions": request.general_instructions,
                "column_instructions": request.column_instructions,
                "client_id": user_id,
                "mode": OperationMode.TRAINING.value,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "current_step": "Job created - initializing S3 setup",
                "progress_details": {
                    "phase": "initializing",
                    "step": "job_created",
                    "progress_percent": 0
                },
                "error_message": None,
                "generated_script": None,
                "generated_script_path": None,
                "test_results": None,
                "agent_results": [],
                # Store original request data for worker processing
                "_request_data": {
                    "job_title": request.job_title,
                    "owner": request.owner,
                    "user_id": user_id,
                    "bucket_name": bucket_name
                }
            }
            
            self._jobs[job_id] = job_data
            await self._save_jobs()  # Fast local save only
            logger.info(f"⚡ Created FAST training job: {job_id} for user: {user_id} (S3 ops deferred)")
            return job_data

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID."""
        async with self._read_lock:
            job = self._jobs.get(job_id)
            return job.copy() if job else None

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        current_step: Optional[str] = None,
        progress_details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update job status and progress."""
        async with self._write_lock:
            if job_id not in self._jobs:
                return False

            job = self._jobs[job_id]
            job["status"] = status
            job["updated_at"] = datetime.now(timezone.utc)

            if current_step is not None:
                job["current_step"] = current_step

            if progress_details is not None:
                job["progress_details"].update(progress_details)

            if error_message is not None:
                job["error_message"] = error_message

            if status in [JobStatus.COMPLETED, JobStatus.FAILED] and job["mode"] == OperationMode.TRAINING.value:
                job["completed_at"] = datetime.now(timezone.utc)

                # Update S3 metadata
                await update_job_metadata_to_s3(job, job_id, status, progress_details)

            await self._save_jobs()  # Save to persistent storage
            logger.info(f"Updated job {job_id} status to {status}")
            return True

    async def add_agent_result(
        self,
        job_id: str,
        agent_name: str,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        execution_time: Optional[float] = None,
    ) -> bool:
        """Add an agent execution result to a job."""
        async with self._write_lock:
            if job_id not in self._jobs:
                return False

            job = self._jobs[job_id]
            result = {
                "agent_name": agent_name,
                "success": success,
                "output": output,
                "error": error,
                "execution_time": execution_time,
            }

            job["agent_results"].append(result)
            job["updated_at"] = datetime.now(timezone.utc)
            await self._save_jobs()  # Save to persistent storage

            logger.info(f"Added agent result for job {job_id}: {agent_name} - {'success' if success else 'failed'}")
            return True

    async def set_generated_script(self, job_id: str, script_content: str, script_path: Optional[str] = None) -> bool:
        """Set the generated script for a job."""
        async with self._write_lock:
            if job_id not in self._jobs:
                return False

            self._jobs[job_id]["generated_script"] = script_content
            if script_path:
                self._jobs[job_id]["generated_script_path"] = script_path
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc)
            await self._save_jobs()  # Save to persistent storage

            logger.info(f"Set generated script for job {job_id}")
            return True

    async def set_test_results(self, job_id: str, test_results: Dict[str, Any]) -> bool:
        """Set the test results for a job."""
        async with self._write_lock:
            if job_id not in self._jobs:
                return False

            self._jobs[job_id]["test_results"] = test_results
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc)
            await self._save_jobs()  # Save to persistent storage

            logger.info(f"Set test results for job {job_id}")
            return True

    async def set_inference_output(self, job_id: str, output_data: str, is_content: bool = False) -> bool:
        """Set the inference output for a job."""
        async with self._write_lock:
            if job_id not in self._jobs:
                return False

            if is_content:
                # Store CSV content directly
                self._jobs[job_id]["inference_output"] = {
                    "csv_content": output_data,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(f"Set inference output content for job {job_id}")
            else:
                # Legacy: Store file path (for backward compatibility)
                self._jobs[job_id]["inference_output"] = {
                    "output_file_path": output_data,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(f"Set inference output file path for job {job_id}")

            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc)
            await self._save_jobs()  # Save to persistent storage

            return True

    async def get_inference_output(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the inference output for a job."""
        async with self._read_lock:
            if job_id not in self._jobs:
                return None

            inference_output = self._jobs[job_id].get("inference_output")
            if inference_output is None:
                return None
            return inference_output

    async def list_jobs(self) -> Dict[str, Dict[str, Any]]:
        """List all jobs."""
        async with self._read_lock:
            return self._jobs.copy()

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        async with self._write_lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                logger.info(f"Deleted job: {job_id}")
                return True
            return False

    async def cleanup_completed_jobs(self, max_age_hours: int = 24) -> int:
        """Clean up completed jobs older than max_age_hours."""
        async with self._write_lock:
            now = datetime.now(timezone.utc)
            jobs_to_delete = []

            for job_id, job_data in self._jobs.items():
                if job_data["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    completed_at = job_data.get("completed_at")
                    if completed_at:
                        age_hours = (now - completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            jobs_to_delete.append(job_id)

            for job_id in jobs_to_delete:
                del self._jobs[job_id]

            if jobs_to_delete:
                logger.info(f"Cleaned up {len(jobs_to_delete)} old completed jobs")

            return len(jobs_to_delete)

    async def get_jobs_by_client(self, client_id: str) -> Dict[str, Any]:
        """Get all jobs for a specific client."""
        async with self._read_lock:
            client_jobs = {}
            client_id_str = str(client_id)

            for job_id, job_data in self._jobs.items():
                if job_data.get("client_id") == client_id_str:
                    client_jobs[job_id] = job_data

            logger.info(f"Found {len(client_jobs)} jobs for client {client_id}")
            return client_jobs

    async def get_latest_successful_job_for_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest successful training job for a client."""
        client_jobs = await self.get_jobs_by_client(client_id)

        # Filter for completed training jobs with generated scripts
        successful_jobs = []
        for job_data in client_jobs.values():
            if (
                job_data.get("status") == JobStatus.COMPLETED
                and job_data.get("mode") == OperationMode.TRAINING.value
                and job_data.get("generated_script")
            ):
                successful_jobs.append(job_data)

        if not successful_jobs:
            return None

        # Sort by creation time (newest first)
        successful_jobs.sort(key=lambda x: x["created_at"], reverse=True)
        return successful_jobs[0]


# Global job manager instance
job_manager = JobManager()
