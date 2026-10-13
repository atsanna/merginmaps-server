# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for issues found by the code review of the add-on"""

import json
from unittest.mock import patch

from mergin.app import db
from mergin.auth.models import User
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import Project, ProjectRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.workspace.models import Workspace
from mergin_plus.workspace.tasks import remove_closed_workspaces


def _ws(name, owner, limit=None, *members):
    ws = Workspace(name=name, storage=1024 * 1024, contributors_limit=limit)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    for user, role in members:
        ws.set_role(user.id, role)
    db.session.commit()
    return ws


def _post(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), headers=json_headers)


def _create_user(client, ws, role, username="newuser"):
    return _post(
        client,
        "/v2/users",
        {
            "email": f"{username}@x.com",
            "username": username,
            "password": "Newuser123!",
            "workspace_id": ws.id,
            "role": role,
        },
    )


@patch("mergin.celery.send_email_async.apply_async")
def test_ce_create_user_guard(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    admin = add_user("wsadmin", "Wsadmin123!")
    ws = _ws("team", owner, 2, (admin, WorkspaceRole.ADMIN))

    # admins can not create owners, guests are not a membership role
    login(client, "wsadmin", "Wsadmin123!")
    assert _create_user(client, ws, "owner", "puppet").status_code == 403
    assert _create_user(client, ws, "guest", "guestuser").status_code == 400
    assert User.query.filter_by(username="puppet").first() is None
    # limit (owner + admin = 2 contributors) is checked before the user is created
    resp = _create_user(client, ws, "writer", "wuser")
    assert resp.status_code == 422
    assert User.query.filter_by(username="wuser").first() is None
    resp = _create_user(client, ws, "reader", "ruser")
    assert resp.status_code == 201
    user = User.query.filter_by(username="ruser").first()
    assert ws.get_member(user.id).role == "reader"

    # closed workspace
    ws.close(owner.id)
    db.session.commit()
    login(client, "owner", "Owner123!")
    assert _create_user(client, ws, "reader", "late").status_code == 404


@patch("mergin.celery.send_email_async.apply_async")
def test_invitation_requires_verified_email(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    attacker = add_user("attacker", "Attacker123!")
    ws = _ws("team", owner)
    login(client, "owner", "Owner123!")
    uuid = _post(
        client,
        f"/v2/workspaces/{ws.id}/invitations",
        {"email": "boss@corp.com", "role": "admin"},
    ).json["uuid"]
    # attacker sets the invited e-mail on own profile (CE marks it unverified)
    attacker.email = "boss@corp.com"
    attacker.verified_email = False
    db.session.commit()
    login(client, "attacker", "Attacker123!")
    assert client.get("/v2/invitations").json == []
    assert _post(client, f"/v2/invitations/{uuid}/accept").status_code == 404
    assert ws.get_member(attacker.id) is None


@patch("mergin.celery.send_email_async.apply_async")
def test_share_extend_is_not_new_contributor(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _ws("team", owner, 2)
    p1 = create_project("p1", ws, owner)
    p2 = create_project("p2", ws, owner)
    login(client, "owner", "Owner123!")
    url = "/v2/projects/{}/invitations"
    assert (
        _post(
            client, url.format(p1.id), {"email": "x@y.com", "role": "writer"}
        ).status_code
        == 201
    )
    assert (
        _post(
            client, url.format(p2.id), {"email": "x@y.com", "role": "writer"}
        ).status_code
        == 200
    )


@patch("mergin.celery.send_email_async.apply_async")
def test_transfer_respects_contributors_limit(send_email_mock, client):
    alice = add_user("alice", "Alice123!")
    bob = add_user("bob", "Bob12345!")
    writer = add_user("w1", "Writer123!")
    src = _ws("src", alice)
    dst = _ws("dst", bob, 1)
    p = create_project("data", src, alice)
    p.set_role(writer.id, ProjectRole.WRITER)
    db.session.commit()
    login(client, "alice", "Alice123!")
    transfer_id = _post(
        client, f"/v2/projects/{p.id}/transfer", {"workspace": "dst"}
    ).json["id"]
    login(client, "bob", "Bob12345!")
    resp = _post(client, f"/v2/transfers/{transfer_id}/accept")
    assert resp.status_code == 422
    assert resp.json["code"] == "ContributorsLimitHit"
    db.session.expire_all()
    assert db.session.get(Project, p.id).workspace_id == src.id


@patch("mergin.celery.send_email_async.apply_async")
def test_closed_workspace_is_not_usable_by_name(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _ws("team", owner)
    ws.close(owner.id)
    db.session.commit()
    login(client, "owner", "Owner123!")
    assert _post(client, "/v1/project/team", {"name": "sneaky"}).status_code == 404
    # name of closed workspace is still taken until it is removed
    assert _post(client, "/v1/workspace", {"name": "team"}).status_code == 409


@patch("mergin.celery.send_email_async.apply_async")
def test_purge_does_not_clash_with_other_names(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _ws("acme", owner)
    p = create_project("p", ws, owner)
    _ws(f"acme_{ws.id}", owner)
    broken = _ws("broken", owner)
    ws.close(owner.id)
    broken.close(owner.id)
    db.session.commit()
    ws.removed_at = broken.removed_at = ws.removed_at.replace(year=2000)
    db.session.commit()
    with patch.object(Workspace, "purge", side_effect=[RuntimeError("boom"), None]):
        # a failing workspace does not stop the others
        remove_closed_workspaces()
    remove_closed_workspaces()
    db.session.expire_all()
    ws = db.session.get(Workspace, ws.id)
    assert ws.deleted and ws.name == f"acme#deleted-{ws.id}"
    assert db.session.get(Project, p.id).storage_params is None


def test_project_access_roles(client):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    guest = add_user("guest", "Guest1234!")
    ws = _ws("team", owner, None, (reader, WorkspaceRole.READER))
    p = create_project("p", ws, owner)
    p.set_role(reader.id, ProjectRole.WRITER)
    p.set_role(guest.id, ProjectRole.EDITOR)
    db.session.commit()
    from flask import current_app

    access = {a.username: a for a in current_app.ws_handler.project_access(p)}
    assert access["owner"].role == "owner" and access["owner"].workspace_role == "owner"
    assert (
        access["reader"].role == "writer"
        and access["reader"].workspace_role == "reader"
    )
    assert (
        access["guest"].role == "editor" and access["guest"].workspace_role == "guest"
    )
