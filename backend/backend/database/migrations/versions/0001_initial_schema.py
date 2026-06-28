"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-26
"""

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with open("backend/database/schema.sql", encoding="utf-8") as schema_file:
        op.execute(schema_file.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS investigation_results CASCADE")
    op.execute("DROP TABLE IF EXISTS profile_matches CASCADE")
    op.execute("DROP TABLE IF EXISTS profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS investigations CASCADE")
