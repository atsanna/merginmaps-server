# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import os
import uuid

import pytest
from flask import current_app
from sqlalchemy import text

from mergin.app import create_app, db
from mergin.auth.models import User
from mergin.stats.app import register as register_stats
from mergin.stats.models import MerginInfo
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import Project
from mergin.tests import test_workspace_id, test_workspace_name
from mergin.tests.utils import (
    cleanup,
    create_db,
    initialize,
    login_as_admin,
)
from mergin_plus import register as register_plus
from mergin_plus.workspace.models import Workspace

# reuse CE function scoped fixtures, they depend on the session app defined below
from mergin.tests.fixtures import flask_app  # noqa: F401

TESTS_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir, "mergin", "tests"
)


@pytest.fixture(scope="session")
def session_app():
    """Flask app with enterprise features registered, db tables are created only once"""
    from mergin.sync.db_events import remove_events

    application = create_app(
        [
            "SERVER_TYPE",
            "DOCS_URL",
            "COLLECT_STATISTICS",
            "USER_SELF_REGISTRATION",
            "USER_WORKSPACES_ALLOWED",
        ]
    )
    register_stats(application)
    register_plus(application)
    application.config["TEST_DIR"] = os.path.join(TESTS_DIR, "test_projects")
    application.config["SERVER_NAME"] = "localhost.localdomain"
    application.config["SERVICE_ID"] = str(uuid.uuid4())

    with application.app_context():
        create_db()
        db.drop_all()
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    remove_events()


def create_global_workspace() -> Workspace:
    """Workspace matching CE global one (id 1) used by CE test helpers"""
    ws = Workspace(
        name=test_workspace_name, storage=current_app.config["GLOBAL_STORAGE"]
    )
    ws.id = test_workspace_id
    db.session.add(ws)
    db.session.flush()
    db.session.execute(
        text("SELECT setval('workspace_id_seq', (SELECT max(id) FROM workspace))")
    )
    db.session.commit()
    return ws


@pytest.fixture(scope="function")
def app(flask_app, request):  # noqa: F811
    """Flask app with CE testing objects and the global workspace stored in db"""
    with flask_app.app_context():
        ws = create_global_workspace()
        initialize()
        admin = User.query.filter_by(is_admin=True).first()
        ws.set_role(admin.id, WorkspaceRole.OWNER)
        db.session.add(MerginInfo(service_id=current_app.config["SERVICE_ID"]))
        db.session.commit()

    def teardown():
        with flask_app.app_context():
            dirs = [
                p.storage.project_dir
                for p in Project.query.all()
                if p.storage is not None
            ]
            cleanup(flask_app.test_client(), dirs)

    request.addfinalizer(teardown)
    return flask_app


@pytest.fixture(scope="function")
def client(app):
    """Test client with logged-in superuser"""
    client = app.test_client()
    login_as_admin(client)
    return client
