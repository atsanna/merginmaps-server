# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import re
from typing import Optional

from flask import abort, current_app, request
from flask_login import current_user

from mergin.app import db
from mergin.auth import auth_required
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.schemas import UserWorkspaceSchema
from mergin.sync.utils import (
    check_filename,
    has_valid_first_character,
    is_reserved_word,
)
from ..events import PlusEventType, emit_event
from .models import Workspace


def workspace_name_validation(name: Optional[str]) -> Optional[str]:
    """Return error message if name can not be used as workspace name"""
    name = name.strip() if name else name
    if not name:
        return "Workspace name cannot be empty"
    # workspace name is a part of URLs, so spaces are not allowed unlike for projects
    if re.match(r"^[\w\-\.]+$", name) is None:
        return "Please use only alphanumeric or the following -_. characters."
    for error in (
        has_valid_first_character(name),
        is_reserved_word(name.lower()),
        check_filename(name),
    ):
        if error:
            return error
    return None


def _get_workspace_or_404(id: int) -> Workspace:
    ws = current_app.ws_handler.get(id)
    if not ws or not ws.is_active:
        abort(404, "Workspace not found")
    return ws


def _dump(ws: Workspace) -> dict:
    return UserWorkspaceSchema(context={"user": current_user}).dump(ws)


@auth_required
def create_workspace():
    """Create new workspace owned by session user"""
    if not (current_app.config["USER_WORKSPACES_ALLOWED"] or current_user.is_admin):
        abort(403, "Creating workspaces is not allowed")

    name = (request.json.get("name") or "").strip()
    error = workspace_name_validation(name)
    if error:
        abort(400, error)
    if current_app.ws_handler.get_by_name(name):
        abort(409, f"Workspace {name} already exists")

    ws = Workspace(
        name=name,
        storage=current_app.config["WORKSPACE_STORAGE_SIZE"],
        description=request.json.get("description"),
        contributors_limit=current_app.config["WORKSPACE_CONTRIBUTORS_LIMIT"] or None,
    )
    db.session.add(ws)
    db.session.flush()
    ws.set_role(current_user.id, WorkspaceRole.OWNER)
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_CREATED, ws)
    return _dump(ws), 201


@auth_required
def update_workspace(id: int):
    """Update workspace description"""
    ws = _get_workspace_or_404(id)
    if not ws.user_has_permissions(current_user, "owner"):
        abort(403, "You do not have permissions for this workspace")
    if "name" in request.json and request.json["name"] != ws.name:
        abort(400, "Workspace name can not be changed")
    if "description" in request.json:
        ws.description = request.json["description"]
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_UPDATED, ws)
    return _dump(ws), 200


@auth_required
def close_workspace(id: int):
    """Close workspace, it will be removed permanently after expiration period"""
    ws = _get_workspace_or_404(id)
    if not ws.user_has_permissions(current_user, "owner"):
        abort(403, "You do not have permissions for this workspace")
    ws.close(removed_by=current_user.id)
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_CLOSED, ws)
    return "", 204


@auth_required
def workspace_usage(id: int):
    """Workspace usage and limits, available for workspace admins"""
    ws = _get_workspace_or_404(id)
    if not ws.user_has_permissions(current_user, "admin"):
        abort(403, "You do not have permissions for this workspace")
    members = ws.members()
    data = {
        "storage": ws.storage,
        "disk_usage": ws.disk_usage(),
        "project_count": ws.project_count(),
        "members_count": len(members),
        "contributors_count": len(ws.contributors()),
        "contributors_limit": ws.contributors_limit,
    }
    return data, 200
