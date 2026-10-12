# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import importlib

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from mergin.app import create_simple_app, db
from mergin.test_migrations.utils import assert_schema_consistent, make_migration_engine
from mergin_plus.app import MIGRATIONS_DIR, configure_migrations

migration_engine = make_migration_engine("mergin_plus_migration_test")


@pytest.fixture(scope="module")
def migration_app(migration_engine):
    for module_path in (
        "mergin.auth.models",
        "mergin.stats.models",
        "mergin.sync.models",
        "mergin_plus.workspace.models",
        "mergin_plus.transfer.models",
        "mergin_plus.audit.models",
        "mergin_plus.webhooks.models",
    ):
        importlib.import_module(module_path)

    app = create_simple_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = migration_engine.url.render_as_string(
        hide_password=False
    )
    app.config.update(
        GLOBAL_WORKSPACE="my-org",
        GLOBAL_STORAGE=12345,
        GLOBAL_ADMIN=False,
        GLOBAL_WRITE=True,
        GLOBAL_READ=False,
    )
    configure_migrations(app)
    ctx = app.app_context()
    ctx.push()
    try:
        yield app
    finally:
        ctx.pop()


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def test_enterprise_migration(migration_app, migration_engine):
    """Upgrade existing CE database: global workspace and its members are migrated"""
    upgrade(directory=MIGRATIONS_DIR, revision="community@head")
    with migration_engine.begin() as conn:
        for username, is_admin, active in (
            ("admin", True, True),
            ("user", False, True),
            ("inactive", False, False),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO "user" (username, email, passwd, is_admin, active, verified_email,
                        registration_date, receive_notifications, auth_version)
                    VALUES (:u, :e, 'x', :a, :act, true, now(), true, 1)
                    """
                ),
                {
                    "u": username,
                    "e": f"{username}@example.com",
                    "a": is_admin,
                    "act": active,
                },
            )

    upgrade(directory=MIGRATIONS_DIR, revision="enterprise@head")
    assert _rows(migration_engine, "SELECT id, name, storage FROM workspace") == [
        (1, "my-org", 12345)
    ]
    members = _rows(
        migration_engine,
        """
        SELECT u.username, m.role FROM workspace_member m JOIN "user" u ON u.id = m.user_id
        ORDER BY u.username
        """,
    )
    assert members == [("admin", "owner"), ("user", "writer")]
    # new workspaces continue after migrated one
    assert _rows(migration_engine, "SELECT nextval('workspace_id_seq')") == [(2,)]

    assert_schema_consistent(migration_engine, db.metadata)

    downgrade(directory=MIGRATIONS_DIR, revision="enterprise@base")
    tables = {
        r[0]
        for r in _rows(
            migration_engine,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
        )
    }
    assert "workspace" not in tables and "workspace_member" not in tables
    assert not _rows(
        migration_engine, "SELECT 1 FROM pg_type WHERE typname = 'workspace_role'"
    )
