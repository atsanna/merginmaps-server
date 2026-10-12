# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Server administration of workspaces (superusers only)"""

from flask import abort, current_app, request
from flask_login import current_user
from sqlalchemy import func

from mergin.app import db
from mergin.auth import auth_required
from ..events import PlusEventType, emit_event
from .controller import workspace_name_validation
from .members_controller import member_to_dict
from .models import Workspace

ORDER_COLUMNS = {
    "name": Workspace.name,
    "created": Workspace.created,
    "storage": Workspace.storage,
    "active": Workspace.active,
}


def admin_workspace_to_dict(ws: Workspace) -> dict:
    members = ws.members()
    return {
        "id": ws.id,
        "name": ws.name,
        "description": ws.description,
        "active": ws.active,
        "storage": ws.storage,
        "disk_usage": ws.disk_usage(),
        "project_count": ws.project_count(),
        "members_count": len(members),
        "contributors_count": len(ws.contributors()),
        "contributors_limit": ws.contributors_limit,
        "created": ws.created.isoformat() + "Z",
        "removed_at": ws.removed_at.isoformat() + "Z" if ws.removed_at else None,
        "expiration": ws.expiration.isoformat() + "Z" if ws.expiration else None,
    }


def _get(id: int) -> Workspace:
    ws = db.session.get(Workspace, id)
    if not ws or ws.deleted:
        abort(404, "Workspace not found")
    return ws


def _validate_limits(data: dict) -> None:
    if "storage" in data and (data["storage"] is None or data["storage"] < 0):
        abort(400, "Invalid storage")
    limit = data.get("contributors_limit")
    if limit is not None and limit < 0:
        abort(400, "Invalid contributors limit")


@auth_required(permissions=["admin"])
def list_workspaces(page=1, per_page=50, order_params=None, like=None):
    query = Workspace.query.filter(Workspace.deleted.is_(False))
    if like:
        query = query.filter(Workspace.name.ilike(f"%{like}%"))
    order = []
    for param in (order_params or "name ASC").split(","):
        parts = param.strip().split()
        column = ORDER_COLUMNS.get(parts[0]) if parts else None
        if column is None:
            continue
        desc = len(parts) > 1 and parts[1].upper() == "DESC"
        order.append(column.desc() if desc else column.asc())
    paginate = query.order_by(*order, Workspace.id).paginate(
        page=page, per_page=per_page, max_per_page=100
    )
    return {
        "items": [admin_workspace_to_dict(ws) for ws in paginate.items],
        "count": paginate.total,
    }, 200


@auth_required(permissions=["admin"])
def create_workspace():
    """Create workspace by name, owners are added later by inviting members"""
    data = request.json
    name = (data.get("name") or "").strip()
    error = workspace_name_validation(name)
    if error:
        abort(400, error)
    if current_app.ws_handler.get_by_name(name):
        abort(409, f"Workspace {name} already exists")
    _validate_limits(data)
    limit = data.get(
        "contributors_limit", current_app.config["WORKSPACE_CONTRIBUTORS_LIMIT"] or None
    )
    ws = Workspace(
        name=name,
        storage=data.get("storage", current_app.config["WORKSPACE_STORAGE_SIZE"]),
        description=data.get("description"),
        contributors_limit=limit,
    )
    db.session.add(ws)
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_CREATED, ws)
    return admin_workspace_to_dict(ws), 201


@auth_required(permissions=["admin"])
def get_workspace(id: int):
    ws = _get(id)
    data = admin_workspace_to_dict(ws)
    data["members"] = [member_to_dict(user, role) for user, role in ws.members()]
    return data, 200


@auth_required(permissions=["admin"])
def update_workspace(id: int):
    """Update limits, description and active flag (deactivated workspaces are not accessible to users)"""
    ws = _get(id)
    data = request.json
    _validate_limits(data)
    for key in ("storage", "contributors_limit", "description", "active"):
        if key in data:
            setattr(ws, key, data[key])
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_UPDATED, ws, changes=data)
    return admin_workspace_to_dict(ws), 200


@auth_required(permissions=["admin"])
def delete_workspace(id: int):
    """Schedule workspace removal (same as closing it by owner)"""
    ws = _get(id)
    if not ws.removed_at:
        ws.close(removed_by=current_user.id)
        db.session.commit()
        emit_event(PlusEventType.WORKSPACE_CLOSED, ws)
    return admin_workspace_to_dict(ws), 200


@auth_required(permissions=["admin"])
def restore_workspace(id: int):
    """Cancel scheduled removal of closed workspace"""
    ws = _get(id)
    if not ws.removed_at:
        abort(400, "Workspace is not closed")
    clash = Workspace.query.filter(
        func.lower(Workspace.name) == ws.name.lower(), Workspace.id != ws.id
    ).first()
    if clash:
        abort(409, f"Workspace name {ws.name} is used by another workspace")
    ws.removed_at = None
    ws.removed_by = None
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_RESTORED, ws)
    return admin_workspace_to_dict(ws), 200
