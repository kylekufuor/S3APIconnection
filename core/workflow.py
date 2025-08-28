"""Main workflow orchestration for CSV conversion using CrewAI agents."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from agents.agent_factory import agent_factory
from core.config import settings
from models.schemas import JobStatus
from utils.job_manager import job_manager


class CSVConversionWorkflow:
    """Orchestrates the CSV conversion workflow using CrewAI agents."""

    def __init__(self) -> None:
        self.agent_factory = agent_factory
        self.job_manager = job_manager
        self.logger = logger.bind(component="workflow")

    async def execute_conversion_job(
        self,
        job_id: UUID,
        input_file_path: str,
        expected_output_file_path: Optional[str] = None,
        job_description: Optional[str] = None,
        general_instructions: Optional[str] = None,
        column_instructions: Optional[Dict[str, str]] = None,
        use_full_paths: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a complete CSV conversion job with dynamic agent communication.

        Args:
            job_id: Unique identifier for the job
            input_file_path: Path to the input CSV file
            expected_output_file_path: Path to the expected output CSV file (None for inference mode)
            job_description: Optional description of the conversion task

        Returns:
            Dictionary containing the final result of the conversion
        """
        job_id_str = str(job_id)
        self.logger.info(f"Starting conversion job {job_id_str}")

        # Get job data to determine mode
        job_data = await self.job_manager.get_job(job_id_str)
        if not job_data:
            error_msg = f"Job {job_id_str} not found"
            self.logger.error(error_msg)
            return {"success": False, "error": error_msg, "status": JobStatus.FAILED}

        job_mode = job_data.get("mode", "training")

        # For inference mode, delegate to the dedicated inference method
        if job_mode == "inference":
            client_id = job_data.get("client_id")
            if not client_id:
                error_msg = f"Client ID required for inference job {job_id_str}"
                await self._handle_job_failure(job_id_str, "Missing client ID", error_msg)
                return {"success": False, "error": error_msg, "status": JobStatus.FAILED}

            return await self.execute_inference_job(job_id, input_file_path, str(client_id), job_description)

        max_cycles = 5  # Allow up to 5 improvement cycles
        current_cycle = 0
        previous_attempts: List[Dict[str, Any]] = []
        agent_feedback: Dict[str, Any] = {}

        # Initialize result variables to prevent UnboundLocalError
        planner_result: Dict[str, Any] = {"success": False, "error": "Not executed"}
        coder_result: Dict[str, Any] = {"success": False, "error": "Not executed"}
        tester_result: Dict[str, Any] = {"success": False, "error": "Not executed"}

        while current_cycle < max_cycles:
            current_cycle += 1
            self.logger.info(f"Starting improvement cycle {current_cycle} of {max_cycles}")

            try:
                # Update job status to planning phase
                await self.job_manager.update_job_status(
                    job_id_str,
                    JobStatus.PLANNING,
                    current_step=f"Planning Phase (Cycle {current_cycle})",
                    progress_details={"phase": "analysis", "step": 1, "total_steps": 3, "cycle": current_cycle},
                )

                # Step 1: Execute Planner Agent with feedback
                planner_result = await self._execute_planner_phase(
                    job_id_str,
                    input_file_path,
                    expected_output_file_path,
                    job_description,
                    general_instructions,
                    column_instructions,
                    previous_attempts,
                    agent_feedback,
                    use_full_paths,
                )

                if not planner_result["success"]:
                    # Do not hard-stop; capture feedback and continue to next cycle
                    attempt_result = {
                        "planner_result": planner_result,
                        "coder_result": None,
                        "tester_result": None,
                        "cycle": current_cycle,
                    }
                    previous_attempts.append(attempt_result)

                    error_msg = planner_result.get("error", "Unknown planning error")
                    agent_feedback["coder_feedback"] = [
                        {
                            "issue_type": "planning_error",
                            "suggestion": f"Planning failed: {error_msg}",
                            "error_details": error_msg,
                        }
                    ]

                    if current_cycle < max_cycles:
                        await self.job_manager.update_job_status(
                            job_id_str,
                            JobStatus.PENDING,
                            current_step=f"Retry planning (Cycle {current_cycle + 1})",
                            progress_details={"phase": "improvement", "cycle": current_cycle + 1},
                        )
                        continue
                    else:
                        await self._handle_job_failure(job_id_str, "Planning failed", error_msg)
                        final_status = JobStatus.FAILED
                        success = False
                        break

                # Step 2: Execute Coder Agent with feedback
                await self.job_manager.update_job_status(
                    job_id_str,
                    JobStatus.CODING,
                    current_step=f"Coding Phase (Cycle {current_cycle})",
                    progress_details={"phase": "generation", "step": 2, "total_steps": 3, "cycle": current_cycle},
                )

                coder_result = await self._execute_coder_phase(
                    job_id_str,
                    planner_result,
                    input_file_path,
                    job_description,
                    general_instructions,
                    column_instructions,
                    agent_feedback,
                    use_full_paths,
                )

                if not coder_result["success"]:
                    # Do not hard-stop; capture feedback and continue to next cycle
                    attempt_result = {
                        "planner_result": planner_result,
                        "coder_result": coder_result,
                        "tester_result": None,
                        "cycle": current_cycle,
                    }
                    previous_attempts.append(attempt_result)

                    error_msg = coder_result.get("error", "Unknown code generation error")
                    agent_feedback["coder_feedback"] = [
                        {
                            "issue_type": "generation_error",
                            "suggestion": f"Code generation failed: {error_msg}",
                            "error_details": error_msg,
                        }
                    ]

                    if current_cycle < max_cycles:
                        await self.job_manager.update_job_status(
                            job_id_str,
                            JobStatus.PENDING,
                            current_step=f"Improving based on coder error (Cycle {current_cycle + 1})",
                            progress_details={"phase": "improvement", "cycle": current_cycle + 1},
                        )
                        continue
                    else:
                        await self._handle_job_failure(job_id_str, "Code generation failed", error_msg)
                        final_status = JobStatus.FAILED
                        success = False
                        break

                # Step 3: Execute Tester Agent
                await self.job_manager.update_job_status(
                    job_id_str,
                    JobStatus.TESTING,
                    current_step=f"Testing Phase (Cycle {current_cycle})",
                    progress_details={"phase": "validation", "step": 3, "total_steps": 3, "cycle": current_cycle},
                )

                tester_result = await self._execute_tester_phase(
                    job_id_str, coder_result, input_file_path, expected_output_file_path, use_full_paths
                )

                # Determine if we need another improvement cycle
                if tester_result and tester_result["success"] and tester_result.get("test_passed", False):
                    await self._handle_job_completion(job_id_str, planner_result, coder_result, tester_result)
                    final_status = JobStatus.COMPLETED
                    success = True
                    break  # Success, exit improvement cycles
                else:
                    # Store this attempt for learning
                    attempt_result = {
                        "planner_result": planner_result,
                        "coder_result": coder_result,
                        "tester_result": tester_result,
                        "cycle": current_cycle,
                    }
                    previous_attempts.append(attempt_result)

                    # Extract feedback for next cycle - handle both execution errors and test failures
                    feedback_for_coder = []

                    if tester_result:
                        if not tester_result["success"]:
                            # Script execution failed - extract error for coder
                            error_msg = tester_result.get("error", "Script execution failed")
                            feedback_for_coder.append(
                                {
                                    "issue_type": "execution_error",
                                    "suggestion": f"Fix script execution error: {error_msg}",
                                    "error_details": error_msg,
                                }
                            )
                            # Include tester-proposed fix suggestions if provided
                            extra_feedback = tester_result.get("feedback_for_coder")
                            if isinstance(extra_feedback, list) and extra_feedback:
                                feedback_for_coder.extend(extra_feedback)
                        elif "comparison_result" in tester_result:
                            # Test passed but output doesn't match - extract comparison feedback
                            comparison = tester_result["comparison_result"]
                            feedback_for_coder = comparison.get("feedback_for_coder", [])

                            if feedback_for_coder:
                                agent_feedback["coder_feedback"] = feedback_for_coder
                                agent_feedback["test_report"] = tester_result.get("test_report", "")
                                self.logger.info(f"Extracted feedback for next cycle: {len(feedback_for_coder)} items")
                    else:
                        # Tester phase failed completely
                        feedback_for_coder.append(
                            {
                                "issue_type": "tester_failure",
                                "suggestion": "Tester phase failed - check script syntax and dependencies",
                                "error_details": "Tester phase failed to execute",
                            }
                        )

                    if feedback_for_coder:
                        agent_feedback["coder_feedback"] = feedback_for_coder
                        if tester_result and "test_report" in tester_result:
                            agent_feedback["test_report"] = tester_result.get("test_report", "")

                        # Continue to next improvement cycle
                        if current_cycle < max_cycles:
                            await self.job_manager.update_job_status(
                                job_id_str,
                                JobStatus.PENDING,
                                current_step=f"Improving based on feedback (Cycle {current_cycle + 1})",
                                progress_details={"phase": "improvement", "cycle": current_cycle + 1},
                            )
                            continue

                    # If no feedback or max cycles reached, fail the job
                    error_msg = (
                        "Testing failed"
                        if tester_result and tester_result["success"]
                        else tester_result.get("error", "Unknown testing error")
                        if tester_result
                        else "Tester phase failed"
                    )
                    await self._handle_job_failure(
                        job_id_str, error_msg, tester_result.get("error") if tester_result else "Tester phase failed"
                    )
                    final_status = JobStatus.FAILED
                    success = False
                    break

            except Exception as e:
                error_msg = f"Unexpected error in conversion workflow: {str(e)}"
                self.logger.error(error_msg)
                await self._handle_job_failure(job_id_str, "Workflow error", error_msg)
                return {"job_id": job_id, "success": False, "status": JobStatus.FAILED, "error": error_msg}

        # Compile final result
        final_result = {
            "job_id": job_id,
            "success": success,
            "status": final_status,
            "planner_result": planner_result,
            "coder_result": coder_result,
            "tester_result": tester_result,
            "generated_script": coder_result.get("script_content")
            if coder_result and coder_result["success"]
            else None,
            "test_passed": tester_result.get("test_passed", False)
            if tester_result and tester_result["success"]
            else False,
            "cycles": current_cycle,
        }

        self.logger.info(
            f"Conversion job {job_id_str} completed with status: {final_status} after {current_cycle} cycles"
        )
        return final_result

    async def execute_inference_job(
        self, job_id: UUID, input_file_path: str, client_id: str, job_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute an inference job using a previously trained model.

        Args:
            job_id: Unique identifier for the job
            input_file_path: Path to the input CSV file
            client_id: Client ID to use for finding the trained model
            job_description: Optional description of the task

        Returns:
            Dictionary containing the final result of the inference
        """
        job_id_str = str(job_id)
        self.logger.info(f"Starting inference job {job_id_str} for client {client_id}")

        try:
            # Update job status to inference phase
            await self.job_manager.update_job_status(
                job_id_str,
                JobStatus.PLANNING,
                current_step="Loading trained model",
                progress_details={"phase": "inference", "step": 1, "total_steps": 2},
            )

            # Get the latest trained script for the client
            from uuid import UUID

            from utils.file_handlers import get_latest_user_script

            client_uuid = UUID(client_id)
            script_path = get_latest_user_script(client_uuid)

            if not script_path:
                error_msg = f"No trained model found for client {client_id}"
                await self._handle_job_failure(job_id_str, "No trained model", error_msg)
                return {"success": False, "error": error_msg, "status": JobStatus.FAILED}

            # Update job status to executing phase
            await self.job_manager.update_job_status(
                job_id_str,
                JobStatus.CODING,
                current_step="Executing inference",
                progress_details={"phase": "inference", "step": 2, "total_steps": 2},
            )

            # Execute the inference
            inference_result = await self._execute_inference_phase(
                job_id_str, script_path, input_file_path, job_description
            )

            if not inference_result["success"]:
                await self._handle_job_failure(job_id_str, "Inference failed", inference_result.get("error"))
                return inference_result

            # Handle successful completion
            await self._handle_inference_completion(job_id_str, inference_result)
            return inference_result

        except Exception as e:
            error_msg = f"Unexpected error in inference workflow: {str(e)}"
            self.logger.error(error_msg)
            await self._handle_job_failure(job_id_str, "Inference workflow error", error_msg)
            return {"job_id": job_id, "success": False, "status": JobStatus.FAILED, "error": error_msg}

    async def _execute_planner_phase(
        self,
        job_id: str,
        input_file_path: str,
        expected_output_file_path: Optional[str],
        job_description: Optional[str],
        general_instructions: Optional[str] = None,
        column_instructions: Optional[Dict[str, str]] = None,
        previous_attempts: Optional[List[Dict[str, Any]]] = None,
        agent_feedback: Optional[Dict[str, Any]] = None,
        use_full_paths: bool = False,
    ) -> Dict[str, Any]:
        """Execute the planning phase with feedback from other agents."""
        self.logger.info(f"Executing planner phase for job {job_id}")

        try:
            planner_agent = self.agent_factory.get_planner_agent()

            if use_full_paths:
                resolved_input_path = str(Path(input_file_path).resolve())
                resolved_expected_path = (
                    str(Path(expected_output_file_path).resolve()) if expected_output_file_path else None
                )
            else:
                resolved_input_path = str((Path(settings.upload_dir) / input_file_path).resolve())
                resolved_expected_path = (
                    str((Path(settings.upload_dir) / expected_output_file_path).resolve())
                    if expected_output_file_path
                    else None
                )

            task_data = {
                "input_file_path": resolved_input_path,
                "expected_output_file_path": resolved_expected_path,
                "job_description": job_description,
                "general_instructions": general_instructions,
                "column_instructions": column_instructions or {},
                "previous_attempts": previous_attempts or [],
                "agent_feedback": agent_feedback or {},
            }

            import time

            start_time = time.time()
            result = await planner_agent.execute_task(task_data)
            execution_time = time.time() - start_time

            # Add agent result to job
            await self.job_manager.add_agent_result(
                job_id,
                "Planner",
                result["success"],
                output=str(result.get("plan", {})) if result["success"] else None,
                error=result.get("error"),
                execution_time=execution_time,
            )

            return result

        except Exception as e:
            error_msg = f"Planner phase error: {str(e)}"
            self.logger.error(error_msg)

            await self.job_manager.add_agent_result(job_id, "Planner", False, error=error_msg)

            return {"success": False, "error": error_msg}

    async def _execute_coder_phase(
        self,
        job_id: str,
        planner_result: Dict[str, Any],
        input_file_path: str,
        job_description: Optional[str],
        general_instructions: Optional[str] = None,
        column_instructions: Optional[Dict[str, str]] = None,
        agent_feedback: Optional[Dict[str, Any]] = None,
        use_full_paths: bool = False,
    ) -> Dict[str, Any]:
        """Execute the coding phase with feedback from tester agent."""
        self.logger.info(f"Executing coder phase for job {job_id}")

        try:
            coder_agent = self.agent_factory.get_coder_agent()

            if use_full_paths:
                resolved_input_path = str(Path(input_file_path).resolve())
            else:
                resolved_input_path = str((Path(settings.upload_dir) / input_file_path).resolve())

            task_data = {
                "plan": planner_result["plan"],
                "input_file_path": resolved_input_path,
                "required_libraries": planner_result.get("required_libraries", ["pandas"]),
                "job_description": job_description,
                "general_instructions": general_instructions,
                "column_instructions": column_instructions or {},
                "agent_feedback": agent_feedback or {},
            }

            import time

            start_time = time.time()
            result = await coder_agent.execute_task(task_data)
            execution_time = time.time() - start_time

            # Save generated script to job and user-specific directory
            if result["success"] and result.get("script_content"):
                # Get job data to extract client_id
                job_data = await self.job_manager.get_job(job_id)
                if job_data and job_data.get("client_id"):
                    from uuid import UUID

                    from utils.file_handlers import save_user_script

                    client_id = UUID(job_data["client_id"])
                    script_path = await save_user_script(result["script_content"], client_id, job_id)

                    # Save to job manager with script path
                    await self.job_manager.set_generated_script(job_id, result["script_content"], str(script_path))
                    result["generated_script_path"] = str(script_path.resolve())
                else:
                    # Fallback to original method if no client_id
                    from uuid import uuid4

                    temp_client_id = uuid4()
                    script_path = await save_user_script(result["script_content"], temp_client_id, job_id)
                    await self.job_manager.set_generated_script(job_id, result["script_content"], str(script_path))
                    result["generated_script_path"] = str(script_path.resolve())

            # Add agent result to job
            await self.job_manager.add_agent_result(
                job_id,
                "Coder",
                result["success"],
                output=f"Generated {len(result.get('script_content', ''))} character script"
                if result["success"]
                else None,
                error=result.get("error"),
                execution_time=execution_time,
            )

            return result

        except Exception as e:
            error_msg = f"Coder phase error: {str(e)}"
            self.logger.error(error_msg)

            await self.job_manager.add_agent_result(job_id, "Coder", False, error=error_msg)

            return {"success": False, "error": error_msg}

    async def _execute_tester_phase(
        self,
        job_id: str,
        coder_result: Dict[str, Any],
        input_file_path: str,
        expected_output_file_path: Optional[str],
        use_full_paths: bool = False,
    ) -> Dict[str, Any]:
        """Execute the testing phase."""
        self.logger.info(f"Executing tester phase for job {job_id}")

        try:
            tester_agent = self.agent_factory.get_tester_agent()

            # Ensure we have the script path
            if "generated_script_path" not in coder_result:
                error_msg = "No script path found in coder result"
                self.logger.error(error_msg)
                return {"success": False, "error": error_msg}

            if use_full_paths:
                resolved_input_path = str(Path(input_file_path).resolve())
                resolved_expected_path = (
                    str(Path(expected_output_file_path).resolve()) if expected_output_file_path else None
                )
            else:
                resolved_input_path = str((Path(settings.upload_dir) / input_file_path).resolve())
                resolved_expected_path = (
                    str((Path(settings.upload_dir) / expected_output_file_path).resolve())
                    if expected_output_file_path
                    else None
                )

            task_data = {
                "generated_script_path": coder_result["generated_script_path"],
                "input_file_path": resolved_input_path,
                "expected_output_file_path": resolved_expected_path,
                "job_id": job_id,
            }

            import time

            start_time = time.time()
            result = await tester_agent.execute_task(task_data)
            execution_time = time.time() - start_time

            # Save test results to job
            if result["success"]:
                test_results = {
                    "test_passed": result.get("test_passed", False),
                    "comparison_result": result.get("comparison_result", {}),
                    "execution_time": execution_time,
                }
                await self.job_manager.set_test_results(job_id, test_results)

            # Add agent result to job
            await self.job_manager.add_agent_result(
                job_id,
                "Tester",
                result["success"],
                output=f"Test {'passed' if result.get('test_passed') else 'failed'}" if result["success"] else None,
                error=result.get("error"),
                execution_time=execution_time,
            )

            return result

        except Exception as e:
            error_msg = f"Tester phase error: {str(e)}"
            self.logger.error(error_msg)

            await self.job_manager.add_agent_result(job_id, "Tester", False, error=error_msg)

            return {"success": False, "error": error_msg}

    async def _execute_inference_phase(
        self, job_id: str, script_path: Path, input_file_path: str, job_description: Optional[str]
    ) -> Dict[str, Any]:
        """Execute the inference phase using a trained model."""
        self.logger.info(f"Executing inference phase for job {job_id}")

        try:
            import subprocess
            from pathlib import Path

            from utils.file_handlers import safe_file_path, validate_file_exists

            # Prepare the command with temporary output
            input_full_path = Path(settings.upload_dir) / input_file_path

            # Create a temporary file for output (will be deleted after reading)
            import tempfile

            temp_output = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
            temp_output_path = Path(temp_output.name)
            temp_output.close()

            # Validate script file
            script_exists, script_error = validate_file_exists(script_path, "script")
            if not script_exists:
                self.logger.error(script_error)
                return {"success": False, "error": script_error}

            # Validate input file
            input_exists, input_error = validate_file_exists(input_full_path, "input")
            if not input_exists:
                self.logger.error(input_error)
                return {"success": False, "error": input_error}

            cmd = [
                "uv",
                "run",
                safe_file_path(script_path),
                safe_file_path(input_full_path),
                "--save-csv",
                safe_file_path(temp_output_path),
            ]

            self.logger.info(f"Executing command: {' '.join(cmd)}")

            # Execute the script
            import time

            start_time = time.time()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=script_path.parent,  # Run from script directory
            )

            execution_time = time.time() - start_time

            if result.returncode != 0:
                error_msg = f"Script execution failed: {result.stderr}"
                self.logger.error(error_msg)
                return {"success": False, "error": error_msg}

            # Read the output CSV content and clean up temp file
            if temp_output_path.exists():
                try:
                    # Read CSV content into memory
                    with open(temp_output_path, "r", encoding="utf-8") as f:
                        csv_content = f.read()

                    # Clean up temporary file
                    temp_output_path.unlink()

                    # Save output content to job manager (not file path)
                    await self.job_manager.set_inference_output(job_id, csv_content, is_content=True)

                    return {
                        "success": True,
                        "output_csv_content": csv_content,
                        "execution_time": execution_time,
                        "script_path": str(script_path),
                    }
                except Exception as e:
                    # Clean up temp file even if reading fails
                    if temp_output_path.exists():
                        temp_output_path.unlink()
                    error_msg = f"Failed to read output CSV: {str(e)}"
                    return {"success": False, "error": error_msg}
            else:
                error_msg = "Script executed but no output file was created"
                return {"success": False, "error": error_msg}

        except subprocess.TimeoutExpired:
            error_msg = "Script execution timed out after 5 minutes"
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Inference execution error: {str(e)}"
            self.logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def _handle_job_completion(
        self, job_id: str, planner_result: Dict[str, Any], coder_result: Dict[str, Any], tester_result: Dict[str, Any]
    ) -> None:
        """Handle successful job completion."""
        await self.job_manager.update_job_status(
            job_id,
            JobStatus.COMPLETED,
            current_step="Completed",
            progress_details={
                "phase": "completed",
                "step": 3,
                "total_steps": 3,
                "summary": "All phases completed successfully",
            },
        )

        self.logger.info(f"Job {job_id} completed successfully")

    async def _handle_job_failure(self, job_id: str, failure_reason: str, error_details: Optional[str] = None) -> None:
        """Handle job failure."""
        await self.job_manager.update_job_status(
            job_id,
            JobStatus.FAILED,
            current_step="Failed",
            error_message=f"{failure_reason}: {error_details}" if error_details else failure_reason,
            progress_details={"failure_reason": failure_reason},
        )

        self.logger.error(f"Job {job_id} failed: {failure_reason}")

    async def _handle_inference_completion(self, job_id: str, inference_result: Dict[str, Any]) -> None:
        """Handle successful inference completion."""
        await self.job_manager.update_job_status(
            job_id,
            JobStatus.COMPLETED,
            current_step="Inference completed",
            progress_details={
                "phase": "completed",
                "execution_time": inference_result.get("execution_time", 0),
                "output_file": inference_result.get("output_csv_path", ""),
            },
        )

        self.logger.info(f"Inference job {job_id} completed successfully")

    def _is_value_mapping_issue(self, tester_result: Dict[str, Any]) -> bool:
        """Check if the test failure is due to value mapping issues."""
        if not tester_result.get("success", False):
            return False

        comparison_result = tester_result.get("comparison_result", {})
        suggestions = comparison_result.get("suggestions", [])

        # Check if there are value mapping suggestions
        value_mapping_keywords = [
            "exact value",
            "exact values",
            "value mapping",
            "output matching",
            "precise values",
            "format matching",
            "case sensitive",
            "exact format",
        ]

        for suggestion in suggestions:
            if any(keyword in suggestion.lower() for keyword in value_mapping_keywords):
                return True

        return False


# Global workflow instance
csv_conversion_workflow = CSVConversionWorkflow()
