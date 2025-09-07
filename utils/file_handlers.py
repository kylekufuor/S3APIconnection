"""File handling utilities for CSV validation and processing."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import urlparse

import boto3
import pandas as pd  # type: ignore
from botocore.exceptions import ClientError
from fastapi import HTTPException
from loguru import logger

from core.config import settings
from models.schemas import JobMetadata, JobStatus


async def validate_csv_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate that a file is a properly formatted CSV.

    Args:
        file_path: Path to the CSV file to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Run pandas.read_csv in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, pd.read_csv, file_path)

        if df.empty:
            return False, "CSV file is empty"

        if len(df.columns) == 0:
            return False, "CSV file has no columns"

        logger.info(f"Validated CSV file: {file_path.name}, Shape: {df.shape}")
        return True, None

    except pd.errors.EmptyDataError:
        return False, "CSV file is empty or contains no data"
    except pd.errors.ParserError as e:
        return False, f"CSV parsing error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error reading CSV: {str(e)}"


def _read_text_lines(file_path: Path, max_lines: int = 200) -> List[str]:
    """Read first max_lines of a text file safely as UTF-8 with fallback encodings."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
            return lines[:max_lines]
    except Exception:
        try:
            with open(file_path, "r", encoding="latin-1", errors="replace") as f:
                lines = f.read().splitlines()
                return lines[:max_lines]
        except Exception:
            return []


def _guess_delimiter(lines: List[str]) -> str:
    """Guess a likely delimiter by counting occurrences across lines."""
    candidates = [",", "\t", ";", "|"]
    best = ","
    best_score: float = -1.0
    for cand in candidates:
        # Score: average count per line where count > 0
        counts = [line.count(cand) for line in lines if line and not line.strip().startswith(("#", "//", "--"))]
        counts = [c for c in counts if c > 0]
        if counts:
            score = sum(counts) / len(counts)
            if score > best_score:
                best = cand
                best_score = score
    return best


def _column_count_distribution(lines: List[str], delimiter: str) -> Dict[int, int]:
    """Return a histogram of field counts per non-empty, non-comment line."""
    dist: Dict[int, int] = {}
    for line in lines:
        if not line or not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith(("#", "//", "--")):
            continue
        # Heuristic: ignore obvious section separators
        if set(stripped) <= {"-", "_", " "}:
            continue
        count = len([*stripped.split(delimiter)])
        dist[count] = dist.get(count, 0) + 1
    return dist


def _detect_header_index(lines: List[str], delimiter: str, expected_min_cols: int = 2) -> Optional[int]:
    """Detect the first plausible header line index based on token-ness and consistency."""
    for idx, line in enumerate(lines):
        tokens = [t.strip() for t in line.split(delimiter)]
        if len(tokens) < expected_min_cols:
            continue
        # Header heuristic: majority tokens are alphabetic or alphanumeric header-like strings
        headerish = sum(1 for t in tokens if t and any(ch.isalpha() for ch in t))
        if headerish / max(1, len(tokens)) >= 0.5:
            return idx
    return None


