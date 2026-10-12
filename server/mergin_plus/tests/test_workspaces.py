# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import json
from datetime import datetime, timedelta

import pytest
from flask import current_app

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import Project
from mergin.sync.permissions import ProjectPermissions
from mergin.sync.models import ProjectRole
from mergin.tests import json_headers, test_workspace_id
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.workspace.controller import workspace_name_validation
from mergin_plus.workspace.models import Workspace, WorkspaceMember
from mergin_plus.workspace.tasks import remove_closed_workspaces


def _workspace(name: str, owner=None, **members) -> Workspace:
    ws = Workspace(name=name, storage=1024 * 1024)
    db.session.add(ws)
    db.session.flush()
    if owner:
        ws.set_role(owner.id, WorkspaceRole.OWNER)
    for user, role in members.values():
        ws.set_role(user.id, role)
    db.session.commit()
    return ws


def test_config(client):
    resp = client.get("/config")
    assert resp.json["server_type"] == "ee"
    assert resp.json["collect_statistics"] is False
    assert resp.json["user_workspaces_allowed"] is True


@pytest.mark.parametrize(
    "name,valid",
    [
        ("my-workspace", True),
        ("ws_1.0", True),
        ("", False),
        ("with space", False),
        (".hidden", False),
        ("admin", False),
        ("Admin", False),
        ("a/b", False),
    ],
)
def test_workspace_name_validation(name, valid):
    assert (workspace_name_validation(name) is None) == valid


def test_create_workspace(client):
    user = add_user("alice", "Alice123!")
    login(client, "alice", "Alice123!")
    resp = client.post(
        "/v1/workspace",
        data=json.dumps({"name": "alice-ws", "description": "test"}),
        headers=json_headers,
    )
    assert resp.status_code == 201
    assert resp.json["name"] == "alice-ws"
    assert resp.json["role"] == "owner"
    assert resp.json["storage"] == current_app.config["WORKSPACE_STORAGE_SIZE"]
    ws = current_app.ws_handler.get(resp.json["id"])
    assert ws.get_user_role(user) is WorkspaceRole.OWNER

    # name is unique (case insensitive)
    resp = client.post(
        "/v1/workspace", data=json.dumps({"name": "ALICE-ws"}), headers=json_headers
    )
    assert resp.status_code == 409
    resp = client.post(
        "/v1/workspace", data=json.dumps({"name": "bad name"}), headers=json_headers
    )
    assert resp.status_code == 400

    # listed in user workspaces and user info
    resp = client.get("/v1/workspaces")
    assert [w["name"] for w in resp.json] == ["alice-ws"]
    resp = client.get("/v1/user/profile")
    assert resp.status_code == 200


def test_create_workspace_not_allowed(client):
    add_user("bob", "Bob12345!")
    current_app.config["USER_WORKSPACES_ALLOWED"] = False
    try:
        login(client, "bob", "Bob12345!")
        resp = client.post(
            "/v1/workspace", data=json.dumps({"name": "bob-ws"}), headers=json_headers
        )
        assert resp.status_code == 403
        # superuser still can
        login(client, "mergin", "ilovemergin")
        resp = client.post(
            "/v1/workspace", data=json.dumps({"name": "bob-ws"}), headers=json_headers
        )
        assert resp.status_code == 201
    finally:
        current_app.config["USER_WORKSPACES_ALLOWED"] = True


def test_update_workspace(client):
    owner = add_user("owner", "Owner123!")
    admin = add_user("wsadmin", "Wsadmin123!")
    ws = _workspace("upd", owner, a=(admin, WorkspaceRole.ADMIN))

    login(client, "wsadmin", "Wsadmin123!")
    resp = client.patch(
        f"/v1/workspace/{ws.id}",
        data=json.dumps({"description": "new"}),
        headers=json_headers,
    )
    assert resp.status_code == 403

    login(client, "owner", "Owner123!")
    resp = client.patch(
        f"/v1/workspace/{ws.id}",
        data=json.dumps({"description": "new"}),
        headers=json_headers,
    )
    assert resp.status_code == 200
    assert resp.json["description"] == "new"
    resp = client.patch(
        f"/v1/workspace/{ws.id}",
        data=json.dumps({"name": "renamed"}),
        headers=json_headers,
    )
    assert resp.status_code == 400
    resp = client.patch("/v1/workspace/9999", data=json.dumps({}), headers=json_headers)
    assert resp.status_code == 404


