# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Audit event types emitted by the add-on (CE types are reused where they exist)"""

from enum import Enum

from mergin.audit import emit
from mergin.audit.listeners import actor_context


class PlusEventType(str, Enum):
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_CLOSED = "workspace.closed"
    WORKSPACE_RESTORED = "workspace.restored"
    WORKSPACE_MEMBER_ADDED = "workspace.member.added"
    WORKSPACE_MEMBER_UPDATED = "workspace.member.updated"
    WORKSPACE_MEMBER_REMOVED = "workspace.member.removed"
    WORKSPACE_INVITATION_CREATED = "workspace.invitation.created"
    WORKSPACE_INVITATION_ACCEPTED = "workspace.invitation.accepted"
    WORKSPACE_INVITATION_DECLINED = "workspace.invitation.declined"
    WORKSPACE_INVITATION_DELETED = "workspace.invitation.deleted"


def emit_event(event_type, workspace=None, **kwargs) -> None:
    """Emit audit event on behalf of the current request user"""
    value = event_type.value if isinstance(event_type, Enum) else event_type
    if workspace is not None:
        kwargs.setdefault("target_workspace_id", workspace.id)
        kwargs.setdefault("workspace_name", workspace.name)
    emit(value, **actor_context(), **kwargs)
