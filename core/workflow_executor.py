"""
Workflow Executor Service - Manages CrewAI workflows in separate processes.

This service handles the execution of long-running CrewAI workflows in isolated
processes to prevent blocking the main API server.
"""

import asyncio
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from models.schemas import JobStatus
from utils.job_manager import job_manager


class WorkflowExecutorService:
    """Service to execute CrewAI workflows in separate processes with queue management."""

    def __init__(self):
        # Calculate optimal worker count based on CPU cores
        self.max_workers = min(32, max(4, multiprocessing.cpu_count() * 2))  # Max 32 workers, min 4
        self.executor: Optional[ProcessPoolExecutor] = None
        self.active_jobs = {}  # Track active jobs
        self.queue_size = 0
        self.logger = logger.bind(component="workflow_executor")
        
        # Initialize the executor
        self._initialize_executor()

    def _initialize_executor(self) -> None:
        """Initialize the ProcessPoolExecutor with optimal settings."""
        try:
            # Configure multiprocessing for the workflow processes
            if sys.platform.startswith('win'):
                multiprocessing.set_start_method('spawn', force=True)
            else:
                multiprocessing.set_start_method('fork', force=True)
            
            self.executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                initializer=_init_worker_process,
            )
            self.logger.info(f"Initialized ProcessPoolExecutor with {self.max_workers} workers")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize ProcessPoolExecutor: {e}")
            raise

    async def submit_workflow(
        self,
        job_id: str,
        input_file_path: str,
        expected_output_file_path: Optional[str] = None,
        job_description: Optional[str] = None,
        general_instructions: Optional[str] = None,
        column_instructions: Optional[Dict[str, str]] = None,
        use_full_paths: bool = False,
    ) -> bool:
        """
        Submit a workflow to be executed in a separate process.
        
        Args:
            job_id: Unique identifier for the job
            input_file_path: Path to input CSV file
            expected_output_file_path: Path to expected output CSV file
            job_description: Description of the job
            general_instructions: General transformation instructions
            column_instructions: Column-specific instructions
            use_full_paths: Whether to use full file paths
            
        Returns:
            bool: True if submitted successfully, False otherwise
        """
        if not self.executor:
            self.logger.error("ProcessPoolExecutor not initialized")
            return False

        try:
            self.logger.info(f"Submitting workflow job {job_id} to process pool")
            
            # Update job status to queued
            await job_manager.update_job_status(
                job_id,
                JobStatus.PENDING,
                current_step="Queued for processing",
                progress_details={
                    "queue_position": self.queue_size + 1,
                    "active_workers": len(self.active_jobs),
                    "max_workers": self.max_workers
                }
            )

            # Prepare arguments for the worker process
            workflow_args = {
                'job_id': job_id,
                'input_file_path': input_file_path,
                'expected_output_file_path': expected_output_file_path,
                'job_description': job_description,
                'general_instructions': general_instructions,
                'column_instructions': column_instructions,
                'use_full_paths': use_full_paths,
            }

            # Submit to executor
            future = self.executor.submit(_execute_workflow_process, workflow_args)
            
            # Store the future for tracking
            self.active_jobs[job_id] = future
            self.queue_size += 1

            # Set up callback for when the job completes
            def _job_completed(fut):
                try:
                    result = fut.result()
                    self.logger.info(f"Workflow job {job_id} completed with result: {result}")
                except Exception as e:
                    self.logger.error(f"Workflow job {job_id} failed: {e}")
                finally:
                    # Clean up tracking
                    if job_id in self.active_jobs:
                        del self.active_jobs[job_id]
                    self.queue_size = max(0, self.queue_size - 1)

            future.add_done_callback(_job_completed)
            
            self.logger.info(
                f"Job {job_id} submitted successfully. "
                f"Queue size: {self.queue_size}, Active workers: {len(self.active_jobs)}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to submit workflow job {job_id}: {e}")
            return False

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue and worker status."""
        return {
            "max_workers": self.max_workers,
            "active_jobs": len(self.active_jobs),
            "queue_size": self.queue_size,
            "available_workers": self.max_workers - len(self.active_jobs),
            "active_job_ids": list(self.active_jobs.keys())
        }

    def shutdown(self):
        """Shutdown the executor gracefully."""
        if self.executor:
            self.logger.info("Shutting down ProcessPoolExecutor...")
            self.executor.shutdown(wait=True)
            self.executor = None


def _init_worker_process():
    """Initialize each worker process with necessary setup."""
    # Set up logging for worker process
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>WORKER-{process}</cyan> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level="INFO"
    )
    
    # Add project directory to path so imports work
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    logger.info(f"Worker process {os.getpid()} initialized")


def _execute_workflow_process(workflow_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the CrewAI workflow in a separate process.
    
    This function runs in an isolated process and handles the entire
    workflow execution including all agent interactions.
    
    Args:
        workflow_args: Dictionary containing all workflow parameters
        
    Returns:
        Dictionary containing the workflow results
    """
    job_id = workflow_args['job_id']
    process_logger = logger.bind(job_id=job_id, process=os.getpid())
    
    try:
        process_logger.info(f"Starting workflow execution for job {job_id} in process {os.getpid()}")
        
        # Import here to avoid import issues in worker process
        import asyncio
        
        # Create new event loop for this process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Create fresh workflow instance for this worker process
            # This prevents sharing asyncio objects from the main process
            from core.workflow import CSVConversionWorkflow
            workflow_instance = CSVConversionWorkflow(use_fresh_instances=True)
            
            # Execute the workflow
            result = loop.run_until_complete(
                workflow_instance.execute_conversion_job(
                    job_id=workflow_args['job_id'],
                    input_file_path=workflow_args['input_file_path'],
                    expected_output_file_path=workflow_args['expected_output_file_path'],
                    job_description=workflow_args['job_description'],
                    general_instructions=workflow_args['general_instructions'],
                    column_instructions=workflow_args['column_instructions'],
                    use_full_paths=workflow_args['use_full_paths'],
                )
            )
            
            process_logger.info(f"Workflow job {job_id} completed successfully")
            return result
            
        finally:
            loop.close()

    except Exception as e:
        process_logger.error(f"Workflow execution failed for job {job_id}: {e}")
        return {
            "job_id": job_id,
            "success": False,
            "status": JobStatus.FAILED,
            "error": str(e)
        }


# Global instance
workflow_executor = WorkflowExecutorService()
