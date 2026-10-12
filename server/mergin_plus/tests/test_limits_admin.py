# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import json
from unittest.mock import patch

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import ProjectRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.workspace.models import Workspace


def _workspace(name, owner, limit=None) -> Workspace:
    ws = Workspace(name=name, storage=1024 * 1024, contributors_limit=limit)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    db.session.commit()
    return ws


def _post(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), headers=json_headers)


def _patch(client, url, data):
    return client.patch(url, data=json.dumps(data), headers=json_headers)


@patch("mergin.celery.send_email_async.apply_async")
def test_contributors_limit(send_email_mock, client):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    other = add_user("other", "Other1234!")
    ws = _workspace("team", owner, limit=2)
    ws.set_role(reader.id, WorkspaceRole.READER)
    db.session.commit()
    p = create_project("p", ws, owner)
    login(client, "owner", "Owner123!")
    members = f"/v2/workspaces/{ws.id}/members"

    # readers are not contributors, one more contributor fits
    assert ws.contributors() == {owner.id}
    resp = _patch(client, f"{members}/{reader.id}", {"role": "editor"})
    assert resp.status_code == 200
    # limit reached: CE collaborators API, member role change and invitations are refused
    resp = _post(
        client,
        f"/v2/projects/{p.id}/collaborators",
        {"user": "other", "role": "writer"},
    )
    assert resp.status_code == 422
    assert resp.json["code"] == "ContributorsLimitHit"
    assert p.get_role(other.id) is None
    resp = _post(
        client,
        f"/v2/projects/{p.id}/collaborators",
        {"user": "other", "role": "reader"},
    )
    assert resp.status_code == 201
    resp = _post(
        client,
        f"/v2/workspaces/{ws.id}/invitations",
        {"email": "new@person.com", "role": "writer"},
    )
    assert resp.status_code == 422
    resp = _post(
        client,
        f"/v2/workspaces/{ws.id}/invitations",
        {"email": "new@person.com", "role": "reader"},
    )
    assert resp.status_code == 201
    # changes of existing contributors are fine
    assert (
        _patch(client, f"{members}/{reader.id}", {"role": "writer"}).status_code == 200
    )
    usage = client.get(f"/v1/workspace/{ws.id}/usage").json
    assert usage["contributors_count"] == 2
    assert usage["contributors_limit"] == 2

    # workspace over limit after admin lowered it: no new contributor, other changes allowed
    ws.contributors_limit = 1
    db.session.commit()
    assert (
        _patch(client, f"{members}/{reader.id}", {"role": "reader"}).status_code == 200
    )
    assert (
        _patch(client, f"{members}/{reader.id}", {"role": "editor"}).status_code == 422
    )


def test_admin_workspaces(client):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("team", owner)
    create_project("p", ws, owner)

    # superuser only
    login(client, "owner", "Owner123!")
    assert client.get("/app/admin/workspaces").status_code == 403
    login(client, "mergin", "ilovemergin")

    resp = client.get("/app/admin/workspaces?order_params=name DESC")
    assert resp.status_code == 200
    assert resp.json["count"] == 2
    assert [w["name"] for w in resp.json["items"]] == ["team", "mergin"]
    assert client.get("/app/admin/workspaces?like=tea").json["count"] == 1

    resp = _post(
        client,
        "/app/admin/workspaces",
        {"name": "created", "storage": 5000, "contributors_limit": 3},
    )
    assert resp.status_code == 201
    assert resp.json["storage"] == 5000
    assert resp.json["contributors_limit"] == 3
    assert resp.json["members_count"] == 0
    assert (
        _post(client, "/app/admin/workspaces", {"name": "Created"}).status_code == 409
    )

    resp = client.get(f"/app/admin/workspaces/{ws.id}")
    assert resp.json["project_count"] == 1
    assert [m["username"] for m in resp.json["members"]] == ["owner"]

    resp = _patch(
        client,
        f"/app/admin/workspaces/{ws.id}",
        {"storage": 10, "contributors_limit": 5, "active": False},
    )
    assert resp.status_code == 200
    assert resp.json["active"] is False
    assert (
        _patch(client, f"/app/admin/workspaces/{ws.id}", {"storage": -1}).status_code
        == 400
    )

    # deactivated workspace is not accessible to its users
    login(client, "owner", "Owner123!")
    assert client.get("/v1/project/team/p").status_code == 404
    login(client, "mergin", "ilovemergin")
    _patch(client, f"/app/admin/workspaces/{ws.id}", {"active": True})

    # scheduled removal and restore
    resp = client.delete(f"/app/admin/workspaces/{ws.id}")
    assert resp.status_code == 200
    assert resp.json["removed_at"] and resp.json["expiration"]
    resp = _post(client, f"/app/admin/workspaces/{ws.id}/restore")
    assert resp.status_code == 200
    assert resp.json["removed_at"] is None
    assert _post(client, f"/app/admin/workspaces/{ws.id}/restore").status_code == 400
    assert client.get("/app/admin/workspaces/9999").status_code == 404
