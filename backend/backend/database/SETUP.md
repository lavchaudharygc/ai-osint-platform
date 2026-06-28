# Database Setup

1. Create a PostgreSQL database and user.
2. Export `DATABASE_URL`, for example:
   `export DATABASE_URL=postgresql+psycopg://osint:osint@localhost:5432/osint`
3. Install backend dependencies from `requirements.txt`.
4. Run `alembic upgrade head` from the repository root.
5. For a manual bootstrap, run `psql "$DATABASE_URL" -f backend/database/schema.sql`.

The schema stores investigations, discovered profiles, match analysis, cached results, and scraping audit logs.

## ERD

The ERD is stored as Mermaid Markdown in `backend/database/ERD_DIAGRAM.md` to keep diagrams reviewable in text-only PR tooling.