def analyze_raw_text_quality(file_path: Path) -> Dict[str, Any]:
    """
    Lightweight, delimiter-agnostic scan to assess input text quality and suggest cleaning.

    Returns a dictionary with keys:
      - sample_lines: first N lines
      - delimiter_guess
      - column_count_distribution
      - dominant_field_count
      - header_index_guess
      - leading_noise_lines
      - messy_indicators: list[str]
      - quality_label: "clean" | "semi-structured" | "messy"
      - cleaning_recommendations: dict
    """
    lines = _read_text_lines(file_path)
    delimiter = _guess_delimiter(lines)
    dist = _column_count_distribution(lines, delimiter)
    dominant_fields = None
    if dist:
        dominant_fields = max(dist.items(), key=lambda x: x[1])[0]

    header_idx = _detect_header_index(lines, delimiter)
    leading_noise = header_idx if header_idx is not None else 0

    messy_indicators: List[str] = []
    if not lines:
        messy_indicators.append("file_empty_or_unreadable")
    if header_idx is None:
        messy_indicators.append("header_not_found")
    if dominant_fields is None or (
        len(dist.keys()) > 1 and (sum(dist.values()) - dist.get(dominant_fields, 0)) / max(1, sum(dist.values())) > 0.2
    ):
        messy_indicators.append("inconsistent_field_counts")
    # Heuristics for prose/comment style lines near start
    prose_tokens = ["generated on", "prepared by", "start of", "report", "summary", "financial"]
    first_nonempty = " ".join(lines[:10]).lower()
    if any(tok in first_nonempty for tok in prose_tokens):
        messy_indicators.append("introductory_prose_detected")

    # Quality label
    if not messy_indicators:
        quality = "clean"
    elif len(messy_indicators) == 1 and messy_indicators[0] == "inconsistent_field_counts":
        quality = "semi-structured"
    else:
        quality = "messy"

    cleaning_recs: Dict[str, Any] = {
        "skip_rows": leading_noise,
        "delimiter": delimiter,
        "enforce_field_count": dominant_fields,
        "drop_extra_fields": True,
        "strip_whitespace": True,
        "on_bad_lines": "skip",  # for pandas engine='python'
        "engine": "python",
        "comment_prefixes": ["#", "//", "--"],
        "keep_line_rule": (
            f"keep only lines that split into exactly {dominant_fields} fields by '{delimiter}'"
            if dominant_fields
            else "keep lines that look like CSV records"
        ),
    }

    return {
        "sample_lines": lines[:30],
        "delimiter_guess": delimiter,
        "column_count_distribution": dist,
        "dominant_field_count": dominant_fields,
        "header_index_guess": header_idx,
        "leading_noise_lines": leading_noise,
        "messy_indicators": messy_indicators,
        "quality_label": quality,
        "cleaning_recommendations": cleaning_recs,
    }


async def analyze_csv_structure(file_path: Path) -> Dict[str, Any]:
    """
    Analyze the structure of a CSV file.

    Args:
        file_path: Path to the CSV file to analyze

    Returns:
        Dictionary containing CSV structure information
    """
    try:
        # Raw text quality scan first to inform planner about cleanliness
        raw_quality = analyze_raw_text_quality(file_path)

        loop = asyncio.get_event_loop()
        # Try robust pandas read with hints from raw analysis
        read_kwargs: Dict[str, Any] = {}
        if raw_quality.get("quality_label") != "clean":
            # Use python engine and tolerant parsing
            read_kwargs = {
                "engine": "python",
                "on_bad_lines": "skip",
            }
            # If we have a header index guess, attempt to skip prelude
            header_idx = raw_quality.get("header_index_guess")
            if isinstance(header_idx, int) and header_idx > 0:
                read_kwargs["skiprows"] = header_idx
            # Provide delimiter guess when obvious
            delimiter = raw_quality.get("delimiter_guess")
            if delimiter:
                read_kwargs["sep"] = delimiter

        df = await loop.run_in_executor(None, lambda: pd.read_csv(file_path, **read_kwargs))

        # Basic structure info
        structure: Dict[str, Any] = {
            "filename": file_path.name,
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": df.dtypes.astype(str).to_dict(),
            "null_counts": df.isnull().sum().to_dict(),
            "sample_data": df.head().to_dict("records") if not df.empty else [],
            "raw_text_analysis": raw_quality,
        }

        # Additional statistics for numeric columns
        numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
        if numeric_columns:
            structure["numeric_stats"] = df[numeric_columns].describe().to_dict()

        # String column analysis
        string_columns = df.select_dtypes(include=["object"]).columns.tolist()
        if string_columns:
            structure["string_stats"] = {}
            for col in string_columns:
                unique_vals = df[col].nunique()
                structure["string_stats"][col] = {
                    "unique_count": unique_vals,
                    "unique_values": df[col].unique()[:10].tolist(),  # First 10 unique values
                }

        logger.info(f"Analyzed CSV structure for: {file_path.name}")
        return structure

    except Exception as e:
        logger.error(f"Error analyzing CSV structure: {str(e)}")
        raise


