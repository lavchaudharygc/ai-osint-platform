# OSINT Platform Architecture v1.0

```text
┌─────────────────────────────────────────────────┐
│                  FRONTEND (HTML/JS)             │
│  Search             Results          Report View│
└──────────────────┬──────────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────────┐
│              API GATEWAY (FastAPI)              │
│  Auth Middleware   Rate Limit   Validation      │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│           INVESTIGATION ORCHESTRATOR            │
│  1. Validate Request                            │
│  2. Fetch Primary Platform Data                 │
│  3. Cross-Platform Discovery                    │
│  4. AI Correlation Analysis                     │
│  5. Risk Assessment                             │
│  6. Generate Report                             │
│  7. Store Results                               │
└──────┬──────────┬──────────┬────────────────────┘
       │          │          │
┌──────▼──┐ ┌─────▼───┐ ┌────▼─────────┐
│ SCRAPER │ │   AI    │ │   REPORT     │
│ ENGINE  │ │ ENGINE  │ │  GENERATOR   │
└──────┬──┘ └─────┬───┘ └────┬─────────┘
       │          │          │
┌──────▼──────────▼──────────▼────────────────────┐
│              DATA LAYER                         │
│  PostgreSQL (primary)  Redis (cache)  File Store│
└─────────────────────────────────────────────────┘
```

## Module Communication

- Modules communicate through typed Python service interfaces and Pydantic schemas.
- Async operations support parallel checks across public profile platforms.
- The event bus in `backend/core/events.py` provides a lightweight path to WebSocket status updates.
- Data access is isolated behind SQLAlchemy models and FastAPI dependencies.

## Runtime Modules

- `backend/main.py`: FastAPI application assembly, CORS, health checks, routers.
- `backend/api/endpoints`: HTTP route handlers.
- `backend/services`: Provider-specific integration and username discovery services.
- `backend/schemas`: Request and response contracts.
- `backend/database`: SQL schema, ORM models, and Alembic migrations.

## Text Diagram Source

The editable Mermaid source for the architecture diagram is stored in `ARCHITECTURE_DIAGRAM.mmd` so code review and PR creation tools can render the change without binary-file support.
