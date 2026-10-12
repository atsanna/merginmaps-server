"""Add workspaces and workspace members

Creates the global CE workspace (id 1) as a real workspace so existing projects keep working,
its members are derived from superusers and GLOBAL_ADMIN/GLOBAL_WRITE/GLOBAL_READ settings.

Revision ID: e1a0c0de0001
Revises:
Create Date: 2026-10-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1a0c0de0001"
down_revision = None
branch_labels = ("enterprise",)
depends_on = "d8a2f6c1e5b4"


def _global_settings():
    try:
        from flask import current_app

        cfg = current_app.config
        return (
            cfg.get("GLOBAL_WORKSPACE", "mergin"),
            cfg.get("GLOBAL_STORAGE", 1024**3),
            cfg.get("GLOBAL_ADMIN", False),
            cfg.get("GLOBAL_WRITE", False),
            cfg.get("GLOBAL_READ", False),
        )
    except RuntimeError:
        return "mergin", 1024**3, False, False, False


def upgrade():
    workspace_role = postgresql.ENUM(
        "guest",
        "reader",
        "editor",
        "writer",
        "admin",
        "owner",
        name="workspace_role",
    )
    op.create_table(
        "workspace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("storage", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.Column("removed_by", sa.Integer(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["removed_by"],
            ["user.id"],
            name=op.f("fk_workspace_removed_by_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace")),
    )
    op.create_index(op.f("ix_workspace_active"), "workspace", ["active"])
    op.create_index(op.f("ix_workspace_removed_at"), "workspace", ["removed_at"])
    op.create_index(
        "ix_workspace_name_lower",
        "workspace",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_table(
        "workspace_member",
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", workspace_role, nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_workspace_member_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_workspace_member_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id", "user_id", name=op.f("pk_workspace_member")
        ),
    )
    op.create_index(
        op.f("ix_workspace_member_user_id"), "workspace_member", ["user_id"]
    )

    # migrate CE global workspace
    conn = op.get_bind()
    has_data = conn.execute(
        sa.text(
            'SELECT EXISTS (SELECT 1 FROM project) OR EXISTS (SELECT 1 FROM "user")'
        )
    ).scalar()
    if not has_data:
        return

    name, storage, global_admin, global_write, global_read = _global_settings()
    conn.execute(
        sa.text(
            """
            INSERT INTO workspace (id, name, description, storage, active, created, deleted)
            VALUES (1, :name, NULL, :storage, true, now(), false)
            """
        ),
        {"name": name, "storage": storage},
    )
    conn.execute(
        sa.text("SELECT setval('workspace_id_seq', (SELECT max(id) FROM workspace))")
    )
    default_role = None
    if global_admin:
        default_role = "admin"
    elif global_write:
        default_role = "writer"
    elif global_read:
        default_role = "reader"
    conn.execute(
        sa.text(
            """
            INSERT INTO workspace_member (workspace_id, user_id, role, created)
            SELECT 1, id, CAST(:default_role AS workspace_role), now()
            FROM "user"
            WHERE active IS true AND (is_admin IS true OR :default_role IS NOT NULL)
            """
        ).bindparams(sa.bindparam("default_role", type_=sa.String)),
        {"default_role": default_role},
    )
    # superusers are owners of the migrated workspace
    conn.execute(
        sa.text(
            """
            INSERT INTO workspace_member (workspace_id, user_id, role, created)
            SELECT 1, id, 'owner', now() FROM "user" WHERE active IS true AND is_admin IS true
            ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = 'owner'
            """
        )
    )


def downgrade():
    op.drop_index(op.f("ix_workspace_member_user_id"), table_name="workspace_member")
    op.drop_table("workspace_member")
    op.drop_index("ix_workspace_name_lower", table_name="workspace")
    op.drop_index(op.f("ix_workspace_removed_at"), table_name="workspace")
    op.drop_index(op.f("ix_workspace_active"), table_name="workspace")
    op.drop_table("workspace")
    sa.Enum(name="workspace_role").drop(op.get_bind(), checkfirst=False)
