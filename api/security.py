from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from core.config import settings

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    # If the secret key is not set in the environment, disable security
    if not settings.fastapi_and_wep_app_secret_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key is missing")

    if not api_key_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key is missing")
    if api_key_header != settings.fastapi_and_wep_app_secret_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
