# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from flask import current_app

from mergin.app import db
from mergin.auth.models import User
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import ProjectRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.workspace.models import Workspace, WorkspaceInvitation
from mergin_plus.workspace.tasks import remove_expired_invitations


def _workspace(name, owner, *members) -> Workspace:
    ws = Workspace(name=name, storage=1024 * 1024)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    for user, role in members:
        ws.set_role(user.id, role)
    db.session.commit()
    return ws


def _post(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), headers=json_headers)


def _patch(client, url, data):
    return client.patch(url, data=json.dumps(data), headers=json_headers)


def test_members_api(client):
    owner = add_user("owner", "Owner123!")
    admin = add_user("wsadmin", "Wsadmin123!")
    reader = add_user("reader", "Reader123!")
    ws = _workspace(
        "team", owner, (admin, WorkspaceRole.ADMIN), (reader, WorkspaceRole.READER)
    )
    url = f"/v2/workspaces/{ws.id}/members"

    login(client, "reader", "Reader123!")
    assert client.get(url).status_code == 403
    # member can see own detail
    resp = client.get(f"{url}/{reader.id}")
    assert resp.status_code == 200
    assert resp.json["workspace_role"] == "reader"
    assert resp.json["contributor"] is False
    assert client.get(f"{url}/{owner.id}").status_code == 403

    login(client, "wsadmin", "Wsadmin123!")
    resp = client.get(url)
    assert resp.status_code == 200
    assert {m["username"]: m["workspace_role"] for m in resp.json} == {
        "owner": "owner",
        "wsadmin": "admin",
        "reader": "reader",
    }

    # python client sends workspace_role
    resp = _patch(client, f"{url}/{reader.id}", {"workspace_role": "writer"})
    assert resp.status_code == 200
    assert resp.json["workspace_role"] == "writer"
    # docs mention role
    resp = _patch(client, f"{url}/{reader.id}", {"role": "editor"})
    assert resp.json["workspace_role"] == "editor"
    assert resp.json["contributor"] is True
    assert _patch(client, f"{url}/{reader.id}", {"role": "guest"}).status_code == 400
    assert _patch(client, f"{url}/{reader.id}", {}).status_code == 400
    # admins can not manage owners
    assert _patch(client, f"{url}/{reader.id}", {"role": "owner"}).status_code == 403
    assert _patch(client, f"{url}/{owner.id}", {"role": "reader"}).status_code == 403
    assert client.delete(f"{url}/{owner.id}").status_code == 403
    assert _patch(client, f"{url}/9999", {"role": "reader"}).status_code == 404

    # last owner can not be demoted
    login(client, "owner", "Owner123!")
    assert _patch(client, f"{url}/{owner.id}", {"role": "admin"}).status_code == 400
    assert client.delete(f"{url}/{owner.id}").status_code == 400
    assert _patch(client, f"{url}/{admin.id}", {"role": "owner"}).status_code == 200
    assert _patch(client, f"{url}/{owner.id}", {"role": "admin"}).status_code == 200


def test_reset_projects_roles_and_remove_member(client):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    ws = _workspace("team", owner, (reader, WorkspaceRole.READER))
    p = create_project("p", ws, owner)
    p.set_role(reader.id, ProjectRole.WRITER)
    db.session.commit()
    url = f"/v2/workspaces/{ws.id}/members/{reader.id}"

    login(client, "owner", "Owner123!")
    resp = _patch(client, url, {"role": "reader", "reset_projects_roles": True})
    assert resp.status_code == 200
    db.session.expire_all()
    assert p.get_role(reader.id) is None

    p.set_role(reader.id, ProjectRole.WRITER)
    db.session.commit()
    # member leaves workspace, also direct project access is removed
    login(client, "reader", "Reader123!")
    assert client.delete(url).status_code == 204
    db.session.expire_all()
    assert ws.get_member(reader.id) is None
    assert ws.get_user_role(reader) is None


