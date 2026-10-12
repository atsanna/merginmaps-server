"""Add workspace contributors limit

Revision ID: e1a0c0de0004
Revises: e1a0c0de0003
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1a0c0de0004"
down_revision = "e1a0c0de0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspace", sa.Column("contributors_limit", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("workspace", "contributors_limit")
