from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI-OSINT Platform",
    description="OSINT Investigation Tool for LEAs",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "status": "online",
        "platform": "AI-OSINT",
        "version": "0.1.0",
        "sprint": 1
    }

@app.post("/investigate")
def investigate(username: str, platform: str = "instagram"):
    """Main investigation endpoint"""
    return {
        "investigation_id": "INV-001",
        "username": username,
        "platform": platform,
        "status": "investigation_started",
        "message": f"Starting investigation for @{username} on {platform}"
    }