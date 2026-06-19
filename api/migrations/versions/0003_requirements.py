"""requirements (exigences extraites d'un AO)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("obligation", sa.String(), nullable=False, server_default="obligatoire"),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="extracted"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_requirements_org_id", "requirements", ["org_id"])
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_index("ix_requirements_org_id", table_name="requirements")
    op.drop_table("requirements")
