# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.workspace.models import Workspace
from mergin_plus.workspace.project_handler import editor_can_push


def _file(path, diff=False):
    item = {"path": path, "checksum": "a" * 40, "size": 10, "chunks": ["c1"]}
    if diff:
        item["diff"] = {"path": path + "-diff-1", "checksum": "b" * 40, "size": 5}
    return item


@pytest.mark.parametrize(
    "changes,allowed",
    [
        ({"added": [_file("photo.jpg")]}, True),
        ({"added": [_file("new.gpkg")]}, True),
        ({"updated": [_file("data.gpkg", diff=True)]}, True),
        ({"updated": [_file("notes.txt")]}, True),
        ({"removed": [_file("photo.jpg")]}, True),
        ({"updated": [_file("data.gpkg")]}, False),
        ({"removed": [_file("data.GPKG")]}, False),
        ({"updated": [_file("project.qgz")]}, False),
        ({"added": [_file("sub/other.qgs")]}, False),
        ({"removed": [_file("project.qgs")]}, False),
        ({"updated": [_file("mergin-config.json")]}, False),
        ({"added": [], "updated": [], "removed": []}, True),
    ],
)
def test_editor_can_push(changes, allowed):
    assert editor_can_push(changes) == allowed


@pytest.mark.parametrize(
    "role,path,status",
    [
        (WorkspaceRole.EDITOR, "photo.jpg", 200),
        (WorkspaceRole.EDITOR, "project.qgz", 403),
        (WorkspaceRole.WRITER, "project.qgz", 200),
        (WorkspaceRole.READER, "photo.jpg", 403),
    ],
)
def test_editor_push(client, role, path, status):
    owner = add_user("owner", "Owner123!")
    user = add_user("member", "Member123!")
    ws = Workspace(name="team", storage=1024 * 1024)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    ws.set_role(user.id, role)
    db.session.commit()
    project = create_project("p", ws, owner)

    login(client, "member", "Member123!")
    resp = client.post(
        f"/v1/project/push/team/{project.name}",
        data=json.dumps(
            {
                "version": "v0",
                "changes": {"added": [_file(path)], "updated": [], "removed": []},
            }
        ),
        headers=json_headers,
    )
    assert resp.status_code == status
