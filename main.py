"""Main FastAPI application for the AI CSV Converter."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.routes import router as api_router
from api.security import get_api_key
from core.config import settings
from core.logging import setup_logging
from models.schemas import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Setup logging first
    setup_logging()

    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")

    # Check OpenAI API key
    import os

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if api_key:
        logger.info("OpenAI API key loaded successfully")
        # Ensure it's set in environment for CrewAI
        os.environ["OPENAI_API_KEY"] = api_key
    else:
        logger.warning("OpenAI API key not found - AI agents will not work")

    # Ensure directories exist
    settings.upload_dir.mkdir(exist_ok=True)
    settings.temp_dir.mkdir(exist_ok=True)
    logger.info(f"Upload directory: {settings.upload_dir}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    
    # Initialize workflow executor
    from core.workflow_executor import workflow_executor
    logger.info(f"Workflow executor initialized with {workflow_executor.max_workers} workers")

    yield

    # Shutdown
    logger.info("Shutting down application")
    # Gracefully shutdown workflow executor
    workflow_executor.shutdown()
    logger.info("Workflow executor shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-powered CSV to CSV converter using CrewAI agents",
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(
        api_router, prefix="/api/v1", tags=["CSV Converter"], dependencies=[Depends(get_api_key)]
    )

    # Global exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions."""
        error_response = ErrorResponse(
            error=exc.detail or "An error occurred", detail=getattr(exc, "detail", None)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(mode='json'),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle general exceptions."""
        logger.error(f"Unhandled exception: {exc}")
        error_response = ErrorResponse(
            error="Internal server error", detail=str(exc) if settings.debug else None
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(mode='json'),
        )

    # Root endpoint - redirect to docs
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint - redirects to API documentation."""
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/docs")

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "app_name": settings.app_name, "version": settings.app_version}


    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
