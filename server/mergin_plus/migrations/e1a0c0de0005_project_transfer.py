"""Add project transfers

Revision ID: e1a0c0de0005
Revises: e1a0c0de0004
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0005"
down_revision = "e1a0c0de0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_transfer",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_workspace_id", sa.Integer(), nullable=False),
        sa.Column("to_workspace_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_workspace_id"],
            ["workspace.id"],
            name=op.f("fk_project_transfer_from_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_project_transfer_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["user.id"],
            name=op.f("fk_project_transfer_requested_by_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["to_workspace_id"],
            ["workspace.id"],
            name=op.f("fk_project_transfer_to_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_transfer")),
        sa.UniqueConstraint("project_id", name=op.f("uq_project_transfer_project_id")),
    )
    op.create_index(
        op.f("ix_project_transfer_expires_at"), "project_transfer", ["expires_at"]
    )
    op.create_index(
        op.f("ix_project_transfer_from_workspace_id"),
        "project_transfer",
        ["from_workspace_id"],
    )
    op.create_index(
        op.f("ix_project_transfer_to_workspace_id"),
        "project_transfer",
        ["to_workspace_id"],
    )


def downgrade():
    op.drop_index(
        op.f("ix_project_transfer_to_workspace_id"), table_name="project_transfer"
    )
    op.drop_index(
        op.f("ix_project_transfer_from_workspace_id"), table_name="project_transfer"
    )
    op.drop_index(op.f("ix_project_transfer_expires_at"), table_name="project_transfer")
    op.drop_table("project_transfer")
