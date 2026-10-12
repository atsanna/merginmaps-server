# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from flask import current_app

from mergin.app import db
from mergin.auth.app import user_created
from mergin.sync.interfaces import WorkspaceRole


def add_created_user_to_workspace(user, **kwargs):
    """User created through POST /v2/users becomes member of requested workspace.
    Permission of the caller to add users was already checked by the endpoint.
    """
    workspace_id = kwargs.get("workspace_id")
    role = kwargs.get("workspace_role")
    if workspace_id is None or not role or role == WorkspaceRole.GUEST.value:
        return
    ws = current_app.ws_handler.get(workspace_id)
    if not ws:
        return
    ws.set_role(user.id, WorkspaceRole(role))
    db.session.commit()


def register_listeners():
    # connecting the same function again is a no-op for blinker
    user_created.connect(add_created_user_to_workspace)
