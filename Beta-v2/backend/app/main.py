"""FastAPI application entrypoint for Beta-v2."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.investigation import router as investigation_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Government SOC / Law Enforcement OSINT Engine (Beta-v2)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation_router)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
