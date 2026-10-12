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
    }


def send_invitation_email(inv: WorkspaceInvitation) -> None:
    base_url = current_app.config["MERGIN_BASE_URL"].rstrip("/")
    user = User.query.filter(func.lower(User.email) == inv.email).first()
    email_data = {
        "subject": f"Invitation to workspace {inv.workspace.name}",
        "html": render_template(
            "email/workspace_invitation.html",
            workspace=inv.workspace.name,
            inviter=current_user.username,
            role=inv.role,
            expire=inv.expires_at,
            # existing users accept in dashboard, new users register first
            link=f"{base_url}/invitations" if user else f"{base_url}/register",
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
    return "", 204


# invitations managed by workspace admins


@auth_required
def create_invitation(id: int):
    ws = _get_workspace(id)
    _require_admin(ws)
    email = (request.json.get("email") or "").strip().lower()
    if "@" not in email:
        abort(400, "Invalid email")
    role = _parse_role(request.json.get("role"))
    _check_can_grant(ws, role)

    user = User.query.filter(func.lower(User.email) == email).first()
    if user and ws.get_member(user.id):
        abort(409, "User is already a workspace member")
    inv = WorkspaceInvitation.query.filter_by(workspace_id=ws.id, email=email).first()
    if inv and not inv.is_expired:
        abort(409, "Invitation already exists")
    if inv:
        # replace expired invitation
        db.session.delete(inv)
        db.session.flush()
    inv = WorkspaceInvitation(ws, email, role, current_user)
    db.session.add(inv)
    db.session.commit()
    send_invitation_email(inv)
    return invitation_to_dict(inv), 201


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
    member = ws.get_member(current_user.id)
    # keep higher role if user is already a member
    if not member or WorkspaceRole(inv.role) >= WorkspaceRole(member.role):
        inv.accept(current_user)
    else:
        db.session.delete(inv)
    db.session.commit()
    member = ws.get_member(current_user.id)
    return member_to_dict(current_user, WorkspaceRole(member.role)), 200


@auth_required
def decline_invitation(uuid: str):
    inv = _get_user_invitation(uuid)
    db.session.delete(inv)
    db.session.commit()
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