async def compare_csv_structures(input_path: Path, expected_output_path: Path) -> Dict:
    """
    Compare the structures of input and expected output CSV files.

    Args:
        input_path: Path to the input CSV file
        expected_output_path: Path to the expected output CSV file

    Returns:
        Dictionary containing comparison results
    """
    try:
        # Analyze both files
        input_structure = await analyze_csv_structure(input_path)
        output_structure = await analyze_csv_structure(expected_output_path)

        comparison = {
            "input": input_structure,
            "expected_output": output_structure,
            "differences": {
                "column_changes": {},
                "shape_changes": {},
                "data_type_changes": {},
            },
        }

        # Compare shapes
        if input_structure["shape"] != output_structure["shape"]:
            comparison["differences"]["shape_changes"] = {
                "input_shape": input_structure["shape"],
                "output_shape": output_structure["shape"],
                "rows_changed": output_structure["shape"][0] - input_structure["shape"][0],
                "columns_changed": output_structure["shape"][1] - input_structure["shape"][1],
            }

        # Compare columns
        input_cols = set(input_structure["columns"])
        output_cols = set(output_structure["columns"])

        if input_cols != output_cols:
            comparison["differences"]["column_changes"] = {
                "added_columns": list(output_cols - input_cols),
                "removed_columns": list(input_cols - output_cols),
                "common_columns": list(input_cols & output_cols),
            }

        # Compare data types for common columns
        common_cols = input_cols & output_cols
        dtype_changes = {}
        for col in common_cols:
            if input_structure["dtypes"].get(col) != output_structure["dtypes"].get(col):
                dtype_changes[col] = {
                    "input_type": input_structure["dtypes"].get(col),
                    "output_type": output_structure["dtypes"].get(col),
                }

        if dtype_changes:
            comparison["differences"]["data_type_changes"] = dtype_changes

        logger.info("Completed CSV structure comparison")
        return comparison

    except Exception as e:
        logger.error(f"Error comparing CSV structures: {str(e)}")
        raise


def cleanup_temp_files(job_id: str) -> None:
    """
    Clean up temporary files associated with a job.

    Args:
        job_id: The job ID to clean up files for
    """
    from core.config import settings

    try:
        # Find and remove files matching the job ID pattern
        temp_files = list(settings.temp_dir.glob(f"*{job_id}*"))

        for file_path in temp_files:
            file_path.unlink()
            logger.info(f"Cleaned up temp file: {file_path}")

    except Exception as e:
        logger.error(f"Error cleaning up temp files for job {job_id}: {str(e)}")


