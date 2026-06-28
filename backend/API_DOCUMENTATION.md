# AI-OSINT Platform API Documentation

Base URL: `http://localhost:8000`

FastAPI also exposes interactive documentation at `/docs` and OpenAPI JSON at `/openapi.json`.

## Root API Info

`GET /`

Returns a small JSON index with health, documentation, investigation, history, and report endpoint URLs.

## Health Check

`GET /health`

Returns service status, timestamp, and API version.

## Username Investigation

`POST /api/v1/investigation/username`

Request body:

```json
{
  "username": "example_user",
  "platform": "instagram",
  "case_id": "CASE-001",
  "correlation_depth": 2
}
```

Supported primary platforms are `instagram`, `twitter`, `telegram`, and `linkedin`.
The response includes a generated investigation ID, primary platform data, cross-platform matches, a placeholder AI correlation summary, and a risk assessment.

## Investigation History

- `GET /api/v1/investigation/history?limit=20&offset=0`
- `GET /api/v1/investigation/history/{investigation_id}`

The current implementation uses an in-memory store for development. Production deployments should connect these endpoints to PostgreSQL.

## Report Generation

`POST /api/v1/reports/generate-report/{investigation_id}?format=pdf`

Supported formats are `pdf` and `html`. The endpoint validates the investigation exists and returns the future report URL.
