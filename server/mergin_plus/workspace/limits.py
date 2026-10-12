# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Workspace contributors limit enforced for every way roles are granted.

Roles can be granted by CE code paths too (project collaborators API, access requests, bulk access update),
so the limit is checked on database flush instead of in single endpoints:
before flush the contributors of affected workspaces are recorded, after flush they are compared.
Changes which do not add a contributor are always allowed, even if the workspace is already over limit.
"""

from sqlalchemy import event
from werkzeug.exceptions import UnprocessableEntity

from mergin.app import db
from mergin.sync.models import Project, ProjectRole, ProjectUser
from .models import CONTRIBUTOR_ROLES, Workspace, WorkspaceMember

STATE_KEY = "plus_contributors_before"


class ContributorsLimitHit(UnprocessableEntity):
    def __init__(self, workspace: Workspace):
        super().__init__(
            f"Workspace {workspace.name} reached its limit of "
            f"{workspace.contributors_limit} contributors"
        )
        self.workspace = workspace


def _affected_workspaces(session) -> set:
    ids = set()
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, WorkspaceMember) and obj.role in CONTRIBUTOR_ROLES:
            ids.add(obj.workspace_id)
        elif (
            isinstance(obj, ProjectUser)
            and obj.role
            and obj.role != ProjectRole.READER.value
        ):
            project = obj.project or db.session.get(Project, obj.project_id)
            if project:
                ids.add(project.workspace_id)
    return ids


def before_flush(session, flush_context, instances):
    with session.no_autoflush:
        ids = _affected_workspaces(session)
        if not ids:
            return
        workspaces = Workspace.query.filter(
            Workspace.id.in_(ids), Workspace.contributors_limit.isnot(None)
        ).all()
        state = session.info.setdefault(STATE_KEY, {})
        for ws in workspaces:
            state.setdefault(ws.id, ws.contributors())


def after_flush(session, flush_context):
    state = session.info.pop(STATE_KEY, None)
    if not state:
        return
    for ws_id, before in state.items():
        ws = session.get(Workspace, ws_id)
        after = ws.contributors()
        if after - before and len(after) > ws.contributors_limit:
            raise ContributorsLimitHit(ws)


def check_can_add_contributor(ws: Workspace, pending: int = 0) -> None:
    """Explicit check for actions which will add a contributor later (e.g. invitations)"""
    if ws.contributors_limit is None:
        return
    if len(ws.contributors()) + pending >= ws.contributors_limit:
        raise ContributorsLimitHit(ws)


def handle_limit_hit(e: ContributorsLimitHit):
    """Flush failed, session must be rolled back before it can be used again"""
    db.session.rollback()
    return {"code": "ContributorsLimitHit", "detail": e.description}, 422


def pending_contributor_invitations(ws: Workspace) -> int:
    from datetime import datetime
    from .models import WorkspaceInvitation

    invitations = WorkspaceInvitation.query.filter(
        WorkspaceInvitation.workspace_id == ws.id,
        WorkspaceInvitation.expires_at > datetime.utcnow(),
    ).all()
    return len(
        [i for i in invitations if invitation_adds_contributor(i.role, i.projects)]
    )


def invitation_adds_contributor(role: str, projects: list) -> bool:
    return role in CONTRIBUTOR_ROLES or any(
        p.get("role", ProjectRole.READER.value) != ProjectRole.READER.value
        for p in projects or []
    )


def register_events():
    if not event.contains(db.session, "before_flush", before_flush):
        event.listen(db.session, "before_flush", before_flush)
        event.listen(db.session, "after_flush", after_flush)