def ensure_user_directory(client_id: str) -> Path:
    """
    Ensure that a user-specific directory exists.

    Args:
        client_id: The client ID

    Returns:
        Path to the user directory
    """
    from core.config import settings

    user_dir = settings.temp_dir / str(client_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Ensured user directory exists: {user_dir}")
    return user_dir


async def save_generated_script_to_s3(script_content: str, client_id: str, job_id: str) -> str:
    """
    Save a generated Python script to S3.

    Args:
        script_content: The Python script content
        client_id: The client ID (user_id)
        job_id: The job ID for reference

    Returns:
        The S3 path to the saved script file
    """
    s3_client = get_s3_client()
    bucket_name = settings.aws_bucket_name
    user_id = str(client_id)
    script_name = f"generatedScript_{job_id}.py"
    script_key = f"{user_id}/{job_id}/script/{script_name}"
    script_path = f"s3://{bucket_name}/{script_key}"

    try:
        s3_client.put_object(Bucket=bucket_name, Key=script_key, Body=script_content.encode("utf-8"))
        logger.info(f"Saved user script to S3: {script_path}")
        return script_path

    except ClientError as e:
        logger.error(f"Error saving user script to S3: {e}")
        raise


async def _cleanup_old_job_scripts(user_dir: Path, job_id: str, current_script_name: str) -> None:
    """
    Clean up any old script files for the same job ID to prevent accumulation.

    Args:
        user_dir: User directory path
        job_id: Current job ID
        current_script_name: Name of the current script file to keep
    """
    try:
        # Find and remove old scripts for this job (with different naming patterns)
        pattern_variants = [
            f"generatedScript_*_{job_id}_*.py",  # Old timestamp-based naming
            f"generatedScript_{job_id}_*.py",  # Current job-based naming
        ]

        for pattern in pattern_variants:
            for old_script in user_dir.glob(pattern):
                if old_script.name != current_script_name:
                    try:
                        old_script.unlink()
                        logger.info(f"Cleaned up old script: {old_script}")
                    except Exception as e:
                        logger.warning(f"Could not remove old script {old_script}: {e}")

    except Exception as e:
        logger.warning(f"Error during script cleanup: {e}")
        # Don't fail the main operation if cleanup fails


def get_user_scripts(client_id: str) -> List[Dict]:
    """
    Get all scripts for a specific user, sorted by creation time.

    Args:
        client_id: The client ID

    Returns:
        List of script information dictionaries
    """
    from core.config import settings

    user_dir = settings.temp_dir / str(client_id)

    if not user_dir.exists():
        logger.info(f"No directory found for user {client_id}")
        return []

    scripts: List[Dict[str, Any]] = []
    script_pattern = f"generatedScript_*_{client_id}.py"

    try:
        for script_path in user_dir.glob(script_pattern):
            # Handle both old timestamp-based and new job-based naming conventions
            filename_parts = script_path.stem.split("_")
            if len(filename_parts) >= 3:
                second_part = filename_parts[1]

                try:
                    # Try to parse as timestamp (old format)
                    timestamp_ms = int(second_part)
                    if timestamp_ms > 1000000000000:  # Sanity check for millisecond timestamp
                        created_at = timestamp_ms / 1000  # Convert to seconds
                        timestamp_ms_val = timestamp_ms
                    else:
                        raise ValueError("Not a valid timestamp")
                except ValueError:
                    # New job-based format: use file modification time
                    created_at = script_path.stat().st_mtime
                    timestamp_ms_val = int(created_at * 1000)  # Convert to ms for sorting compatibility

                scripts.append(
                    {
                        "script_name": script_path.name,
                        "file_path": str(script_path),
                        "timestamp_ms": timestamp_ms_val,
                        "created_at": created_at,
                    }
                )

        # Sort by timestamp (newest first)
        scripts.sort(key=lambda x: int(cast(int, x.get("timestamp_ms", 0))), reverse=True)
        logger.info(f"Found {len(scripts)} scripts for user {client_id}")

    except Exception as e:
        logger.error(f"Error getting user scripts: {str(e)}")
        return []

    return scripts


def get_latest_user_script(client_id: str) -> Optional[Path]:
    """
    Get the latest script for a specific user.

    Args:
        client_id: The client ID

    Returns:
        Path to the latest script file, or None if no scripts found
    """
    scripts = get_user_scripts(client_id)

    if not scripts:
        logger.info(f"No scripts found for user {client_id}")
        return None

    latest_script_path = Path(scripts[0]["file_path"])
    logger.info(f"Latest script for user {client_id}: {latest_script_path.name}")
    return latest_script_path


def list_all_users() -> List[str]:
    """
    List all users who have generated scripts.

    Returns:
        List of client IDs
    """
    from core.config import settings

    users = []

    try:
        for user_dir in settings.temp_dir.iterdir():
            if user_dir.is_dir():
                users.append(user_dir.name)

        logger.info(f"Found {len(users)} users with scripts")

    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return []

    return sorted(users)


def safe_file_path(file_path: Path) -> str:
    """
    Convert a file path to a string that's safe for subprocess calls.

    Args:
        file_path: Path object to convert

    Returns:
        String representation safe for subprocess calls
    """
    return str(file_path.resolve())


def validate_file_exists(file_path: Path, file_type: str = "file") -> tuple[bool, str]:
    """
    Validate that a file exists and is accessible.

    Args:
        file_path: Path to the file to validate
        file_type: Type of file for error messages (e.g., "script", "input", "output")

    Returns:
        Tuple of (exists, error_message)
    """
    if not file_path.exists():
        return False, f"{file_type.title()} file not found: {file_path}"

    if not file_path.is_file():
        return False, f"{file_type.title()} path is not a file: {file_path}"

    try:
        with open(file_path, "r") as f:
            pass
        return True, ""
    except (OSError, IOError):
        return False, f"{file_type.title()} file is not readable: {file_path}"


def get_s3_client():
    """Get a boto3 S3 client."""
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=boto3.session.Config(
            connect_timeout=10,
            read_timeout=30,
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
    )


def s3_folder_exists(s3_client, bucket_name, folder_path):
    """Check if a folder exists in S3."""
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_path)
        return "Contents" in response
    except ClientError as e:
        logger.error(f"Error checking S3 folder: {e}")
        return False


