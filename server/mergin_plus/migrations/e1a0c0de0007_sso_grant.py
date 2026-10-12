"""Add SSO grants

Revision ID: e1a0c0de0007
Revises: e1a0c0de0006
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0007"
down_revision = "e1a0c0de0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sso_grant",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sso_grant")),
    )
    op.create_index(op.f("ix_sso_grant_expires_at"), "sso_grant", ["expires_at"])


def downgrade():
    op.drop_index(op.f("ix_sso_grant_expires_at"), table_name="sso_grant")
    op.drop_table("sso_grant")
