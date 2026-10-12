# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import os
from typing import Dict, List

from mergin.auth.models import User
from mergin.sync.models import Project, ProjectRole, ProjectUser
from mergin.sync.permissions import ProjectPermissions
from mergin.sync.project_handler import ProjectHandler as CEProjectHandler
from mergin.sync.interfaces import WorkspaceRole
from .models import WorkspaceMember

# files defining project structure, editors can not change them
PROTECTED_EXTENSIONS = (".qgs", ".qgz")
PROTECTED_FILES = ("mergin-config.json",)
GEOPACKAGE_EXTENSION = ".gpkg"


def _is_protected(path: str) -> bool:
    name = os.path.basename(path).lower()
    return name in PROTECTED_FILES or name.endswith(PROTECTED_EXTENSIONS)


def _is_geopackage(path: str) -> bool:
    return path.lower().endswith(GEOPACKAGE_EXTENSION)


def editor_can_push(changes: Dict[str, List[dict]]) -> bool:
    """Whether changes are allowed for editors: data edits only, no changes of project structure.

    - QGIS project files and mergin-config.json can not be added, updated or removed
    - geopackages can be updated only with diffs (no schema changes) and can not be removed
    - other files (e.g. photos) can be freely added, updated and removed
    """
    for item in changes.get("added", []):
        if _is_protected(item["path"]):
            return False
    for item in changes.get("updated", []):
        path = item["path"]
        if _is_protected(path):
            return False
        if _is_geopackage(path) and not item.get("diff"):
            return False
    for item in changes.get("removed", []):
        path = item["path"]
        if _is_protected(path) or _is_geopackage(path):
            return False
    return True


class ProjectHandler(CEProjectHandler):
    def get_push_permission(self, changes: dict):
        if editor_can_push(changes):
            return ProjectPermissions.Edit
        return ProjectPermissions.Upload

    def get_email_receivers(self, project: Project) -> List[User]:
        """Project owners and workspace owners/admins who want to receive notifications"""
        direct_owners = ProjectUser.query.with_entities(ProjectUser.user_id).filter(
            ProjectUser.project_id == project.id,
            ProjectUser.role == ProjectRole.OWNER.value,
        )
        ws_managers = WorkspaceMember.query.with_entities(
            WorkspaceMember.user_id
        ).filter(
            WorkspaceMember.workspace_id == project.workspace_id,
            WorkspaceMember.role.in_(
                [WorkspaceRole.ADMIN.value, WorkspaceRole.OWNER.value]
            ),
        )
        return User.query.filter(
            User.id.in_(direct_owners) | User.id.in_(ws_managers),
            User.active,
            User.verified_email,
            User.receive_notifications,
        ).all()
