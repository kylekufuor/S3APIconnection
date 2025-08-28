"""Planner Agent implementation for CSV analysis and transformation planning."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from crewai import Crew, Task

from ..utils.file_handlers import analyze_csv_structure, compare_csv_structures
from .base_agent import BaseCSVAgent


class PlannerAgent(BaseCSVAgent):
    """
    The Planner Agent analyzes CSV files and creates detailed transformation plans.

    This agent acts as a Solution Architect, analyzing input and expected output
    CSV files to create step-by-step plans for data transformation.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Planner",
            role="Solution Architect",
            goal="To analyze the provided input and expected output CSV files and create a detailed, step-by-step plan for the Coder Agent.",
            backstory="""You are an experienced Solution Architect who specializes in data transformation tasks. 
            You have a keen eye for detail and can break down complex data manipulation logic into simple, 
            easy-to-follow steps. You are an expert in using the pandas library in Python. Your plans are 
            so clear that even a junior Python developer can understand and implement them perfectly.""",
        )

    async def execute_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the planning task.

        Args:
            task_data: Dictionary containing:
                - input_file_path: Path to the input CSV file
                - expected_output_file_path: Path to the expected output CSV file
                - job_description: Optional description of the transformation task
                - general_instructions: Optional general transformation instructions
                - column_instructions: Optional column-specific transformation instructions
                - previous_attempts: Optional list of previous attempt results
                - agent_feedback: Optional feedback from other agents

        Returns:
            Dictionary containing the transformation plan and analysis
        """
        input_file_path = Path(task_data["input_file_path"])
        expected_output_file_path = Path(task_data["expected_output_file_path"])
        job_description = task_data.get("job_description", "")
        general_instructions = task_data.get("general_instructions", "")
        column_instructions = task_data.get("column_instructions", {})
        previous_attempts = task_data.get("previous_attempts", [])
        agent_feedback = task_data.get("agent_feedback", {})

        self.log_execution_start(f"Analyzing CSV files: {input_file_path.name} -> {expected_output_file_path.name}")

        try:
            # Analyze both CSV files
            input_analysis = await analyze_csv_structure(input_file_path)
            output_analysis = await analyze_csv_structure(expected_output_file_path)

            # Compare structures to identify differences
            comparison = await compare_csv_structures(input_file_path, expected_output_file_path)

            # Create the transformation plan
            plan = await self._create_transformation_plan(
                input_analysis,
                output_analysis,
                comparison,
                job_description,
                general_instructions,
                column_instructions,
                previous_attempts,
                agent_feedback,
            )

            result = {
                "success": True,
                "plan": plan,
                "input_analysis": input_analysis,
                "output_analysis": output_analysis,
                "comparison": comparison,
                "required_libraries": ["pandas"],
            }

            self.log_execution_end(True, f"Created transformation plan with {len(plan['steps'])} steps")
            return result

        except Exception as e:
            error_msg = f"Failed to create transformation plan: {str(e)}"
            self.log_execution_end(False, error_msg)
            return {"success": False, "error": error_msg, "plan": None}

    async def _create_transformation_plan(
        self,
        input_analysis: Dict[str, Any],
        output_analysis: Dict[str, Any],
        comparison: Dict[str, Any],
        job_description: str,
        general_instructions: str,
        column_instructions: Dict[str, str],
        previous_attempts: Optional[List[Dict[str, Any]]] = None,
        agent_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a detailed transformation plan based on the analysis and feedback."""

        # Create the task for the agent
        planning_task = Task(
            description=self._build_planning_prompt(
                input_analysis,
                output_analysis,
                comparison,
                job_description,
                general_instructions,
                column_instructions,
                previous_attempts,
                agent_feedback,
            ),
            agent=self.agent,
            expected_output="A detailed step-by-step transformation plan in structured format",
        )

        # Create a crew to execute the task
        crew = Crew(agents=[self.agent], tasks=[planning_task], verbose=False)

        # Execute the task through the crew
        result = crew.kickoff()
        plan_text = str(result)

        # Parse the plan into structured format and enrich with schema policies
        return self._parse_plan_output(plan_text, comparison, output_analysis)

    def _build_planning_prompt(
        self,
        input_analysis: Dict[str, Any],
        output_analysis: Dict[str, Any],
        comparison: Dict[str, Any],
        job_description: str,
        general_instructions: str,
        column_instructions: Dict[str, str],
        previous_attempts: Optional[List[Dict[str, Any]]] = None,
        agent_feedback: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for the planning task."""

        # Extract sample data for better value mapping
        input_sample = input_analysis.get("sample_data") or []
        output_sample = output_analysis.get("sample_data") or []

        # Create a value mapping guide from sample data
        value_mapping_guide = self._create_value_mapping_guide(input_sample, output_sample)

        # Add previous attempt information if available
        previous_attempts_info = ""
        if previous_attempts:
            previous_attempts_info = self._format_previous_attempts(previous_attempts)

        # Add agent feedback information if available
        agent_feedback_info = ""
        if agent_feedback:
            try:
                agent_feedback_info = self._format_agent_feedback(agent_feedback)
            except Exception:
                agent_feedback_info = ""

        # Raw text quality diagnostics for planner context
        input_raw = input_analysis.get("raw_text_analysis", {})

        # Format general instructions
        general_instructions_text = ""
        if general_instructions and general_instructions.strip():
            general_instructions_text = f"GENERAL TRANSFORMATION INSTRUCTIONS:\n{general_instructions.strip()}\n\n"

        print("PLANNER: general_instructions_text: ", general_instructions_text)

        # Format column-specific instructions
        column_instructions_text = ""
        if column_instructions:
            column_instructions_text = "COLUMN-SPECIFIC TRANSFORMATION INSTRUCTIONS:\n"
            for col, instruction in column_instructions.items():
                column_instructions_text += f"- {col}: {instruction}\n"
            column_instructions_text += "\n"

        prompt = f"""
        You are a Data Transformation Expert. Your goal is to analyze CSV files and create precise, output-first transformation plans based on general and column-specific instructions.

        JOB DESCRIPTION: {job_description or "Transform input CSV to match expected output CSV using transformation instructions"}
        
        {general_instructions_text}

        {column_instructions_text}
        
        {previous_attempts_info}
        
        {agent_feedback_info}
        
        OUTPUT-FIRST TARGET (FOCUS MOST ON THIS):
        - Expected Filename: {output_analysis["filename"]}
        - Expected Columns (exact names & order): {output_analysis["columns"]}
        - Expected Data Types: {output_analysis["dtypes"]}
        - Expected Sample Data: {output_sample}
        
        INPUT CSV STRUCTURE (for reference and cleaning only):
        - Filename: {input_analysis["filename"]}
        - Shape: {input_analysis["shape"]} (rows, columns)
        - Columns: {input_analysis["columns"]}
        - Data Types: {input_analysis["dtypes"]}
        - Null Counts: {input_analysis["null_counts"]}
        - Sample Data: {input_sample}
        
        RAW TEXT QUALITY DIAGNOSTICS (input):
        - Quality: {input_raw.get("quality_label")}
        - Indicators: {input_raw.get("messy_indicators")}
        - Leading noise lines: {input_raw.get("leading_noise_lines")}
        - Header index guess: {input_raw.get("header_index_guess")}
        - Delimiter guess: {input_raw.get("delimiter_guess")}
        - Dominant field count: {input_raw.get("dominant_field_count")}
        - Cleaning recommendations: {input_raw.get("cleaning_recommendations")}
        
        STRUCTURAL DIFFERENCES:
        {self._format_differences(comparison["differences"])}
        
        CRITICAL PRINCIPLES:
        1. OUTPUT-FIRST: Always design from expected output schema; ignore/out-drop any input-only artifacts or stray values (e.g., appended tokens like "Gift wrapped").
        2. EXACT MATCHING: Values, formats, and column order must match expected output exactly.
        3. CLEAN BEFORE PROCESS: If input is messy or semi-structured, specify robust pre-cleaning steps (text-level) before pandas processing.
        4. GENERALIZE: Provide rules that work on arbitrary messy CSVs; avoid overfitting to the specific files.
        5. CONFLICT RESOLUTION: If the job description/guides conflict with RAW TEXT QUALITY DIAGNOSTICS (e.g., delimiter), TRUST THE DIAGNOSTICS and expected output sample over the description.
        6. NO FIXED ROW LIMITS: Process ALL rows from the detected header through end-of-file (EOF). Do not limit to a static number of lines.
        7. REQUIRED vs OPTIONAL COLUMNS: Infer required columns from the expected output (no nulls in sample or semantic names like id/date/amount). Treat other columns as optional. Only enforce non-null on required columns.
        8. TOLERANCE POLICY: Avoid dropping rows during pre-cleaning for missing optional fields. Prefer to keep and let pandas handle; drop rows post-load only if required fields are missing or irreparable.
        9. QUOTE-AWARE PARSING: Never split fields by delimiter naïvely. Treat quoted delimiters as literal text. Prefer Python's csv module (csv.reader/csv.writer with quotechar='"', doublequote=True) or pandas read_csv with quotechar='"', escapechar=None, engine='python'.
        10. NO HARDCODED CONSTANTS: Do not hardcode dates/values from examples. Derive formats (e.g., date output pattern) from expected output sample; otherwise infer from data dynamically.
        11. ROBUST PANDAS IO: Use engine='python', on_bad_lines='skip', explicit sep if needed; handle dates and numeric types reliably.
        
        VALUE MAPPING ANALYSIS:
        {value_mapping_guide}
        
        FULL COMPREHENSIVE ROADMAP (deliver in numbered steps):
        A. Input Pre-cleaning (text-level, before pandas) — when quality != 'clean':
           - Describe how to read lines, drop prose/comment/section headers, and keep only records with exactly the expected number of fields based on the expected output columns OR the dominant field count.
           - Propose regexes and rules (general, parameterized) to remove lines like report headers (e.g., "Generated on:", "Start of", etc.).
           - Suggest normalization (strip whitespace, unify delimiters to comma if needed), and how to write a clean temp CSV for pandas.
        A2. Header Localization by Expected Columns (robust):
           - Scan the raw file to find the first line that contains most of the expected output column names (case-insensitive).
           - Treat this line as the header; ignore all lines above it.
           - Ensure each subsequent data line has the same number of fields as there are expected columns; trim extras.
           - Keep ALL subsequent data lines until EOF (no fixed window like 20 lines).
           - Optimization: First check the first non-empty line; if it doesn't contain the expected columns, scan the whole file for the best match.
        A4. Quote-safe pre-clean (recommended):
           - Use csv.reader with detected delimiter and quotechar='"' to parse lines; skip obvious prose/comment lines.
           - Use csv.writer with quotechar='"', quoting=csv.QUOTE_MINIMAL to write a normalized temp CSV.
        A5. Tolerant row retention:
           - During pre-clean, do NOT drop rows solely due to under/over field counts. Trim extras and keep rows that meet a tolerance threshold (e.g., at least 50% of fields non-empty OR all required fields present). Missing fields should be allowed and later become NaN in pandas.
           - Drop extra unnamed columns post-load if they exist.
        A3. Column Importance & Null Policy (data-driven):
           - From the expected output sample/null counts, infer required vs optional columns.
           - Heuristics: columns named like /id|date|amount|total|currency/ are required; if the sample shows nulls for a column, classify as optional unless semantics say otherwise.
           - Document the required set explicitly for the coder.
        B. Robust Loading with pandas:
           - Use recommended read_csv parameters derived from cleaning recommendations (engine, sep, skiprows, on_bad_lines).
        C. Column Selection & Mapping:
           - Select only expected columns, rename/massage input columns to match expected names and order.
        D. Data Cleaning & Type Normalization:
           - Enforce dtypes, parse/format dates to match expected samples; handle numbers and signs.
        E. Row-level Rules (post-load in pandas):
           - Do NOT drop rows in pre-clean unless the line is clearly non-record.
           - After loading, drop rows only if required columns are null/invalid.
           - Allow optional columns (e.g., Status, Description) to be empty.
           - Consider soft thresholds (e.g., keep rows with at least 30% non-empty fields) only if necessary; prioritize required-field presence first.
        F. Validation:
           - Assert final columns/order match expected; optionally sample-compare formats.
        
        Please produce the roadmap as a numbered list of actionable steps, each specifying:
        - What to do (clearly labeled e.g., "Pre-cleaning", "Load", "Map Columns", "Normalize Dates")
        - The pandas or Python operations/methods to use (e.g., regex, csv module, pandas options)
        - Parameters/conditions (e.g., field count to keep, delimiter, date format)
        - Exactly how to handle out-of-schema values (drop/ignore/transform)
        
        Remember: Bias toward the expected output schema; the input may be messy or contain random content. Your plan must be generic and robust.
        """

        return prompt.strip()

    def _format_differences(self, differences: Dict[str, Any]) -> str:
        """Format the differences for the prompt."""
        formatted = []

        if differences.get("shape_changes"):
            shape_changes = differences["shape_changes"]
            formatted.append(f"Shape Changes: {shape_changes['input_shape']} -> {shape_changes['output_shape']}")

        if differences.get("column_changes"):
            col_changes = differences["column_changes"]
            if col_changes.get("added_columns"):
                formatted.append(f"Added Columns: {col_changes['added_columns']}")
            if col_changes.get("removed_columns"):
                formatted.append(f"Removed Columns: {col_changes['removed_columns']}")

        if differences.get("data_type_changes"):
            formatted.append("Data Type Changes:")
            for col, changes in differences["data_type_changes"].items():
                formatted.append(f"  - {col}: {changes['input_type']} -> {changes['output_type']}")

        return "\n".join(formatted) if formatted else "No significant structural differences detected"

    def _create_value_mapping_guide(self, input_sample: List[Dict], output_sample: List[Dict]) -> str:
        """Create a value mapping guide from sample data."""
        if not input_sample or not output_sample:
            return "No sample data available for value mapping."

        guide = []

        # Find common columns between input and output
        input_cols = set(input_sample[0].keys()) if input_sample else set()
        output_cols = set(output_sample[0].keys()) if output_sample else set()
        common_cols = input_cols & output_cols

        for col in common_cols:
            # Get unique values from input and output samples
            input_values = set()
            output_values = set()

            for row in input_sample:
                if col in row and row[col] is not None:
                    input_values.add(str(row[col]))

            for row in output_sample:
                if col in row and row[col] is not None:
                    output_values.add(str(row[col]))

            # If there are different values, create a mapping
            if input_values != output_values:
                guide.append(f"Column '{col}':")
                for input_val in sorted(input_values):
                    # Find corresponding output value
                    for output_val in sorted(output_values):
                        guide.append(f"  '{input_val}' -> '{output_val}'")

        # Look for new columns in output
        new_cols = output_cols - input_cols
        for col in new_cols:
            guide.append(f"New column '{col}':")
            output_values = set()
            for row in output_sample:
                if col in row and row[col] is not None:
                    output_values.add(str(row[col]))
            for val in sorted(output_values):
                guide.append(f"  Use value: '{val}'")

        return "\n".join(guide) if guide else "No value mappings needed."

    def _format_previous_attempts(self, previous_attempts: List[Dict[str, Any]]) -> str:
        """Format information about previous attempts for the prompt."""
        if not previous_attempts:
            return ""

        info = ["PREVIOUS ATTEMPT FAILURES (LEARN FROM THESE):"]

        for i, attempt in enumerate(previous_attempts, 1):
            tester_res = attempt.get("tester_result") or {}
            if isinstance(tester_res, dict) and "comparison_result" in tester_res:
                comparison = tester_res.get("comparison_result")
                if isinstance(comparison, dict):
                    suggestions = comparison.get("suggestions", [])
                    if suggestions:
                        info.append(f"Attempt {i} failed due to:")
                        for suggestion in suggestions:
                            info.append(f"  - {suggestion}")
                else:
                    # Execution error (no structured comparison). Surface error details if present.
                    err = tester_res.get("error") or "Test execution failed without comparison details"
                    info.append(f"Attempt {i} execution error: {err}")

        return "\n".join(info) + "\n"

    def _format_agent_feedback(self, agent_feedback: Dict[str, Any]) -> str:
        """Format agent feedback for the prompt."""
        if not agent_feedback:
            return ""

        feedback_info = ["AGENT FEEDBACK (INCORPORATE THESE INSIGHTS):"]

        if "coder_feedback" in agent_feedback:
            coder_feedback = agent_feedback["coder_feedback"]
            feedback_info.append("Coder Agent Feedback:")
            for feedback in coder_feedback:
                feedback_info.append(f"  - {feedback.get('suggestion', '')}")

        if "test_report" in agent_feedback:
            feedback_info.append("Test Report Insights:")
            feedback_info.append(f"  - {agent_feedback['test_report']}")

        return "\n".join(feedback_info) + "\n"

    def _parse_plan_output(
        self, plan_text: str, comparison: Dict[str, Any], output_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse the plan output into a structured format."""

        # Split the plan into steps (looking for numbered items)
        lines = plan_text.strip().split("\n")
        steps = []
        current_step = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this is a new numbered step
            if line and (line[0].isdigit() or line.startswith(("•", "-", "*"))):
                if current_step:
                    steps.append(current_step.strip())
                current_step = line
            else:
                current_step += " " + line

        # Add the last step
        if current_step:
            steps.append(current_step.strip())

        # Infer required vs optional columns from expected output analysis (generalized, not hardcoded)
        inferred_required, inferred_optional = self._infer_required_optional_columns(output_analysis)

        return {
            "steps": steps,
            "total_steps": len(steps),
            "complexity": self._assess_complexity(comparison),
            "estimated_time": "5-15 minutes",
            "key_operations": self._extract_key_operations(plan_text),
            "required_columns": inferred_required,
            "optional_columns": inferred_optional,
        }

    def _infer_required_optional_columns(self, output_analysis: Dict[str, Any]) -> tuple[list, list]:
        """Infer required vs optional columns from expected output profile in a generalized way.

        Heuristics (ordered):
        - Columns whose names match /id|date|amount|total|currency|qty|quantity|price/i are likely required
        - If sample/null_counts show non-zero nulls for a column, lean optional
        - Otherwise default to required
        """
        columns = output_analysis.get("columns", []) or []
        null_counts = output_analysis.get("null_counts", {}) or {}

        required: list = []
        optional: list = []

        import re as _re

        strong_required_pattern = _re.compile(r"(id|date|amount|total|currency|qty|quantity|price|number)", _re.I)

        for col in columns:
            name = str(col)
            likely_required = bool(strong_required_pattern.search(name))
            has_nulls = null_counts.get(col, 0) not in (None, 0)

            if likely_required and not has_nulls:
                required.append(col)
            elif likely_required and has_nulls:
                # still required but flag for post-load cleaning
                required.append(col)
            elif not likely_required and has_nulls:
                optional.append(col)
            else:
                # default required if nothing indicates optionality
                required.append(col)

        # Ensure we don't classify all as required if evidence is weak; keep at least one optional when nulls exist
        if not optional:
            for col in columns:
                if null_counts.get(col, 0):
                    optional.append(col)
        # Deduplicate and order as in original
        required = [c for c in columns if c in required and c not in optional]
        optional = [c for c in columns if c in optional]

        return required, optional

    def _assess_complexity(self, comparison: Dict[str, Any]) -> str:
        """Assess the complexity of the transformation."""
        differences = comparison["differences"]
        complexity_score = 0

        if differences.get("shape_changes"):
            complexity_score += 2

        if differences.get("column_changes"):
            col_changes = differences["column_changes"]
            complexity_score += len(col_changes.get("added_columns", []))
            complexity_score += len(col_changes.get("removed_columns", []))

        if differences.get("data_type_changes"):
            complexity_score += len(differences["data_type_changes"])

        if complexity_score == 0:
            return "Simple"
        elif complexity_score <= 3:
            return "Moderate"
        else:
            return "Complex"

    def _extract_key_operations(self, plan_text: str) -> list:
        """Extract key pandas operations mentioned in the plan."""
        operations = []
        common_ops = [
            "read_csv",
            "to_csv",
            "rename",
            "drop",
            "dropna",
            "fillna",
            "astype",
            "to_datetime",
            "merge",
            "concat",
            "groupby",
            "sort_values",
            "reset_index",
            "pivot",
            "melt",
        ]

        for op in common_ops:
            if op in plan_text.lower():
                operations.append(op)

        return operations
