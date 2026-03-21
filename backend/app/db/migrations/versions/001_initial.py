"""Initial schema

Revision ID: 001
Revises: None
Create Date: 2026-03-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("seniority", sa.String(32), nullable=False),
        sa.Column("years_experience", sa.Integer, nullable=False, server_default="0"),
        sa.Column("work_type", sa.String(32), nullable=False, server_default="any"),
        sa.Column("salary_min", sa.Integer, nullable=True),
        sa.Column("salary_max", sa.Integer, nullable=True),
        sa.Column("raw_cv_text", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("url", sa.String(512), nullable=False, server_default=""),
        sa.Column("salary", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "match_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(64), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("probability", sa.Float, nullable=False),
        sa.Column("recommendation", sa.String(32), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("company", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", sa.String(255), nullable=False, server_default=""),
        sa.Column("match_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("applications")
    op.drop_table("match_scores")
    op.drop_table("jobs")
    op.drop_table("candidates")