async def create_s3_folders(user_id: str, job_id: str):
    """Create the folder structure in S3 for a job."""
    loop = asyncio.get_event_loop()

    def _create_folders():
        s3_client = get_s3_client()
        bucket_name = settings.aws_bucket_name

        base_path = f"{user_id}/{job_id}/"
        folders_to_create = ["input/", "output/", "script/"]

        for folder in folders_to_create:
            folder_path = f"{base_path}{folder}"
            if not s3_folder_exists(s3_client, bucket_name, folder_path):
                try:
                    s3_client.put_object(Bucket=bucket_name, Key=folder_path)
                    logger.info(f"Created S3 folder: {folder_path}")
                except ClientError as e:
                    logger.error(f"Error creating S3 folder: {e}")
                    raise

    await loop.run_in_executor(None, _create_folders)


async def upload_to_s3(source: str, s3_path: str):
    """Upload a file to S3 from a URL, local path, or base64 string."""
    loop = asyncio.get_event_loop()
    bucket_name = settings.aws_bucket_name

    try:
        if source.startswith("s3://"):
            source_bucket, source_key = source.replace("s3://", "").split("/", 1)

            if source_bucket == bucket_name and source_key == s3_path:
                logger.info(f"Source and destination are the same, skipping copy: {source}")
                return

            logger.info(f"Copying file from {source} to s3://{bucket_name}/{s3_path}")

            def _copy_s3_object():
                s3_client = get_s3_client()
                copy_source = {"Bucket": source_bucket, "Key": source_key}
                s3_client.copy_object(CopySource=copy_source, Bucket=bucket_name, Key=s3_path)

            await loop.run_in_executor(None, _copy_s3_object)

        elif source.startswith("http://") or source.startswith("https://"):
            # Handle URL
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(source)
                response.raise_for_status()

                def _upload_from_url():
                    s3_client = get_s3_client()
                    s3_client.put_object(Bucket=bucket_name, Key=s3_path, Body=response.content)

                await loop.run_in_executor(None, _upload_from_url)
        else:
            # Handle base64 encoded data
            try:
                # Handle data URI format or plain base64
                if ";base64," in source:
                    data = base64.b64decode(source.split(";base64,")[-1])
                else:
                    data = base64.b64decode(source)
            except Exception as decode_error:
                logger.error(f"Failed to decode base64 data: {decode_error}")
                raise ValueError(f"Invalid base64 data: {decode_error}")

            def _upload_from_base64():
                s3_client = get_s3_client()
                s3_client.put_object(Bucket=bucket_name, Key=s3_path, Body=data)

            await loop.run_in_executor(None, _upload_from_base64)

        logger.info(f"Uploaded file to S3: {s3_path}")

    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload: {e}")
        raise


async def save_job_metadata_to_s3(metadata: JobMetadata, user_id: str, job_id: str):
    """Save the job metadata to a JSON file in S3."""
    loop = asyncio.get_event_loop()

    def _save_metadata():
        s3_client = get_s3_client()
        bucket_name = settings.aws_bucket_name
        metadata_path = f"{user_id}/{job_id}/job_metadata.json"

        try:
            s3_client.put_object(Bucket=bucket_name, Key=metadata_path, Body=metadata.model_dump_json(indent=2))
            logger.info(f"Saved job metadata to S3: {metadata_path}")
        except ClientError as e:
            logger.error(f"Error saving job metadata to S3: {e}")
            raise

    await loop.run_in_executor(None, _save_metadata)


async def update_job_metadata_to_s3(
    job: Dict[str, Any],
    job_id: str,
    status: JobStatus,
    progress_details: Dict[str, Any],
):
    """Update job metadata to S3."""
    loop = asyncio.get_event_loop()

    try:
        client_id = job.get("client_id")
        if client_id:
            bucket_name = settings.aws_bucket_name
            job_metadata_path = f"{client_id}/{job_id}/job_metadata.json"

            def _update_metadata():
                s3_client = get_s3_client()
                response = s3_client.get_object(Bucket=bucket_name, Key=job_metadata_path)
                metadata_content = response["Body"].read().decode("utf-8")
                metadata = JobMetadata.model_validate_json(metadata_content)

                metadata.job_status = status
                metadata.finished_at = job["completed_at"]

                if progress_details and "script_path" in progress_details:
                    metadata.script_path = progress_details["script_path"]

                return metadata

            metadata = await loop.run_in_executor(None, _update_metadata)
            await save_job_metadata_to_s3(metadata, client_id, job_id)
    except ClientError as e:
        logger.error(f"Failed to update S3 metadata for job {job_id}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while updating S3 metadata for job {job_id}: {e}")