def test_roles_and_project_permissions(app):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    editor = add_user("editor", "Editor123!")
    writer = add_user("writer", "Writer123!")
    admin = add_user("wsadmin", "Wsadmin123!")
    guest = add_user("guest", "Guest1234!")
    outsider = add_user("outsider", "Outsider1!")
    ws = _workspace(
        "roles",
        owner,
        r=(reader, WorkspaceRole.READER),
        e=(editor, WorkspaceRole.EDITOR),
        w=(writer, WorkspaceRole.WRITER),
        a=(admin, WorkspaceRole.ADMIN),
    )
    p = create_project("p1", ws, owner)
    other = create_project("p2", ws, owner)
    other.set_role(guest.id, ProjectRole.READER)
    db.session.commit()

    expected = {
        owner: ProjectRole.OWNER,
        admin: ProjectRole.OWNER,
        writer: ProjectRole.WRITER,
        editor: ProjectRole.EDITOR,
        reader: ProjectRole.READER,
        guest: None,
        outsider: None,
    }
    for user, role in expected.items():
        assert ProjectPermissions.get_user_project_role(p, user) == role, user.username

    assert ws.get_user_role(guest) is WorkspaceRole.GUEST
    assert ws.get_user_role(outsider) is None
    assert ProjectPermissions.get_user_project_role(other, guest) == ProjectRole.READER

    # project role raises access over workspace role
    p.set_role(reader.id, ProjectRole.OWNER)
    db.session.commit()
    assert ProjectPermissions.get_user_project_role(p, reader) == ProjectRole.OWNER

    # project lists respect workspaces
    handler = current_app.ws_handler
    assert {w.name for w in handler.list_user_workspaces("guest")} == {"roles"}
    assert handler.list_user_workspaces("outsider") == []
    assert handler.get_preferred(reader).name == "roles"


def test_projects_isolated_between_workspaces(client):
    alice = add_user("alice", "Alice123!")
    bob = add_user("bob", "Bob12345!")
    ws_a = _workspace("ws-a", alice)
    ws_b = _workspace("ws-b", bob)
    create_project("same", ws_a, alice)
    create_project("same", ws_b, bob)

    login(client, "alice", "Alice123!")
    resp = client.get("/v1/project/ws-a/same")
    assert resp.status_code == 200
    resp = client.get("/v1/project/ws-b/same")
    assert resp.status_code == 403
    resp = client.get("/v1/project/paginated?page=1&per_page=50")
    names = {(p["namespace"], p["name"]) for p in resp.json["projects"]}
    assert ("ws-a", "same") in names
    assert ("ws-b", "same") not in names

    # only workspace admins can create projects
    resp = client.post(
        "/v1/project/ws-b", data=json.dumps({"name": "new"}), headers=json_headers
    )
    assert resp.status_code == 403
    resp = client.post(
        "/v1/project/ws-a", data=json.dumps({"name": "new"}), headers=json_headers
    )
    assert resp.status_code == 200


def test_workspace_usage(client):
    alice = add_user("alice", "Alice123!")
    reader = add_user("reader", "Reader123!")
    ws = _workspace("usage", alice, r=(reader, WorkspaceRole.READER))
    p = create_project("p", ws, alice)
    p.disk_usage = 1000
    db.session.commit()

    login(client, "reader", "Reader123!")
    assert client.get(f"/v1/workspace/{ws.id}/usage").status_code == 403
    login(client, "alice", "Alice123!")
    resp = client.get(f"/v1/workspace/{ws.id}/usage")
    assert resp.status_code == 200
    assert resp.json == {
        "storage": 1024 * 1024,
        "disk_usage": 1000,
        "project_count": 1,
        "members_count": 2,
        "contributors_count": 1,
        "contributors_limit": None,
    }


def test_storage_limit_per_workspace(client):
    alice = add_user("alice", "Alice123!")
    ws = _workspace("small", alice)
    ws.storage = 10
    db.session.commit()
    p = create_project("p", ws, alice)
    login(client, "alice", "Alice123!")
    changes = {
        "added": [
            {"path": "big.txt", "checksum": "a" * 40, "size": 100, "chunks": ["c1"]}
        ],
        "updated": [],
        "removed": [],
    }
    resp = client.post(
        f"/v1/project/push/small/{p.name}",
        data=json.dumps({"version": "v0", "changes": changes}),
        headers=json_headers,
    )
    assert resp.status_code == 422
    assert resp.json["code"] == "StorageLimitHit"


def test_close_and_purge_workspace(client):
    alice = add_user("alice", "Alice123!")
    ws = _workspace("closing", alice)
    p = create_project("p", ws, alice)
    ws_id = ws.id

    login(client, "alice", "Alice123!")
    resp = client.delete(f"/v1/workspace/{ws_id}")
    assert resp.status_code == 204
    assert client.get(f"/v1/workspace/{ws_id}").status_code == 404
    assert client.get("/v1/project/closing/p").status_code == 404
    assert client.get("/v1/workspaces").json == []

    # not yet expired
    remove_closed_workspaces()
    assert db.session.get(Project, p.id).storage_params is not None

    ws = db.session.get(Workspace, ws_id)
    ws.removed_at = datetime.utcnow() - timedelta(
        days=current_app.config["WORKSPACE_EXPIRATION"] + 1
    )
    db.session.commit()
    remove_closed_workspaces()
    ws = db.session.get(Workspace, ws_id)
    assert ws.deleted
    assert ws.name == f"closing_{ws_id}"
    assert db.session.get(Project, p.id).storage_params is None
    assert WorkspaceMember.query.filter_by(workspace_id=ws_id).count() == 0

    # name is free again
    resp = client.post(
        "/v1/workspace", data=json.dumps({"name": "closing"}), headers=json_headers
    )
    assert resp.status_code == 201


def test_global_workspace_fixture(client):
    """CE test project lives in workspace 1 which is a db row owned by superuser"""
    ws = current_app.ws_handler.get(test_workspace_id)
    assert ws.name == "mergin"
    assert client.get("/v1/project/mergin/test").status_code == 200
    assert current_app.ws_handler.workspace_count() == 1
