from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm_client import LLMServiceError

settings = get_settings()
_logger = get_logger(__name__)

app = FastAPI(title="Table Talk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMServiceError)
async def llm_service_error_handler(request: Request, exc: LLMServiceError) -> JSONResponse:
    _logger.error("LLM service error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "The AI service is temporarily unavailable. Please try again shortly."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Last-resort net: log the real exception server-side, never leak a
    # stack trace or internal detail to the client.
    _logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


app.include_router(health_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
