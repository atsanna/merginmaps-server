# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from flask import abort, current_app, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import func

from mergin.app import db
from mergin.auth import auth_required
from mergin.auth.app import user_created
from mergin.auth.forms import UserRegistrationForm
from mergin.auth.schemas import UserInfoSchema
from mergin.auth.models import User
from mergin.celery import send_email_async
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import Project, ProjectRole
from ..events import PlusEventType, emit_event
from .limits import (
    check_can_add_contributor,
    invitation_adds_contributor,
    pending_contributor_invitations,
)
from .models import Workspace, WorkspaceInvitation, WorkspaceMember

# roles which can be granted through membership, guests are users with direct project access only
MEMBER_ROLES = [r for r in WorkspaceRole if r is not WorkspaceRole.GUEST]


def _get_workspace(id: int) -> Workspace:
    ws = current_app.ws_handler.get(id)
    if not ws or not ws.is_active:
        abort(404, "Workspace not found")
    return ws


def _require_admin(ws: Workspace) -> None:
    if not ws.user_has_permissions(current_user, "admin"):
        abort(403, "You do not have permissions for this workspace")


def _parse_role(value) -> WorkspaceRole:
    try:
        role = WorkspaceRole(value)
    except ValueError:
        abort(400, f"Invalid role: {value}")
    if role not in MEMBER_ROLES:
        abort(400, f"Invalid role: {value}")
    return role


def _check_can_grant(ws: Workspace, role: WorkspaceRole) -> None:
    """Only owners can grant (or take away) owner role"""
    if role is WorkspaceRole.OWNER and not ws.user_has_permissions(
        current_user, "owner"
    ):
        abort(403, "Only workspace owners can manage owners")


def _is_last_owner(ws: Workspace, user_id: int) -> bool:
    owners = [u.id for u in ws.owners()]
    return owners == [user_id]


def member_to_dict(user: User, role: WorkspaceRole) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.name(),
        "workspace_role": role.value,
        "contributor": role >= WorkspaceRole.EDITOR,
        "last_signed_in": (
            user.last_signed_in.isoformat() + "Z" if user.last_signed_in else None
        ),
    }


def invitation_to_dict(inv: WorkspaceInvitation) -> dict:
    return {
        "uuid": str(inv.uuid),
        "email": inv.email,
        "role": inv.role,
        "workspace_id": inv.workspace_id,
        "workspace": inv.workspace.name,
        "inviter": inv.inviter.username if inv.inviter else None,
        "created": inv.created.isoformat() + "Z",
        "expires_at": inv.expires_at.isoformat() + "Z",
        "expired": inv.is_expired,
        "projects": inv.projects,
    }


def send_invitation_email(inv: WorkspaceInvitation) -> None:
    base_url = current_app.config["MERGIN_BASE_URL"].rstrip("/")
    email_data = {
        "subject": f"Invitation to workspace {inv.workspace.name}",
        "html": render_template(
            "email/workspace_invitation.html",
            workspace=inv.workspace.name,
            inviter=current_user.username,
            role=inv.role,
            expire=inv.expires_at,
            # the page lets existing users accept and new users create their account
            link=f"{base_url}/invitations/{inv.uuid}",
        ),
        "recipients": [inv.email],
        "sender": current_app.config["MAIL_DEFAULT_SENDER"],
    }
    send_email_async.delay(**email_data)


# members


@auth_required
def list_members(id: int):
    ws = _get_workspace(id)
    _require_admin(ws)
    return [member_to_dict(user, role) for user, role in ws.members()], 200


@auth_required
def get_member(id: int, user_id: int):
    ws = _get_workspace(id)
    if current_user.id != user_id:
        _require_admin(ws)
    member = ws.get_member(user_id)
    if not member or not member.user.active:
        abort(404, "Member not found")
    return member_to_dict(member.user, WorkspaceRole(member.role)), 200


@auth_required
def update_member(id: int, user_id: int):
    ws = _get_workspace(id)
    _require_admin(ws)
    member = ws.get_member(user_id)
    if not member or not member.user.active:
        abort(404, "Member not found")
    # python client sends 'workspace_role', public docs mention 'role'
    value = request.json.get("workspace_role", request.json.get("role"))
    if value is None:
        abort(400, "Missing workspace role")
    role = _parse_role(value)
    current_role = WorkspaceRole(member.role)
    _check_can_grant(ws, role)
    _check_can_grant(ws, current_role)
    if (
        current_role is WorkspaceRole.OWNER
        and role is not WorkspaceRole.OWNER
        and _is_last_owner(ws, user_id)
    ):
        abort(400, "Workspace must have at least one owner")
    ws.set_role(user_id, role)
    if request.json.get("reset_projects_roles"):
        ws.reset_projects_roles(user_id)
    db.session.commit()
    emit_event(
        PlusEventType.WORKSPACE_MEMBER_UPDATED,
        ws,
        target_user_id=user_id,
        old_role=current_role.value,
        new_role=role.value,
    )
    return member_to_dict(member.user, role), 200


