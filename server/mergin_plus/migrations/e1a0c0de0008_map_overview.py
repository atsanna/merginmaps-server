"""Add web map overviews

Revision ID: e1a0c0de0008
Revises: e1a0c0de0007
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0008"
down_revision = "e1a0c0de0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "map_overview",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qgis_file", sa.String(), nullable=True),
        sa.Column("data_dir", sa.String(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("updated", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_map_overview_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_map_overview")),
    )


def downgrade():
    op.drop_table("map_overview")
