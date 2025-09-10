"""Coder Agent implementation for generating Python scripts with PEP 723 dependencies."""

from typing import Any, Dict, Optional

from crewai import Crew, Task  # type: ignore

from .base_agent import BaseCSVAgent


class CoderAgent(BaseCSVAgent):
    """
    The Coder Agent writes Python scripts that implement transformation plans.

    This agent acts as a skilled Python developer, generating self-contained
    scripts with embedded dependencies using the PEP 723 format for uv execution.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Coder",
            role="Python Developer",
            goal="To write a single, self-contained Python script that implements the plan provided by the Solution Architect.",
            backstory="""You are a skilled Python developer with expertise in writing clean, efficient, 
            and well-documented code. You are a proponent of modern Python tooling and are an expert in 
            using uv for script execution and dependency management. You follow instructions precisely and 
            create scripts that are both readable and maintainable. You always include proper error handling 
            and follow PEP 8 style guidelines.""",
        )

    async def execute_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the coding task.

        Args:
            task_data: Dictionary containing:
                - plan: The transformation plan from the Planner Agent
                - input_file_path: Path to the input CSV file
                - required_libraries: List of required Python libraries
                - job_description: Optional description of the task
                - general_instructions: Optional general transformation instructions
                - column_instructions: Optional column-specific transformation instructions
                - agent_feedback: Optional feedback from other agents

        Returns:
            Dictionary containing the generated script and metadata
        """
        plan = task_data["plan"]
        input_file_path = task_data["input_file_path"]
        required_libraries = task_data.get("required_libraries", ["pandas"])
        job_description = task_data.get("job_description", "")
        general_instructions = task_data.get("general_instructions", "")
        column_instructions = task_data.get("column_instructions", {})
        agent_feedback = task_data.get("agent_feedback", {})

        self.log_execution_start(f"Generating Python script based on {len(plan['steps'])} transformation steps")

        try:
            # Generate the Python script
            script_content = await self._generate_script(
                plan,
                input_file_path,
                required_libraries,
                job_description,
                general_instructions,
                column_instructions,
                agent_feedback,
            )

            result = {
                "success": True,
                "script_content": script_content,
                "dependencies": required_libraries,
                "complexity": plan.get("complexity", "Unknown"),
                "step_count": plan.get("total_steps", 0),
            }

            self.log_execution_end(True, f"Generated script with {len(script_content)} characters")
            return result

        except Exception as e:
            error_msg = f"Failed to generate Python script: {str(e)}"
            self.log_execution_end(False, error_msg)
            return {"success": False, "error": error_msg, "script_content": None}

    async def _generate_script(
        self,
        plan: Dict[str, Any],
        input_file_path: str,
        required_libraries: list,
        job_description: str,
        general_instructions: str,
        column_instructions: Dict[str, str],
        agent_feedback: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate the Python script based on the transformation plan and feedback."""

        # Create the task for the agent
        coding_task = Task(
            description=self._build_coding_prompt(
                plan,
                input_file_path,
                required_libraries,
                job_description,
                general_instructions,
                column_instructions,
                agent_feedback,
            ),
            agent=self.agent,
            expected_output="A complete Python script with PEP 723 dependencies that implements the transformation plan",
        )

        # Create a crew to execute the task
        crew = Crew(agents=[self.agent], tasks=[coding_task], verbose=False)

        # Execute the task through the crew
        result = crew.kickoff()
        script_content = str(result)

        # Ensure the script has proper PEP 723 format
        return self._ensure_pep723_format(script_content, required_libraries)

    def _build_coding_prompt(
        self,
        plan: Dict[str, Any],
        input_file_path: str,
        required_libraries: list,
        job_description: str,
        general_instructions: str,
        column_instructions: Dict[str, str],
        agent_feedback: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for the coding task."""

        plan_steps = "\n".join([f"{i + 1}. {step}" for i, step in enumerate(plan["steps"])])
        dependencies_str = '",\n    "'.join(required_libraries)

        # Format feedback for the prompt
        feedback_info = ""
        if agent_feedback:
            feedback_info = self._format_coder_feedback(agent_feedback)

        # Format general instructions
        general_instructions_text = ""
        if general_instructions and general_instructions.strip():
            general_instructions_text = f"GENERAL TRANSFORMATION INSTRUCTIONS:\n{general_instructions.strip()}\n\n"

        print("CODER: general_instructions_text: ", general_instructions_text)

        # Format column-specific instructions
        column_instructions_text = ""
        if column_instructions:
            column_instructions_text = "COLUMN-SPECIFIC TRANSFORMATION INSTRUCTIONS:\n"
            for col, instruction in column_instructions.items():
                column_instructions_text += f"- {col}: {instruction}\n"
            column_instructions_text += "\n"

        prompt = f"""
        You are a Python Data Processing Expert. Implement a data transformation plan that produces EXACT output matching the expected format, prioritizing the expected output schema and transformation instructions.

        JOB DESCRIPTION: {job_description or "Transform CSV data according to the plan and transformation instructions"}
        
        {general_instructions_text}

        {column_instructions_text}        
        TRANSFORMATION PLAN (output-first; include pre-cleaning if needed):
        {plan_steps}
        
        {feedback_info}
        
        CRITICAL IMPLEMENTATION PRINCIPLES:
        1. **OUTPUT-FIRST**: Only output the expected schema columns in the exact order; drop stray/out-of-schema tokens (e.g., trailing values like "Gift wrapped").
        2. **EXACT OUTPUT MATCHING**: Values, column names, order, and formats must match the expected output exactly.
        3. **ROBUST PRE-CLEANING**: If the plan indicates messy input, first read as text and clean via regex/line rules, then load with pandas.
        4. **HANDLE EDGE CASES**: Account for null values, missing data, mixed delimiters, and type conversions.
        5. **FOLLOW THE PLAN**: Implement each step precisely.
        6. **LEARN FROM FEEDBACK**: If feedback is provided, address the specific issues.
        7. **PANDAS COMPATIBILITY**: Use modern pandas API - avoid deprecated parameters like 'line_terminator'
        8. **DATETIME HANDLING**: Use specific datetime conversion patterns as detailed below
        
        TECHNICAL REQUIREMENTS:
        1. The script MUST start with PEP 723 dependencies in this exact format:
        
        # /// script
        # requires-python = ">=3.10"
        # dependencies = [
        #   "{dependencies_str}",
        # ]
        # ///
        
        2. The script must be self-contained and executable with `uv run script.py "input_file.csv"`
        3. Use pandas for all CSV operations
        4. Accept input file path as first command line argument
        5. Accept optional --save-csv argument for output file path
        6. Print the final DataFrame to stdout using df.to_csv(index=False) if no --save-csv is provided
        7. Save to file if --save-csv argument is provided
        8. Include proper error handling with try/except blocks
        9. Add docstrings and comments explaining the logic
        10. Follow PEP 8 style guidelines
        11. Use modern pandas API - avoid deprecated parameters
        
        PANDAS COMPATIBILITY NOTES:
        - Use `df.to_csv(index=False)` NOT `df.to_csv(index=False, line_terminator='\\n')`
        - The `line_terminator` parameter is deprecated in newer pandas versions
        - Use `sep=','` for explicit comma separation if needed
        - Use `encoding='utf-8'` for proper text encoding
        
        DATETIME CONVERSION GUIDELINES:
        When working with date/datetime columns, follow these specific patterns:
        
        1. **INPUT DATE PARSING** - Use this code for input date columns unless the user specifies an exact format:
           ```python
           df['date_column'] = pd.to_datetime(
               df['date_column'],
               format="mixed",
               errors="coerce",
               utc=True,  # CRITICAL: Always include utc=True
           )
           ```
           
           **CRITICAL**: `utc=True` is MANDATORY because:
           - Ensures consistent datetime objects (prevents object dtype)
           - Allows `.dt` accessor to work properly for formatting
           - Prevents "Can only use .dt accessor with datetimelike values" error
           - Handles multiple date formats in the same column
           - Normalizes different timezones
           - Invalid dates convert to NaT (Not a Time)
        
        2. **WHEN TO USE SPECIFIC FORMAT** - Only use a specific format if:
           - The user explicitly mentions the exact format (e.g., "dates are in YYYY-MM-DD format")
           - The user confirms all dates follow the same format
           - Example with specific format:
           ```python
           df['date_column'] = pd.to_datetime(
               df['date_column'],
               format='%Y-%m-%d',  # Use the specific format provided
               errors="coerce",
               utc=True,  # ALWAYS include utc=True even with specific format
           )
           ```
        
        3. **OUTPUT DATE FORMATTING** - To convert processed datetime to desired output format:
           ```python
           df['date_column'] = df['date_column'].dt.strftime('%Y-%m-%d')  # Example format
           ```
           
           Common format codes:
           - '%Y-%m-%d' → '2023-01-15'
           - '%m/%d/%Y' → '01/15/2023'
           - '%d-%m-%Y' → '15-01-2023'
           - '%Y-%m-%d %H:%M:%S' → '2023-01-15 14:30:00'
           - '%B %d, %Y' → 'January 15, 2023'
        
        4. **DATETIME PROCESSING WORKFLOW** (ALWAYS INCLUDE utc=True):
           ```python
           # Step 1: Parse input dates (MUST include utc=True)
           df['date_col'] = pd.to_datetime(
               df['date_col'], 
               format="mixed", 
               errors="coerce", 
               utc=True  # MANDATORY - prevents .dt accessor errors
           )
           
           # Step 2: Perform any date operations if needed
           # df['date_col'] = df['date_col'] + pd.DateOffset(days=30)  # Example
           
           # Step 3: Format to desired output (utc=True ensures .dt works)
           df['date_col'] = df['date_col'].dt.strftime('%Y-%m-%d')  # Match expected output
           ```
        
        5. **ERROR HANDLING FOR DATES**:
           - ALWAYS use `errors="coerce"` to handle invalid dates gracefully
           - ALWAYS use `utc=True` to ensure datetime objects and prevent `.dt` accessor errors
           - Check for NaT (Not a Time) values if needed: `df['date_col'].isna()`
           - Consider dropping rows with invalid dates only if they are critical
           
        **REMEMBER**: Every `pd.to_datetime()` call MUST include `utc=True` to prevent:
           - "Can only use .dt accessor with datetimelike values" error
           - Object dtype columns that break `.dt.strftime()` formatting
           - Inconsistent datetime handling across different input formats
        
        IMPLEMENTATION STRATEGY:
        - Implement a small `preclean_input_to_temp_csv` helper that:
          * Reads the input with Python's csv.reader to be quote-aware (quotechar='"', doublequote=True), so commas inside quotes are preserved.
          * Drops comment/prose/section header lines; detects header by matching expected column names (case-insensitive).
          * Keeps ALL rows from header to EOF; enforces exact field count by trimming extras; does not drop rows due to missing optional fields during pre-clean.
          * Writes a temporary clean CSV using csv.writer with quotechar='"', quoting=csv.QUOTE_MINIMAL; if input is already clean, return original path.
        - Load CSV with pandas using robust parameters (engine='python', on_bad_lines='skip', explicit sep when needed; quotechar='"').
        - Select/map columns to the exact expected output schema (case-insensitive, ignore spaces/underscores; allow fuzzy matches); enforce dtypes; normalize dates using the datetime conversion guidelines above.
        - **DATETIME PROCESSING**: For date/datetime columns, use `pd.to_datetime()` with `format="mixed"`, `errors="coerce"`, `utc=True` unless user specifies exact format. Then use `.dt.strftime()` to match expected output format.
        - Pre-clean tolerance: do not discard rows due to field count alone; keep rows meeting tolerance (>=50% non-empty OR all required present); fill missing with NaN for pandas.
        - Numeric conversion safety: strip regular and non-breaking spaces, then convert; only drop rows if a required field fails conversion irreparably.
        - Null policy: use the plan-provided required_columns vs optional_columns lists (do NOT hardcode). Drop rows only if required columns are missing/invalid; allow optional columns to be empty.
        - Validate final columns and order match expected output schema.
        - Use modern pandas API.
        
        SCRIPT STRUCTURE:
        ```python
        # /// script
        # requires-python = ">=3.10" 
        # dependencies = [
        #   "pandas",
        # ]
        # ///
        
        import pandas as pd
        import sys
        import argparse
        from pathlib import Path
        import re
        import tempfile
        
        def preclean_input_to_temp_csv(input_path: str, expected_num_fields: int | None = None) -> str:
            '''
            Optional generic pre-cleaning for messy inputs: keeps only lines that look like records
            and trims extra tokens. Returns a temporary CSV path when cleaning is applied, otherwise
            returns the original path.
            '''
            try:
                with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except Exception:
                return input_path

            # Guess delimiter by frequency
            delimiters = [",", "\t", ";", "|"]
            counts = {{delim: 0 for delim in delimiters}}
            for line in lines[:200]:
                for delim in delimiters:
                    counts[delim] += line.count(delim)
            delim = max(counts, key=counts.get)

            # Guess field count if not provided
            if expected_num_fields is None:
                from collections import Counter
                field_counts = Counter(len([*l.split(delim)]) for l in lines if l.strip())
                if field_counts:
                    expected_num_fields = field_counts.most_common(1)[0][0]

            cleaned: list[str] = []
            prose_markers = ("generated on", "prepared by", "start of", "report", "summary")
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith(("#", "//", "--")):
                    continue
                if any(tok in s.lower() for tok in prose_markers):
                    continue
                parts = [p.strip() for p in s.split(delim)]
                if expected_num_fields and len(parts) != expected_num_fields:
                    parts = parts[:expected_num_fields]
                cleaned.append(",".join(parts))

            if not cleaned:
                return input_path

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            with open(tmp.name, "w", encoding="utf-8", errors="replace") as w:
                w.write("\n".join(cleaned))
            return tmp.name

        def process_csv(input_file: str) -> pd.DataFrame:
            \"\"\"
            Process the input CSV according to the transformation plan.
            
            Args:
                input_file: Path to the input CSV file
                
            Returns:
                Transformed DataFrame
            \"\"\"
            try:
                # Pre-clean if needed (safe no-op if input is already clean)
                cleaned_path = preclean_input_to_temp_csv(input_file)
                # Load robustly
                df = pd.read_csv(cleaned_path, engine="python", on_bad_lines="skip")
                
                # Implement each step of the transformation plan here
                # Step 1: ...
                # Step 2: ...
                # etc.
                
                return df
                
            except FileNotFoundError:
                print(f"Error: Input file not found at {{input_file}}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Error processing CSV: {{e}}", file=sys.stderr)
                sys.exit(1)
        
        def main():
            \"\"\"Main entry point for the script.\"\"\"
            parser = argparse.ArgumentParser(description='CSV transformation script')
            parser.add_argument('input_file', help='Path to input CSV file')
            parser.add_argument('--save-csv', help='Path to save output CSV file (optional)')
            
            args = parser.parse_args()
            
            # Validate input file exists
            if not Path(args.input_file).exists():
                print(f"Error: Input file not found at {{args.input_file}}", file=sys.stderr)
                sys.exit(1)
            
            # Process the CSV
            result_df = process_csv(args.input_file)
            
            # Output handling
            if args.save_csv:
                # Save to specified file
                result_df.to_csv(args.save_csv, index=False)
                print(f"Output saved to: {{args.save_csv}}")
            else:
                # Print to stdout (use modern pandas API)
                print(result_df.to_csv(index=False), end='')
        
        if __name__ == "__main__":
            main()
        ```
        
        IMPORTANT: 
        - Implement each step from the transformation plan in the process_csv function
        - Use specific pandas operations mentioned in the plan
        - Ensure proper error handling for edge cases
        - The script should be production-ready and well-documented
        - Test your logic mentally to ensure it makes sense
        - Use EXACT values and formats as specified in the transformation plan
        - If feedback is provided, make sure to address the specific issues mentioned
        - Use modern pandas API to avoid compatibility issues
        - The script must accept CLI arguments: `uv run script.py "input.csv"` or `uv run script.py "input.csv" --save-csv="output.csv"`
        
        Generate ONLY the complete Python script, no additional explanation or markdown formatting.
        """

        return prompt.strip()

    def _format_coder_feedback(self, agent_feedback: Dict[str, Any]) -> str:
        """Format feedback for the coder agent."""
        if not agent_feedback:
            return ""

        feedback_info = ["FEEDBACK FROM PREVIOUS ATTEMPTS (ADDRESS THESE ISSUES):"]

        if "coder_feedback" in agent_feedback:
            coder_feedback = agent_feedback["coder_feedback"]
            feedback_info.append("Specific Issues to Fix:")
            for feedback in coder_feedback:
                if isinstance(feedback, dict):
                    issue_type = feedback.get("issue_type", "unknown")
                    suggestion = feedback.get("suggestion", "")
                    error_details = feedback.get("error_details", "")

                    if issue_type == "execution_error":
                        feedback_info.append(f"  - EXECUTION ERROR: {suggestion}")
                        feedback_info.append(f"    Error details: {error_details}")
                    elif issue_type == "tester_failure":
                        feedback_info.append(f"  - TESTER FAILURE: {suggestion}")
                        feedback_info.append(f"    Error details: {error_details}")
                    else:
                        feedback_info.append(f"  - {suggestion}")
                else:
                    # Handle legacy string format
                    feedback_info.append(f"  - {feedback}")

        if "test_report" in agent_feedback:
            feedback_info.append("Test Report Insights:")
            feedback_info.append(f"  - {agent_feedback['test_report']}")

        return "\n".join(feedback_info) + "\n"

    def _ensure_pep723_format(self, script_content: str, required_libraries: list) -> str:
        """Ensure the script has proper PEP 723 format at the top."""

        # Check if script already has PEP 723 format
        if script_content.strip().startswith("# /// script"):
            return script_content

        # Add PEP 723 header if missing
        deps = '",\n    "'.join(required_libraries)
        pep723_header = f'''# /// script
# requires-python = ">=3.10"
# dependencies = [
    "{deps}",
# ]
# ///

'''

        # Remove any existing shebang or comments at the top
        lines = script_content.strip().split("\n")
        start_idx = 0

        for i, line in enumerate(lines):
            if line.strip().startswith("#!") or (line.strip().startswith("#") and not line.strip().startswith("# ///")):
                start_idx = i + 1
            else:
                break

        # Reconstruct script with PEP 723 header
        script_body = "\n".join(lines[start_idx:])
        return pep723_header + script_body

    def validate_script_syntax(self, script_content: str) -> Dict[str, Any]:
        """Validate the generated script syntax."""
        try:
            compile(script_content, "<string>", "exec")
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": f"Syntax error at line {e.lineno}: {e.msg}"}
        except Exception as e:
            return {"valid": False, "error": f"Compilation error: {str(e)}"}
