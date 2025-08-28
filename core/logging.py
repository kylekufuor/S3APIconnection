"""Logging configuration for the AI CSV Converter application."""

import sys
from pathlib import Path

from loguru import logger

from .config import settings


def setup_logging() -> None:
    """Configure application logging using loguru."""

    # Remove default handler
    logger.remove()

    # Console handler with color formatting
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(sys.stdout, format=log_format, level=settings.log_level, colorize=True, backtrace=True, diagnose=True)

    # File handler if log file is specified
    if settings.log_file:
        log_file_path = Path(settings.log_file)
        log_file_path.parent.mkdir(exist_ok=True)

        # File format without colors
        file_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"

        logger.add(
            log_file_path,
            format=file_format,
            level=settings.log_level,
            rotation="10 MB",
            retention="1 week",
            compression="zip",
            backtrace=True,
            diagnose=True,
        )

    # Log startup information
    logger.info(f"Logging configured - Level: {settings.log_level}")
    if settings.log_file:
        logger.info(f"Log file: {settings.log_file}")


def get_logger(name: str) -> "logger":
    """Get a logger instance with the specified name."""
    return logger.bind(name=name)
