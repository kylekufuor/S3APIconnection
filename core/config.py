"""Configuration settings for the AI CSV Converter application.
### How `config.py` reads from .env

- load_dotenv() is called at import time. It loads key=value pairs from a `.env` file into process environment variables (`os.environ`).
- `Settings` extends `BaseSettings` (pydantic-settings). When `settings = Settings()` is instantiated, it reads values from the environment and applies them to fields (e.g., `openai_api_key`, `openai_model`, `log_level`, etc.). Any field not set in the environment uses the default in the class.
- The inner `Config` specifies `env_file = ".env"` and `env_file_encoding = "utf-8"`, so pydantic-settings also knows to read from `.env`. Combined with `load_dotenv()`, either mechanism will populate fields from `.env`.

Priority: environment > defaults. So values in `.env` override the defaults in the class.

Example `.env` (put at project root):
- OPENAI_API_KEY=sk-xxxx
- OPENAI_MODEL=gpt-4o-mini
- LOG_LEVEL=DEBUG
- UPLOAD_DIR=/absolute/path/uploads
- TEMP_DIR=/absolute/path/temp

How to use in code:
- from app.core.config import settings
- settings.openai_api_key  # pulled from .env if present
- settings.upload_dir  # overrides default if UPLOAD_DIR is set

Note: On Linux/macOS, environment variable names are case-sensitive. Use uppercase names (e.g., OPENAI_API_KEY) to map to `openai_api_key`.

"""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Settings
    app_name: str = "AI CSV Converter"
    app_version: str = "0.1.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # File Storage Settings
    upload_dir: Path = Path(__file__).parent.parent.parent / "uploads"
    temp_dir: Path = Path(__file__).parent.parent.parent / "temp"
    max_file_size: int = 10 * 1024 * 1024  # 10MB

    # CrewAI Settings
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    openai_temperature: float = 0.1

    # Logging Settings
    log_level: str = "INFO"
    log_file: Optional[str] = None
    otel_sdk_disabled: bool = True
    otel_traces_exporter: str = "none"

    # aws settings
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: str = "madular-data-files"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __post_init__(self) -> None:
        """Create necessary directories after initialization."""
        self.upload_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)


# Global settings instance
settings = Settings()