def download_from_s3(s3_path: str, local_path: Path):
    """Download a file from S3 to a local path."""
    s3_client = get_s3_client()
    try:
        parsed_url = urlparse(s3_path)
        bucket_name = parsed_url.netloc
        key = parsed_url.path.lstrip("/")
        s3_client.download_file(bucket_name, key, str(local_path))
        logger.info(f"Downloaded file from S3: {s3_path} to {local_path}")
    except ClientError as e:
        logger.error(f"Error downloading from S3: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 download: {e}")
        raise


# Simple cache for user jobs (cache for 30 seconds)
_user_jobs_cache = {}
_cache_ttl = 30  # seconds

async def get_job_metadata_from_s3(client_id: str, job_id: str) -> Dict[str, Any]:
    """Retrieve specific job metadata from S3.
    
    Args:
        client_id: The user/client ID
        job_id: The specific job ID
        
    Returns:
        Dictionary containing the job metadata
        
    Raises:
        HTTPException: If job not found or access denied
    """
    try:
        bucket_name = settings.aws_bucket_name
        metadata_key = f"{client_id}/{job_id}/job_metadata.json"
        
        logger.info(f"Fetching job metadata: s3://{bucket_name}/{metadata_key}")
        
        # Download metadata file from S3
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=metadata_key)
        metadata_content = response['Body'].read().decode('utf-8')
        
        # Parse JSON metadata
        job_metadata = json.loads(metadata_content)
        
        logger.info(f"Successfully retrieved metadata for job {job_id}")
        return job_metadata
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            logger.error(f"Job metadata not found: {client_id}/{job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found for user {client_id}"
            )
        elif error_code == 'AccessDenied':
            logger.error(f"Access denied to job metadata: {client_id}/{job_id}")
            raise HTTPException(
                status_code=403,
                detail="Access denied to job metadata"
            )
        else:
            logger.error(f"S3 error retrieving job metadata: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve job metadata from S3"
            )
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in job metadata: {e}")
        raise HTTPException(
            status_code=500,
            detail="Job metadata file is corrupted"
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving job metadata: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve job metadata"
        )


async def get_user_jobs_from_s3(client_id: str) -> List[Dict[str, Any]]:
    """
    List all jobs for a user by reading metadata from S3.
    Implements simple caching to avoid repeated S3 calls.

    Args:
        user_id: The ID of the user.

    Returns:
        A list of job metadata dictionaries.
    """
    import time
    
    # Check cache first
    cache_key = f"user_jobs_{user_id}"
    current_time = time.time()
    
    if cache_key in _user_jobs_cache:
        cached_data, cached_time = _user_jobs_cache[cache_key]
        if current_time - cached_time < _cache_ttl:
            logger.info(f"Returning cached jobs for user {user_id}")
            return cached_data
    
    loop = asyncio.get_event_loop()

    def _get_user_jobs():
        s3_client = get_s3_client()
        bucket_name = settings.aws_bucket_name
        prefix = f"{user_id}/"

        jobs = []
        try:
            # List objects with the user's prefix
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter="/")

            for page in pages:
                if "CommonPrefixes" not in page:
                    continue

                for common_prefix in page.get("CommonPrefixes", []):
                    job_id = common_prefix.get("Prefix").split("/")[-2]
                    metadata_key = f"{user_id}/{job_id}/job_metadata.json"

                    try:
                        metadata_obj = s3_client.get_object(Bucket=bucket_name, Key=metadata_key)
                        metadata_content = metadata_obj["Body"].read().decode("utf-8")
                        jobs.append(json.loads(metadata_content))
                    except ClientError as e:
                        if e.response["Error"]["Code"] == "NoSuchKey":
                            logger.warning(f"Metadata file not found for job {job_id} of user {user_id}")
                        else:
                            raise
        except ClientError as e:
            logger.error(f"Error listing jobs for user {user_id} from S3: {e}")
            raise

        return jobs
    
    jobs = await loop.run_in_executor(None, _get_user_jobs)
    
    # Cache the result
    _user_jobs_cache[cache_key] = (jobs, current_time)
    logger.info(f"Cached {len(jobs)} jobs for user {user_id}")
    
    return jobs


