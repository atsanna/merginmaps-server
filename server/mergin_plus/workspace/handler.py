# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime, timedelta
from typing import List, Optional

from flask_login import current_user
from sqlalchemy import Column, func, or_

from mergin.app import db
from mergin.auth.models import User
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import (
    Project,
    ProjectAccessDetail,
    ProjectRole,
    ProjectUser,
)
from mergin.sync.permissions import ProjectPermissions, projects_query
from mergin.sync.workspace import GlobalWorkspaceHandler
from .models import Workspace, WorkspaceMember


class WorkspaceHandler(GlobalWorkspaceHandler):
    """Handler of workspaces stored in database.

    Inherits from CE handler the parts which do not depend on the workspace implementation
    (project members bulk update, access requests query, contributors count).
    """

    def factory_method(self, name: str, storage: int, description: str = None):
        return Workspace(name=name, storage=storage, description=description)

    @staticmethod
    def _query(active: bool = False):
        """Not closed workspaces, optionally only those not deactivated by server admin"""
        query = Workspace.query.filter(Workspace.removed_at.is_(None))
        if active:
            query = query.filter(Workspace.active.is_(True))
        return query

    def get(self, id_) -> Optional[Workspace]:
        try:
            id_ = int(id_)
        except (TypeError, ValueError):
            return None
        return db.session.get(Workspace, id_)

    def get_by_name(self, name) -> Optional[Workspace]:
        if not name:
            return None
        return Workspace.query.filter(
            func.lower(Workspace.name) == name.lower()
        ).first()

    def get_by_names(self, names) -> List[Workspace]:
        lowered = {n.lower() for n in names if n}
        if not lowered:
            return []
        return Workspace.query.filter(func.lower(Workspace.name).in_(lowered)).all()

    def get_by_project(self, project) -> Optional[Workspace]:
        return self.get(project.workspace_id)

    def get_by_ids(self, ids) -> List[Workspace]:
        ids = {i for i in ids if i is not None}
        if not ids:
            return []
        return Workspace.query.filter(Workspace.id.in_(ids)).all()

    def list_active(self) -> List[Workspace]:
        return self._query(active=True).order_by(Workspace.name).all()

    def list_all(self) -> List[Workspace]:
        return (
            Workspace.query.filter(Workspace.deleted.is_(False))
            .order_by(Workspace.name)
            .all()
        )

    def list_user_workspaces(self, name, active=False) -> List[Workspace]:
        """Workspaces where user is a member or a guest (has direct access to some project)"""
        user = User.query.filter_by(username=name).first() if name else None
        if not user:
            return []
        member_ws = db.session.query(WorkspaceMember.workspace_id).filter(
            WorkspaceMember.user_id == user.id
        )
        guest_ws = (
            db.session.query(Project.workspace_id)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .filter(ProjectUser.user_id == user.id, Project.removed_at.is_(None))
        )
        return (
            self._query(active=active)
            .filter(or_(Workspace.id.in_(member_ws), Workspace.id.in_(guest_ws)))
            .order_by(Workspace.name)
            .all()
        )

    def get_preferred(self, user) -> Optional[Workspace]:
        """Workspace with the highest user role, ties are resolved by the oldest membership"""
        workspaces = self.list_user_workspaces(user.username, active=True)
        if not workspaces:
            return None
        roles = list(WorkspaceRole.__members__)
        return max(
            workspaces,
            key=lambda ws: (roles.index(ws.get_user_role(user).name), -ws.id),
        )

    def list_user_invitations(self, user) -> list:
        # invitations are added in a later milestone
        return []

    def filter_projects(
        self,
        order_params=None,
        order_by=None,
        descending=False,
        name=None,
        namespace=None,
        user=None,
        flag=None,
        last_updated_in=None,
        only_namespace=None,
        as_admin=False,
        public=True,
        only_public=False,
    ):
        if only_public:
            projects = (
                Project.query.filter(Project.storage_params.isnot(None))
                .filter(Project.removed_at.is_(None))
                .filter(Project.public.is_(True))
            )
        else:
            projects = projects_query(
                ProjectPermissions.Read, as_admin=as_admin, public=public
            )

        if flag:
            user = User.query.filter_by(username=user).first() if user else current_user
            if user and not user.is_anonymous and user.active:
                if flag == "created":
                    projects = projects.filter(Project.creator_id == user.id)
                if flag == "shared":
                    # accessible through workspace membership or direct project access
                    readable_ws = [
                        ws.id
                        for ws in self.list_user_workspaces(user.username, active=True)
                        if ws.user_has_permissions(user, "read")
                    ]
                    direct = db.session.query(ProjectUser.project_id).filter(
                        ProjectUser.user_id == user.id
                    )
                    projects = projects.filter(
                        Project.creator_id != user.id,
                        or_(
                            Project.workspace_id.in_(readable_ws),
                            Project.id.in_(direct),
                        ),
                    )

        if name:
            projects = projects.filter(Project.name.ilike("%{}%".format(name)))

        for ws_name in (namespace, only_namespace):
            if ws_name:
                ws = self.get_by_name(ws_name)
                projects = projects.filter(
                    Project.workspace_id == (ws.id if ws else -1)
                )

        if last_updated_in:
            projects = projects.filter(
                Project.updated >= datetime.utcnow() - timedelta(days=last_updated_in)
            )

        if order_params:
            order_by_params = []
            for p in order_params.split(","):
                string_param = p.strip()
                ascending = "_asc" in string_param
                string_param = string_param.replace("_asc", "").replace("_desc", "")
                if string_param in ["workspace", "namespace"]:
                    attr = (
                        db.session.query(Workspace.name)
                        .filter(Workspace.id == Project.workspace_id)
                        .scalar_subquery()
                    )
                else:
                    attr = Project.__table__.c.get(string_param, None)
                    if not isinstance(attr, Column):
                        continue
                order_by_params.append(attr.asc() if ascending else attr.desc())
            projects = projects.order_by(*order_by_params)
        elif order_by:
            if order_by == "namespace":
                order_attr = (
                    db.session.query(Workspace.name)
                    .filter(Workspace.id == Project.workspace_id)
                    .scalar_subquery()
                )
            else:
                order_attr = Project.__table__.c.get(order_by, None)
            if order_attr is not None:
                order_attr = order_attr.desc() if descending else order_attr.asc()
                projects = projects.order_by(order_attr)
        return projects

    def projects_query(self, like: str = None):
        query = (
            db.session.query(Project, Workspace.name.label("workspace_name"))
            .join(Workspace, Workspace.id == Project.workspace_id)
            .filter(Project.storage_params.isnot(None))
        )
        if like:
            query = query.filter(
                Project.name.ilike(f"%{like}%") | Workspace.name.ilike(f"%{like}%")
            )
        return query

    def project_access(self, project: Project) -> List[ProjectAccessDetail]:
        """Users with access to project, either directly or through workspace membership"""
        ws = self.get(project.workspace_id)
        result = []
        seen = set()
        direct_ids = [pu.user_id for pu in project.project_users]
        direct_members = (
            User.query.filter(User.active.is_(True), User.id.in_(direct_ids))
            .order_by(User.email)
            .all()
        )
        for user in direct_members + [u for u, _ in ws.members()]:
            if user.id in seen:
                continue
            seen.add(user.id)
            permission = ProjectPermissions.get_user_project_role(project, user)
            project_role = project.get_role(user.id)
            ws_role = ws.get_user_role(user)
            result.append(
                ProjectAccessDetail(
                    id=user.id,
                    username=user.username,
                    name=user.profile.name(),
                    email=user.email,
                    workspace_role=ws_role.value if ws_role else None,
                    role=permission.value if permission else None,
                    project_role=project_role.value if project_role else None,
                    type="member",
                )
            )
        return result

    @staticmethod
    def workspace_count() -> int:
        return Workspace.query.filter(Workspace.removed_at.is_(None)).count()

    def server_editors_count(self) -> int:
        """Active users who can change data in some active workspace project"""
        member_editors = (
            db.session.query(WorkspaceMember.user_id)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .filter(
                Workspace.removed_at.is_(None),
                WorkspaceMember.role.notin_(
                    [WorkspaceRole.GUEST.value, WorkspaceRole.READER.value]
                ),
            )
        )
        project_editors = (
            db.session.query(ProjectUser.user_id)
            .join(Project, Project.id == ProjectUser.project_id)
            .filter(
                Project.removed_at.is_(None),
                ProjectUser.role != ProjectRole.READER.value,
            )
        )
        return User.query.filter(
            User.active.is_(True),
            or_(User.id.in_(member_editors), User.id.in_(project_editors)),
        ).count()
