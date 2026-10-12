"""Add projects granted by workspace invitations

Revision ID: e1a0c0de0003
Revises: e1a0c0de0002
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0003"
down_revision = "e1a0c0de0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspace_invitation",
        sa.Column(
            "projects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("workspace_invitation", "projects")
