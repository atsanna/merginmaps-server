"""Add audit log and webhooks

Revision ID: e1a0c0de0006
Revises: e1a0c0de0005
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0006"
down_revision = "e1a0c0de0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("happened_at", sa.DateTime(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(), nullable=True),
        sa.Column("actor_ip", sa.String(), nullable=True),
        sa.Column("actor_ua", sa.String(), nullable=True),
        sa.Column("actor_device", sa.String(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_workspace_id", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    for column in (
        "event_type",
        "happened_at",
        "actor_id",
        "target_project_id",
        "target_workspace_id",
    ):
        op.create_index(op.f(f"ix_audit_log_{column}"), "audit_log", [column])

    op.create_table(
        "webhook",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=False),
        sa.Column(
            "events", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("last_delivery_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
            name=op.f("fk_webhook_created_by_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_webhook_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook")),
    )
    op.create_index(op.f("ix_webhook_workspace_id"), "webhook", ["workspace_id"])


def downgrade():
    op.drop_index(op.f("ix_webhook_workspace_id"), table_name="webhook")
    op.drop_table("webhook")
    for column in (
        "event_type",
        "happened_at",
        "actor_id",
        "target_project_id",
        "target_workspace_id",
    ):
        op.drop_index(op.f(f"ix_audit_log_{column}"), table_name="audit_log")
    op.drop_table("audit_log")
