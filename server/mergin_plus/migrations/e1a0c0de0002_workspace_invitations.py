"""Add workspace invitations

Revision ID: e1a0c0de0002
Revises: e1a0c0de0001
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0002"
down_revision = "e1a0c0de0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_invitation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="workspace_role", create_type=False),
            nullable=False,
        ),
        sa.Column("inviter_id", sa.Integer(), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["inviter_id"],
            ["user.id"],
            name=op.f("fk_workspace_invitation_inviter_id_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_workspace_invitation_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_invitation")),
        sa.UniqueConstraint("uuid", name=op.f("uq_workspace_invitation_uuid")),
        sa.UniqueConstraint(
            "workspace_id",
            "email",
            name=op.f("uq_workspace_invitation_workspace_id"),
        ),
    )
    op.create_index(
        op.f("ix_workspace_invitation_email"), "workspace_invitation", ["email"]
    )
    op.create_index(
        op.f("ix_workspace_invitation_expires_at"),
        "workspace_invitation",
        ["expires_at"],
    )
    op.create_index(
        op.f("ix_workspace_invitation_workspace_id"),
        "workspace_invitation",
        ["workspace_id"],
    )


def downgrade():
    op.drop_index(
        op.f("ix_workspace_invitation_workspace_id"), table_name="workspace_invitation"
    )
    op.drop_index(
        op.f("ix_workspace_invitation_expires_at"), table_name="workspace_invitation"
    )
    op.drop_index(
        op.f("ix_workspace_invitation_email"), table_name="workspace_invitation"
    )
    op.drop_table("workspace_invitation")