@auth_required
def remove_member(id: int, user_id: int):
    """Remove member from workspace, members can remove themselves (leave)"""
    ws = _get_workspace(id)
    if current_user.id != user_id:
        _require_admin(ws)
    member = ws.get_member(user_id)
    if not member:
        abort(404, "Member not found")
    if current_user.id != user_id:
        _check_can_grant(ws, WorkspaceRole(member.role))
    if member.role == WorkspaceRole.OWNER.value and _is_last_owner(ws, user_id):
        abort(400, "Workspace must have at least one owner")
    ws.remove_member(user_id)
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_MEMBER_REMOVED, ws, target_user_id=user_id)
    return "", 204


# invitations managed by workspace admins


def _parse_invitation_projects(ws: Workspace, items) -> list:
    """Validate list of {"id", "role"} of workspace projects for invitation"""
    result = []
    for item in items or []:
        try:
            role = ProjectRole(item.get("role", ProjectRole.READER.value))
        except ValueError:
            abort(400, f"Invalid project role: {item.get('role')}")
        project = Project.query.filter_by(
            id=item.get("id"), workspace_id=ws.id, removed_at=None
        ).first()
        if not project:
            abort(400, f"Project {item.get('id')} not found in workspace")
        result.append({"id": str(project.id), "role": role.value})
    return result


def _invite(ws: Workspace, email: str, role: WorkspaceRole, projects: list):
    """Create invitation, or extend a pending one with projects, and send e-mail.
    Returns (invitation, created)
    """
    inv = WorkspaceInvitation.query.filter_by(workspace_id=ws.id, email=email).first()
    if invitation_adds_contributor(role.value, projects):
        check_can_add_contributor(ws, pending_contributor_invitations(ws))
    if inv and inv.is_expired:
        db.session.delete(inv)
        db.session.flush()
        inv = None
    created = inv is None
    if created:
        inv = WorkspaceInvitation(ws, email, role, current_user, projects)
        db.session.add(inv)
    else:
        if role is not WorkspaceRole.GUEST and role >= WorkspaceRole(inv.role):
            inv.role = role.value
        for item in projects:
            inv.add_project(item["id"], item["role"])
        inv.renew()
    db.session.commit()
    emit_event(
        PlusEventType.WORKSPACE_INVITATION_CREATED,
        ws,
        target_email=email,
        role=inv.role,
        projects=inv.projects,
    )
    send_invitation_email(inv)
    return inv, created


@auth_required
def create_invitation(id: int):
    """Invite e-mail to workspace as member, or as guest with access to listed projects"""
    ws = _get_workspace(id)
    _require_admin(ws)
    email = (request.json.get("email") or "").strip().lower()
    if "@" not in email:
        abort(400, "Invalid email")
    value = request.json.get("role")
    projects = _parse_invitation_projects(ws, request.json.get("projects"))
    if value == WorkspaceRole.GUEST.value:
        if not projects:
            abort(400, "Guest invitation requires projects")
        role = WorkspaceRole.GUEST
    else:
        role = _parse_role(value)
    _check_can_grant(ws, role)

    user = User.query.filter(func.lower(User.email) == email).first()
    if user and ws.get_member(user.id):
        abort(409, "User is already a workspace member")
    existing = WorkspaceInvitation.query.filter_by(
        workspace_id=ws.id, email=email
    ).first()
    if existing and not existing.is_expired:
        abort(409, "Invitation already exists")
    inv, _ = _invite(ws, email, role, projects)
    return invitation_to_dict(inv), 201


