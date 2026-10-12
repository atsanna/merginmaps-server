# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Transfer of projects between workspaces.

A project owner (or an admin of its workspace) requests the transfer to a target workspace by name,
an admin or owner of the target workspace accepts or declines it. The request expires after
PROJECT_TRANSFER_EXPIRATION days. Project data are not copied, only the workspace of the project changes;
direct project collaborators keep their access.
"""

from datetime import datetime

from flask import abort, current_app, render_template, request
from flask_login import current_user

from mergin.app import db
from mergin.auth import auth_required
from mergin.celery import send_email_async
from mergin.sync.errors import StorageLimitHit
from mergin.sync.forms import project_name_validation
from mergin.sync.models import Project
from mergin.sync.permissions import ProjectPermissions, require_project_by_uuid
from mergin.sync.interfaces import WorkspaceRole
from .models import ProjectTransfer


def _active_workspace(id_or_name):
    handler = current_app.ws_handler
    ws = handler.get(id_or_name) if isinstance(id_or_name, int) else None
    ws = ws or handler.get_by_name(str(id_or_name))
    if not ws or not ws.is_active:
        abort(404, "Workspace not found")
    return ws


def _notify_target_admins(transfer: ProjectTransfer) -> None:
    base_url = current_app.config["MERGIN_BASE_URL"].rstrip("/")
    for user, role in transfer.to_workspace.members():
        if not role >= WorkspaceRole.ADMIN or not user.receive_notifications:
            continue
        send_email_async.delay(
            subject=f"Project transfer to workspace {transfer.to_workspace.name}",
            html=render_template(
                "email/project_transfer.html",
                username=user.username,
                requester=current_user.username,
                project=f"{transfer.from_workspace.name}/{transfer.project.name}",
                workspace=transfer.to_workspace.name,
                expire=transfer.expires_at,
                link=f"{base_url}/workspaces/{transfer.to_workspace_id}/transfers",
            ),
            recipients=[user.email],
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
        )


def _pending(transfer_id) -> ProjectTransfer:
    transfer = db.session.get(ProjectTransfer, transfer_id)
    if not transfer or transfer.is_expired or transfer.project.removed_at:
        abort(404, "Transfer not found")
    return transfer


@auth_required
def request_transfer(id: str):
    project = require_project_by_uuid(id, ProjectPermissions.Delete)
    target = _active_workspace(request.json.get("workspace"))
    if target.id == project.workspace_id:
        abort(400, "Project is already in this workspace")
    existing = ProjectTransfer.query.filter_by(project_id=project.id).first()
    if existing and not existing.is_expired:
        abort(409, "Project transfer is already requested")
    if existing:
        db.session.delete(existing)
        db.session.flush()
    transfer = ProjectTransfer(project, target, current_user)
    db.session.add(transfer)
    db.session.commit()
    _notify_target_admins(transfer)
    return transfer.to_dict(), 201


@auth_required
def project_transfer(id: str):
    project = require_project_by_uuid(id, ProjectPermissions.Read)
    transfer = ProjectTransfer.query.filter_by(project_id=project.id).first()
    if not transfer or transfer.is_expired:
        abort(404, "Transfer not found")
    return transfer.to_dict(), 200


@auth_required
def workspace_transfers(id: int):
    """Pending incoming and outgoing transfers of workspace, for its admins"""
    ws = _active_workspace(id)
    if not ws.user_has_permissions(current_user, "admin"):
        abort(403, "You do not have permissions for this workspace")
    transfers = (
        ProjectTransfer.query.filter(
            (ProjectTransfer.to_workspace_id == ws.id)
            | (ProjectTransfer.from_workspace_id == ws.id),
            ProjectTransfer.expires_at > datetime.utcnow(),
        )
        .order_by(ProjectTransfer.created.desc())
        .all()
    )
    return {
        "incoming": [t.to_dict() for t in transfers if t.to_workspace_id == ws.id],
        "outgoing": [t.to_dict() for t in transfers if t.from_workspace_id == ws.id],
    }, 200


@auth_required
def accept_transfer(id: str):
    """Move project to target workspace, optionally under a new name"""
    transfer = _pending(id)
    target = transfer.to_workspace
    if not (target.is_active and target.user_has_permissions(current_user, "admin")):
        abort(403, "You do not have permissions for the target workspace")
    project = transfer.project
    name = (request.json or {}).get("name") or project.name
    error = project_name_validation(name)
    if error:
        abort(400, error)
    if Project.query.filter_by(workspace_id=target.id, name=name).first():
        abort(409, f"Project {name} already exists in workspace {target.name}")
    usage = target.disk_usage()
    if usage + project.disk_usage > target.storage:
        return StorageLimitHit(usage, target.storage).response(422)

    project.workspace_id = target.id
    project.name = name
    db.session.delete(transfer)
    db.session.commit()
    return {"id": str(project.id), "name": name, "namespace": target.name}, 200


@auth_required
def decline_transfer(id: str):
    """Target workspace admins decline, source side (project owner, workspace admins) cancels"""
    transfer = _pending(id)
    can_decline = transfer.to_workspace.user_has_permissions(current_user, "admin")
    can_cancel = ProjectPermissions.Delete.check(transfer.project, current_user)
    if not (can_decline or can_cancel):
        abort(403, "You do not have permissions for this transfer")
    db.session.delete(transfer)
    db.session.commit()
    return "", 204
