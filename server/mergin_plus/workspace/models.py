# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from flask import current_app
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import ENUM, UUID

from mergin.app import db
from mergin.auth.models import User
from mergin.sync.interfaces import AbstractWorkspace, WorkspaceRole
from mergin.sync.models import Project, ProjectUser


class Workspace(db.Model, AbstractWorkspace):
    """Workspace stored in database, owner of projects and members"""

    __tablename__ = "workspace"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # name is part of project full names (<workspace>/<project>), it can not be changed
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    storage = db.Column(db.BigInteger, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # closed workspace waiting for permanent removal
    removed_at = db.Column(db.DateTime, nullable=True, index=True)
    removed_by = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # closed workspace whose data were permanently removed, row is kept for project references
    deleted = db.Column(db.Boolean, nullable=False, default=False)

    memberships = db.relationship(
        "WorkspaceMember", cascade="all, delete-orphan", back_populates="workspace"
    )

    __table_args__ = (
        db.Index("ix_workspace_name_lower", func.lower(name), unique=True),
    )

    def __init__(self, name: str, storage: int, description: str = None):
        self.name = name
        self.storage = storage
        self.description = description
        self.active = True
        self.deleted = False

    @property
    def is_active(self) -> bool:
        return self.active and self.removed_at is None

    @property
    def expiration(self) -> Optional[datetime]:
        """Time when closed workspace is going to be permanently removed"""
        if not self.removed_at:
            return None
        return self.removed_at + timedelta(
            days=current_app.config["WORKSPACE_EXPIRATION"]
        )

    def close(self, removed_by: int = None) -> None:
        """Close workspace (soft-delete), it can not be used anymore, does not commit"""
        self.removed_at = datetime.utcnow()
        self.removed_by = removed_by

    def purge(self) -> None:
        """Permanently remove closed workspace projects and memberships.
        Workspace row is kept with a free name as (removed) projects still reference it.
        """
        projects = Project.query.filter(
            Project.workspace_id == self.id, Project.storage_params.isnot(None)
        ).all()
        for p in projects:
            p.delete(removed_by=self.removed_by)
        WorkspaceMember.query.filter_by(workspace_id=self.id).delete()
        WorkspaceInvitation.query.filter_by(workspace_id=self.id).delete()
        self.name = f"{self.name}_{self.id}"
        self.active = False
        self.deleted = True
        db.session.commit()

    def disk_usage(self) -> int:
        usage = (
            db.session.query(func.coalesce(func.sum(Project.disk_usage), 0))
            .filter(
                Project.workspace_id == self.id,
                Project.removed_at.is_(None),
                Project.locked_until.is_(None),
            )
            .scalar()
        )
        return int(usage)

    def project_count(self) -> int:
        return Project.query.filter(
            Project.workspace_id == self.id,
            Project.removed_at.is_(None),
            Project.locked_until.is_(None),
        ).count()

    def get_member(self, user_id: int) -> Optional["WorkspaceMember"]:
        return WorkspaceMember.query.filter_by(
            workspace_id=self.id, user_id=user_id
        ).first()

    def is_guest(self, user) -> bool:
        """User without membership who has a direct access to some workspace project"""
        return (
            db.session.query(ProjectUser.project_id)
            .join(Project, Project.id == ProjectUser.project_id)
            .filter(
                ProjectUser.user_id == user.id,
                Project.workspace_id == self.id,
                Project.removed_at.is_(None),
            )
            .first()
            is not None
        )

    def get_user_role(self, user) -> Optional[WorkspaceRole]:
        if not user or not user.is_authenticated:
            return None
        # server superuser can manage any workspace
        if user.is_admin:
            return WorkspaceRole.OWNER
        member = self.get_member(user.id)
        if member:
            return WorkspaceRole(member.role)
        if self.is_guest(user):
            return WorkspaceRole.GUEST
        return None

    def user_has_permissions(self, user, permissions) -> bool:
        role = self.get_user_role(user)
        if role is None:
            return False
        if role is WorkspaceRole.OWNER:
            return True
        if permissions == "guest":
            return role == WorkspaceRole.GUEST
        required = {
            "read": WorkspaceRole.READER,
            "edit": WorkspaceRole.EDITOR,
            "write": WorkspaceRole.WRITER,
            "admin": WorkspaceRole.ADMIN,
            "owner": WorkspaceRole.OWNER,
        }.get(permissions)
        return required is not None and role >= required

    def user_is_member(self, user) -> bool:
        return self.get_member(user.id) is not None

    def members(self) -> List[Tuple[User, WorkspaceRole]]:
        rows = (
            db.session.query(User, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .filter(WorkspaceMember.workspace_id == self.id, User.active.is_(True))
            .order_by(User.email)
            .all()
        )
        return [(user, WorkspaceRole(role)) for user, role in rows]

    def owners(self) -> List[User]:
        return [user for user, role in self.members() if role is WorkspaceRole.OWNER]

    def can_add_users(self, user) -> bool:
        return self.user_has_permissions(user, "admin")

    def set_role(self, user_id: int, role: WorkspaceRole) -> "WorkspaceMember":
        """Create or update membership, does not commit"""
        member = self.get_member(user_id)
        if member:
            member.role = role.value
        else:
            member = WorkspaceMember(
                workspace_id=self.id, user_id=user_id, role=role.value
            )
            db.session.add(member)
        return member

    def remove_member(self, user_id: int) -> None:
        """Remove membership and direct access to workspace projects, does not commit"""
        WorkspaceMember.query.filter_by(workspace_id=self.id, user_id=user_id).delete()
        self.reset_projects_roles(user_id)

    def reset_projects_roles(self, user_id: int) -> None:
        """Remove user direct access to workspace projects, does not commit"""
        projects = db.session.query(Project.id).filter(Project.workspace_id == self.id)
        ProjectUser.query.filter(
            ProjectUser.user_id == user_id, ProjectUser.project_id.in_(projects)
        ).delete(synchronize_session=False)


class WorkspaceMember(db.Model):
    """User membership in workspace with a role"""

    __tablename__ = "workspace_member"

    workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role = db.Column(
        ENUM(*WorkspaceRole.values(), name="workspace_role"),
        nullable=False,
    )
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    workspace = db.relationship("Workspace", back_populates="memberships")
    user = db.relationship("User")


class WorkspaceInvitation(db.Model):
    """Pending invitation of an email address to workspace with a role"""

    __tablename__ = "workspace_invitation"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # stored lower-cased, matched case-insensitively with user emails
    email = db.Column(db.String, nullable=False, index=True)
    role = db.Column(
        ENUM(*WorkspaceRole.values(), name="workspace_role", create_type=False),
        nullable=False,
    )
    inviter_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    workspace = db.relationship("Workspace")
    inviter = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("workspace_id", "email"),)

    def __init__(self, workspace: Workspace, email: str, role: WorkspaceRole, inviter):
        self.uuid = uuid.uuid4()
        self.workspace_id = workspace.id
        self.workspace = workspace
        self.email = email.strip().lower()
        self.role = role.value
        self.inviter_id = inviter.id if inviter else None
        self.created = datetime.utcnow()
        self.renew()

    def renew(self) -> None:
        self.expires_at = datetime.utcnow() + timedelta(
            days=current_app.config["WORKSPACE_INVITATION_EXPIRATION"]
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at < datetime.utcnow()

    def accept(self, user: User) -> "WorkspaceMember":
        """Make user workspace member, invitation is removed, does not commit"""
        member = self.workspace.set_role(user.id, WorkspaceRole(self.role))
        db.session.delete(self)
        return member
