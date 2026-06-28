"""FastAPI application entry point for the AI-OSINT Platform."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.api.endpoints import investigation, reports
from backend.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Law Enforcement OSINT Investigation Tool",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation.router)
app.include_router(reports.router)


@app.get("/")
async def root() -> dict[str, object]:
    return {
        "name": settings.app_name,
        "status": "operational",
        "version": settings.app_version,
        "docs_url": "/docs",
        "health_url": "/health",
        "endpoints": {
            "investigate_username": "/api/v1/investigation/username",
            "investigation_history": "/api/v1/investigation/history",
            "generate_report": "/api/v1/reports/generate-report/{investigation_id}",
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "operational",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": settings.app_version,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
