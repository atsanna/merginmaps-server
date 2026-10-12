# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Testing helpers shared by add-on tests and by the CE suite plugin (mergin_plus.ce_suite)"""

from flask import current_app
from sqlalchemy import text

from mergin.app import db
from mergin.tests import test_workspace_id, test_workspace_name


def create_global_workspace():
    """Workspace matching CE global one (id 1) used by CE test helpers"""
    from .workspace.models import Workspace

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


def initialize_with_workspace(initialize):
    """Wrap CE initialize(): global workspace must exist before the test project, superuser owns it"""

    def wrapper():
        from mergin.auth.models import User
        from mergin.sync.interfaces import WorkspaceRole

        if not current_app.ws_handler.get(test_workspace_id):
            create_global_workspace()
        initialize()
        ws = current_app.ws_handler.get(test_workspace_id)
        admin = User.query.filter_by(is_admin=True).first()
        ws.set_role(admin.id, WorkspaceRole.OWNER)
        db.session.commit()

    return wrapper


def create_app_with_plus(create_app):
    def wrapper(*args, **kwargs):
        from . import register

        application = create_app(*args, **kwargs)
        register(application)
        return application

    return wrapper


def db_global_workspace():
    return current_app.ws_handler.get(test_workspace_id)
