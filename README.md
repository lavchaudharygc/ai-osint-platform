# AI-OSINT Platform

AI-Assisted OSINT Investigation Platform for Indian Law Enforcement Agencies.

## Current Status
🚧 Sprint 1: Username OSINT Module (In Development)

## Team
- Lav (Team Lead / OSINT SME / Research)
- Developer 1 (Backend)
- Developer 2 (Frontend)
- OSINT Teammate 1 (Data Specialist)
- OSINT Teammate 2 (AI Training)
- Researcher 1 (Platform Research)
- Researcher 2 (AI Research)

## Tech Stack
- Backend: Python + FastAPI
- Frontend: HTML + CSS + JavaScript (Phase 1)
- AI: Groq API (Phase 1)
- Database: SQLite (Phase 1)

## Setup and Running Instructions

To run this platform locally, follow these steps to configure and boot both the backend API and the frontend dashboard.

### 1. Prerequisites
- **Python 3.10+** installed on your system.

---

### 2. Backend API Setup
The backend is a FastAPI application that processes scans, handles correlation, runs risk evaluations, and stores history logs.

1. Open a terminal and navigate to the `backend` directory:
   ```powershell
   cd backend
   ```
2. Create a virtual environment:
   ```powershell
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```
4. Install the required python packages:
   ```bash
   pip install -r requirements.txt
   ```
5. Configure environment variables. A `.env` file should be located in the `backend/` directory:
   - To configure the database cache file (defaults to SQLite):
     ```ini
     DATABASE_URL=sqlite:///./osint.db
     ```
   - To integrate the RapidAPI FlashAPI enrichment service for live target scans (optional):
     ```ini
     RAPIDAPI_KEY=your-rapidapi-key
     FLASHAPI_HOST=flashapi1.p.rapidapi.com
     FLASHAPI_BASE_URL=https://flashapi1.p.rapidapi.com
     ```
6. Start the API server:
   ```bash
   python -m backend.main
   ```
   The backend API service will bind to **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. You can view the OpenAPI interactive docs at `http://127.0.0.1:8000/docs`.

---

### 3. Frontend Web Server Setup
To bypass browser CORS security limitations when connecting to the local API, the frontend needs to be served from a web server on one of the backend's allowed origins (`http://127.0.0.1:5500`).

1. Open a new terminal session at the repository root folder.
2. Run Python's built-in lightweight HTTP server, specifying the `frontend` directory and port `5500`:
   ```bash
   python -m http.server 5500 --directory ./frontend
   ```
3. Open your web browser and navigate to:
   **[http://127.0.0.1:5500](http://127.0.0.1:5500)**

---

### 4. Accessing the Secure Portal
When the web page opens, you will be greeted by the **U.P. Police Cyber Cell preloader**. Once the backend API connection checks are verified, you will be prompted for security credentials.

Use the following default investigator access parameters:
- **Investigator ID / Username**: `uppolice`
- **Security Keyphrase / Password**: `testingaccount`

Once authorized, you can run target OSINT scans, view risk threat assessments, and click **Export Official PDF Report** to view and download dossier reports in paper print format.