@auth_required
def share_project(id: str):
    """Share project with e-mail: existing users get direct access,
    others are invited to the workspace as guests of the project (or the pending invitation is extended)
    """
    from mergin.sync.permissions import ProjectPermissions, require_project_by_uuid

    project = require_project_by_uuid(id, ProjectPermissions.Update)
    ws = current_app.ws_handler.get(project.workspace_id)
    email = (request.json.get("email") or "").strip().lower()
    if "@" not in email:
        abort(400, "Invalid email")
    try:
        role = ProjectRole(request.json.get("role", ProjectRole.READER.value))
    except ValueError:
        abort(400, f"Invalid project role: {request.json.get('role')}")

    user = User.query.filter(func.lower(User.email) == email, User.active).first()
    if user:
        project.set_role(user.id, role)
        db.session.commit()
        return {"email": email, "user_id": user.id, "role": role.value}, 200

    inv, created = _invite(
        ws, email, WorkspaceRole.GUEST, [{"id": str(project.id), "role": role.value}]
    )
    return invitation_to_dict(inv), 201 if created else 200


@auth_required
def list_invitations(id: int):
    ws = _get_workspace(id)
    _require_admin(ws)
    invitations = (
        WorkspaceInvitation.query.filter_by(workspace_id=ws.id)
        .order_by(WorkspaceInvitation.created.desc())
        .all()
    )
    return [invitation_to_dict(i) for i in invitations], 200


def _get_ws_invitation(ws: Workspace, uuid: str) -> WorkspaceInvitation:
    inv = WorkspaceInvitation.query.filter_by(workspace_id=ws.id, uuid=uuid).first()
    if not inv:
        abort(404, "Invitation not found")
    return inv


@auth_required
def delete_invitation(id: int, uuid: str):
    ws = _get_workspace(id)
    _require_admin(ws)
    inv = _get_ws_invitation(ws, uuid)
    _check_can_grant(ws, WorkspaceRole(inv.role))
    db.session.delete(inv)
    db.session.commit()
    emit_event(PlusEventType.WORKSPACE_INVITATION_DELETED, ws, target_email=inv.email)
    return "", 204


@auth_required
def resend_invitation(id: int, uuid: str):
    ws = _get_workspace(id)
    _require_admin(ws)
    inv = _get_ws_invitation(ws, uuid)
    _check_can_grant(ws, WorkspaceRole(inv.role))
    inv.renew()
    db.session.commit()
    send_invitation_email(inv)
    return invitation_to_dict(inv), 200


# invitations of session user


def _get_user_invitation(uuid: str) -> WorkspaceInvitation:
    invitations = current_app.ws_handler.list_user_invitations(current_user)
    inv = next((i for i in invitations if str(i.uuid) == uuid), None)
    if not inv:
        abort(404, "Invitation not found")
    return inv


@auth_required
def user_invitations():
    invitations = current_app.ws_handler.list_user_invitations(current_user)
    return [invitation_to_dict(i) for i in invitations], 200


@auth_required
def accept_invitation(uuid: str):
    inv = _get_user_invitation(uuid)
    ws = inv.workspace
    inv_role = inv.role
    inv.accept(current_user)
    db.session.commit()
    emit_event(
        PlusEventType.WORKSPACE_INVITATION_ACCEPTED,
        ws,
        target_user_id=current_user.id,
        role=inv_role,
    )
    member = ws.get_member(current_user.id)
    role = WorkspaceRole(member.role) if member else WorkspaceRole.GUEST
    return member_to_dict(current_user, role), 200


@auth_required
def decline_invitation(uuid: str):
    inv = _get_user_invitation(uuid)
    db.session.delete(inv)
    db.session.commit()
    emit_event(
        PlusEventType.WORKSPACE_INVITATION_DECLINED,
        inv.workspace,
        target_user_id=current_user.id,
    )
    return "", 204


def register_from_invitation(uuid: str):
    """Create account for invited email address and accept the invitation.
    Allowed even when USER_SELF_REGISTRATION is disabled, the secret invitation link
    sent to the email address proves its ownership.
    """
    inv = WorkspaceInvitation.query.filter_by(uuid=uuid).first()
    if not inv or inv.is_expired or not inv.workspace.is_active:
        abort(404, "Invitation not found")
    if User.query.filter(func.lower(User.email) == inv.email).first():
        abort(409, "Account with this email already exists, please log in")

    form = UserRegistrationForm(meta={"csrf": False})
    form.email.data = inv.email
    form.username.data = request.json.get("username") or User.generate_username(
        inv.email
    )
    form.confirm.data = form.password.data
    if not form.validate():
        return jsonify(form.errors), 400

    db.session.info["audit_user_creation_source"] = "invitation"
    user = User.create(form.username.data, inv.email, form.password.data)
    user.active = True
    user.verified_email = True
    user_created.send(user, source="invitation")
    inv.accept(user)
    db.session.commit()
    return jsonify(UserInfoSchema().dump(user)), 201