async def delete_s3_job_folder(user_id: str, job_id: str) -> None:
    """
    Deletes a specific job folder and all its contents from the S3 bucket.

    Args:
        user_id: The ID of the user.
        job_id: The ID of the job to delete.
    """
    loop = asyncio.get_event_loop()

    def _delete_job_folder():
        s3_client = get_s3_client()
        bucket_name = settings.aws_bucket_name
        prefix = f"{user_id}/{job_id}/"

        try:
            objects_to_delete = []
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        objects_to_delete.append({"Key": obj["Key"]})

            if objects_to_delete:
                s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects_to_delete})
                logger.info(f"Deleted {len(objects_to_delete)} objects from S3 for job {job_id} of user {user_id}")
            else:
                logger.info(f"No objects found to delete for job {job_id} of user {user_id}")

        except ClientError as e:
            logger.error(f"Error deleting job folder {job_id} for user {user_id} from S3: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during S3 job folder deletion: {e}")
            raise

    await loop.run_in_executor(None, _delete_job_folder)


async def delete_and_replace_job_folder(user_id: str, job_id: str) -> bool:
    """Delete an existing job folder completely to prepare for replacement.
    
    Args:
        user_id: The user/client ID
        job_id: The job ID to delete and replace
        
    Returns:
        bool: True if deletion was successful or job didn't exist
        
    Raises:
        Exception: If deletion fails due to S3 errors
    """
    try:
        bucket_name = settings.aws_bucket_name
        job_prefix = f"{user_id}/{job_id}/"
        
        logger.info(f"🗑️ Deleting existing job folder for replacement: s3://{bucket_name}/{job_prefix}")
        
        # Get S3 client
        s3_client = get_s3_client()
        
        # List all objects with the job prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=job_prefix)
        
        objects_to_delete = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    objects_to_delete.append({'Key': obj['Key']})
        
        if not objects_to_delete:
            logger.info(f"No existing job folder found for {user_id}/{job_id} - proceeding with new job creation")
            return True
        
        # Delete all objects in batches (max 1000 per batch)
        for i in range(0, len(objects_to_delete), 1000):
            batch = objects_to_delete[i:i + 1000]
            
            s3_client.delete_objects(
                Bucket=bucket_name,
                Delete={
                    'Objects': batch,
                    'Quiet': True
                }
            )
            
            logger.info(f"Deleted batch of {len(batch)} objects from job folder")
        
        logger.info(f"✅ Successfully deleted existing job folder {user_id}/{job_id} ({len(objects_to_delete)} objects)")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            logger.error(f"S3 bucket not found: {bucket_name}")
            raise Exception(f"S3 bucket {bucket_name} does not exist")
        else:
            logger.error(f"S3 error during job folder deletion: {e}")
            raise Exception(f"Failed to delete existing job folder: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during job folder deletion: {e}")
        raise Exception(f"Failed to delete existing job folder: {e}")


async def delete_s3_user_folder(user_id: str):
    """
    Deletes a whole user folder and all its contents from the S3 bucket.

    Args:
        user_id: The ID of the user whose folder is to be deleted.
    """
    loop = asyncio.get_event_loop()
    
    def _delete_user_folder():
        s3_client = get_s3_client()
        bucket_name = settings.aws_bucket_name
        prefix = f"{user_id}/"

        try:
            objects_to_delete = []
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        objects_to_delete.append({"Key": obj["Key"]})

            if objects_to_delete:
                s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects_to_delete})
                logger.info(f"Deleted {len(objects_to_delete)} objects from S3 for user {user_id}")
            else:
                logger.info(f"No objects found to delete for user {user_id}")

        except ClientError as e:
            logger.error(f"Error deleting user folder {user_id} from S3: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during S3 user folder deletion: {e}")
            raise
    
    await loop.run_in_executor(None, _delete_user_folder)