@patch("mergin.celery.send_email_async.apply_async")
def test_invitation_lifecycle(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    invitee = add_user("invitee", "Invitee123!")
    url = f"/v2/workspaces/{ws.id}/invitations"

    login(client, "owner", "Owner123!")
    # python client payload
    resp = _post(client, url, {"email": "Invitee@Mergin.com", "role": "writer"})
    assert resp.status_code == 201
    assert resp.json["email"] == "invitee@mergin.com"
    assert resp.json["role"] == "writer"
    assert send_email_mock.called
    uuid = resp.json["uuid"]
    assert (
        _post(
            client, url, {"email": "invitee@mergin.com", "role": "reader"}
        ).status_code
        == 409
    )
    assert (
        _post(client, url, {"email": "nonsense", "role": "reader"}).status_code == 400
    )
    assert _post(client, url, {"email": "a@b.com", "role": "guest"}).status_code == 400
    assert len(client.get(url).json) == 1

    # invitee sees invitation in user info and invitations list
    login(client, "invitee", "Invitee123!")
    assert client.get(url).status_code == 403
    resp = client.get("/v2/invitations")
    assert [i["workspace"] for i in resp.json] == ["team"]
    resp = client.get("/v1/user/profile")
    assert [i["workspace"] for i in resp.json["invitations"]] == ["team"]
    resp = client.post(f"/v2/invitations/{uuid}/accept")
    assert resp.status_code == 200
    assert resp.json["workspace_role"] == "writer"
    assert ws.get_user_role(invitee) is WorkspaceRole.WRITER
    assert WorkspaceInvitation.query.count() == 0
    assert client.post(f"/v2/invitations/{uuid}/accept").status_code == 404
    # inviting existing member is not possible
    login(client, "owner", "Owner123!")
    assert (
        _post(
            client, url, {"email": "invitee@mergin.com", "role": "reader"}
        ).status_code
        == 409
    )


@patch("mergin.celery.send_email_async.apply_async")
def test_invitation_admin_actions(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    admin = add_user("wsadmin", "Wsadmin123!")
    ws = _workspace("team", owner, (admin, WorkspaceRole.ADMIN))
    add_user("someone", "Someone123!")
    url = f"/v2/workspaces/{ws.id}/invitations"

    login(client, "wsadmin", "Wsadmin123!")
    # admins can not invite owners
    assert _post(client, url, {"email": "x@y.com", "role": "owner"}).status_code == 403
    uuid = _post(client, url, {"email": "someone@mergin.com", "role": "reader"}).json[
        "uuid"
    ]

    # expired invitation is not offered to user and can be resent
    inv = WorkspaceInvitation.query.filter_by(email="someone@mergin.com").first()
    inv.expires_at = datetime.utcnow() - timedelta(days=1)
    db.session.commit()
    assert client.get(url).json[0]["expired"] is True
    login(client, "someone", "Someone123!")
    assert client.get("/v2/invitations").json == []
    assert client.post(f"/v2/invitations/{uuid}/accept").status_code == 404

    login(client, "wsadmin", "Wsadmin123!")
    resp = _post(client, f"{url}/{uuid}/resend")
    assert resp.status_code == 200
    assert resp.json["expired"] is False
    assert send_email_mock.call_count == 2

    login(client, "someone", "Someone123!")
    assert client.post(f"/v2/invitations/{uuid}/decline").status_code == 204
    assert WorkspaceInvitation.query.count() == 0

    login(client, "wsadmin", "Wsadmin123!")
    uuid = _post(client, url, {"email": "new@person.com", "role": "editor"}).json[
        "uuid"
    ]
    assert client.delete(f"{url}/{uuid}").status_code == 204
    assert client.delete(f"{url}/{uuid}").status_code == 404


@patch("mergin.celery.send_email_async.apply_async")
def test_remove_expired_invitations(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    login(client, "owner", "Owner123!")
    url = f"/v2/workspaces/{ws.id}/invitations"
    _post(client, url, {"email": "old@person.com", "role": "reader"})
    _post(client, url, {"email": "recent@person.com", "role": "reader"})
    expiration = current_app.config["WORKSPACE_INVITATION_EXPIRATION"]
    old = WorkspaceInvitation.query.filter_by(email="old@person.com").first()
    old.expires_at = datetime.utcnow() - timedelta(days=expiration + 1)
    recent = WorkspaceInvitation.query.filter_by(email="recent@person.com").first()
    recent.expires_at = datetime.utcnow() - timedelta(days=1)
    db.session.commit()
    remove_expired_invitations()
    assert [i.email for i in WorkspaceInvitation.query.all()] == ["recent@person.com"]


def test_user_info_workspaces_and_invitations(client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    with patch("mergin.celery.send_email_async.apply_async"):
        _post(
            client,
            f"/v2/workspaces/{ws.id}/invitations",
            {"email": "mergin@mergin.com", "role": "admin"},
        )

    login(client, "owner", "Owner123!")
    resp = client.get("/v1/user/profile")
    assert resp.status_code == 200
    assert resp.json["workspaces"] == [{"id": ws.id, "name": "team", "role": "owner"}]
    assert resp.json["preferred_workspace"] == ws.id

    # superuser is not a member of the workspace, but is invited
    login(client, "mergin", "ilovemergin")
    resp = client.get("/v1/user/profile")
    assert [w["name"] for w in resp.json["workspaces"]] == ["mergin"]
    assert [i["workspace"] for i in resp.json["invitations"]] == ["team"]


def test_create_user_in_workspace(client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    login(client, "owner", "Owner123!")
    data = {
        "email": "created@example.com",
        "password": "Created123!",
        "workspace_id": ws.id,
        "role": "editor",
    }
    resp = _post(client, "/v2/users", data)
    assert resp.status_code == 201
    member = client.get(f"/v2/workspaces/{ws.id}/members").json
    assert {m["email"]: m["workspace_role"] for m in member}[
        "created@example.com"
    ] == "editor"

    # readers can not add users
    reader = add_user("reader", "Reader123!")
    ws.set_role(reader.id, WorkspaceRole.READER)
    db.session.commit()
    login(client, "reader", "Reader123!")
    data["email"] = "other@example.com"
    assert _post(client, "/v2/users", data).status_code == 403


@patch("mergin.celery.send_email_async.apply_async")
def test_register_from_invitation(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    login(client, "owner", "Owner123!")
    uuid = _post(
        client,
        f"/v2/workspaces/{ws.id}/invitations",
        {"email": "Newbie@Example.com", "role": "editor"},
    ).json["uuid"]
    assert current_app.config["USER_SELF_REGISTRATION"] is False

    anonymous = current_app.test_client()
    url = f"/v2/invitations/{uuid}/register"
    assert _post(anonymous, url, {"password": "weak"}).status_code == 400
    resp = _post(anonymous, url, {"password": "Newbie123!", "username": "newbie"})
    assert resp.status_code == 201
    assert resp.json["username"] == "newbie"
    assert resp.json["email"] == "newbie@example.com"
    user = User.query.filter_by(username="newbie").first()
    assert user.verified_email and user.active
    assert ws.get_user_role(user) is WorkspaceRole.EDITOR
    # invitation was used
    assert _post(anonymous, url, {"password": "Newbie123!"}).status_code == 404

    # account with invited email exists already
    uuid = _post(
        client,
        f"/v2/workspaces/{ws.id}/invitations",
        {"email": "owner@mergin.com", "role": "reader"},
    )
    assert uuid.status_code == 409
    add_user("existing", "Existing123!")
    other = _workspace("other", owner)
    uuid = _post(
        client,
        f"/v2/workspaces/{other.id}/invitations",
        {"email": "existing@mergin.com", "role": "reader"},
    ).json["uuid"]
    resp = _post(
        anonymous, f"/v2/invitations/{uuid}/register", {"password": "Existing123!"}
    )
    assert resp.status_code == 409
