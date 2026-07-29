"""FastAPI application entry point for the AI-OSINT Platform."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.api.endpoints import (
    apify,
    investigation,
    person_search_routes,
    providers,
    reports,
    training,
)
from backend.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    investigation.initialize_persistent_investigation_store()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Law Enforcement OSINT Investigation Tool",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation.router)
app.include_router(apify.router)
app.include_router(providers.router)
app.include_router(person_search_routes.router)
app.include_router(reports.router)
app.include_router(training.router)


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
            "apify_social_status": "/api/v1/apify/status",
            "provider_routing_status": "/api/v1/providers/status",
            "person_search": "/api/v1/person-search",
            "generate_report": "/api/v1/reports/generate-report/{investigation_id}",
            "training_dataset": "/api/v1/training/dataset/summary",
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
    # Do NOT include str(exc) in the response — it can leak internal paths,
    # module names, or sensitive data. Log it server-side instead.
    import logging as _logging
    _logging.getLogger(__name__).exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import os
    import uvicorn

    # Enable hot-reload only when DEBUG=1 is set explicitly.
    # Never enable in production — it spawns extra processes and
    # re-imports the entire application on every file change.
    _reload = os.environ.get("DEBUG", "").strip() in ("1", "true", "yes")
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=_reload)
