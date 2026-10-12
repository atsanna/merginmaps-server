# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime

from flask import abort, current_app
from flask_login import current_user

from mergin.auth import auth_required
from .models import AuditLog


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        abort(400, f"Invalid date: {value}")


def _query(
    workspace_id=None,
    event_type=None,
    project_id=None,
    actor_id=None,
    since=None,
    until=None,
):
    query = AuditLog.query
    if workspace_id is not None:
        query = query.filter(AuditLog.target_workspace_id == workspace_id)
    if event_type:
        query = query.filter(
            (AuditLog.event_type == event_type)
            | AuditLog.event_type.startswith(event_type + ".")
        )
    if project_id:
        query = query.filter(AuditLog.target_project_id == project_id)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if since:
        query = query.filter(AuditLog.happened_at >= _parse_date(since))
    if until:
        query = query.filter(AuditLog.happened_at < _parse_date(until))
    return query.order_by(AuditLog.happened_at.desc(), AuditLog.id.desc())


def _page(query, page, per_page):
    paginate = query.paginate(page=page, per_page=per_page, max_per_page=500)
    return {"items": [e.to_dict() for e in paginate.items], "count": paginate.total}


@auth_required(permissions=["admin"])
def server_audit_log(page=1, per_page=100, workspace_id=None, **filters):
    """All audit events of the server (superusers)"""
    return _page(_query(workspace_id=workspace_id, **filters), page, per_page), 200


@auth_required
def workspace_audit_log(id: int, page=1, per_page=100, **filters):
    """Audit events of workspace (workspace admins)"""
    ws = current_app.ws_handler.get(id)
    if not ws or not ws.is_active:
        abort(404, "Workspace not found")
    if not ws.user_has_permissions(current_user, "admin"):
        abort(403, "You do not have permissions for this workspace")
    return _page(_query(workspace_id=ws.id, **filters), page, per_page), 200
