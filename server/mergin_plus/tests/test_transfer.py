# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.sync.models import Project, ProjectRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.transfer.models import ProjectTransfer
from mergin_plus.transfer.tasks import remove_expired_transfers
from mergin_plus.workspace.models import Workspace


def _workspace(name, owner, storage=1024 * 1024) -> Workspace:
    ws = Workspace(name=name, storage=storage)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    db.session.commit()
    return ws


def _post(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), headers=json_headers)


@patch("mergin.celery.send_email_async.apply_async")
def test_transfer_lifecycle(send_email_mock, client):
    alice = add_user("alice", "Alice123!")
    bob = add_user("bob", "Bob12345!")
    collaborator = add_user("collab", "Collab123!")
    src = _workspace("src", alice)
    dst = _workspace("dst", bob)
    p = create_project("data", src, alice)
    p.set_role(collaborator.id, ProjectRole.WRITER)
    db.session.commit()
    url = f"/v2/projects/{p.id}/transfer"

    # only project owners / workspace admins can request
    login(client, "collab", "Collab123!")
    assert _post(client, url, {"workspace": "dst"}).status_code == 403
    login(client, "alice", "Alice123!")
    assert _post(client, url, {"workspace": "src"}).status_code == 400
    assert _post(client, url, {"workspace": "nope"}).status_code == 404
    resp = _post(client, url, {"workspace": "dst"})
    assert resp.status_code == 201
    transfer_id = resp.json["id"]
    assert resp.json["to_workspace"] == "dst"
    assert send_email_mock.called
    assert _post(client, url, {"workspace": "dst"}).status_code == 409
    assert client.get(url).json["id"] == transfer_id
    assert (
        client.get(f"/v2/workspaces/{src.id}/transfers").json["outgoing"][0]["id"]
        == transfer_id
    )
    # source side can not accept
    assert _post(client, f"/v2/transfers/{transfer_id}/accept").status_code == 403

    login(client, "bob", "Bob12345!")
    resp = client.get(f"/v2/workspaces/{dst.id}/transfers")
    assert [t["project_name"] for t in resp.json["incoming"]] == ["data"]
    # name clash in target workspace, accept with a new name
    create_project("data", dst, bob)
    assert _post(client, f"/v2/transfers/{transfer_id}/accept").status_code == 409
    resp = _post(client, f"/v2/transfers/{transfer_id}/accept", {"name": "data-src"})
    assert resp.status_code == 200
    assert resp.json == {"id": str(p.id), "name": "data-src", "namespace": "dst"}
    db.session.expire_all()
    p = db.session.get(Project, p.id)
    assert p.workspace_id == dst.id
    assert p.get_role(collaborator.id) is ProjectRole.WRITER
    assert ProjectTransfer.query.count() == 0
    assert client.get("/v1/project/dst/data-src").status_code == 200
    login(client, "alice", "Alice123!")
    assert client.get("/v1/project/dst/data-src").status_code == 403


@patch("mergin.celery.send_email_async.apply_async")
def test_transfer_decline_cancel_storage_expiry(send_email_mock, client):
    alice = add_user("alice", "Alice123!")
    bob = add_user("bob", "Bob12345!")
    src = _workspace("src", alice)
    dst = _workspace("dst", bob, storage=10)
    p = create_project("data", src, alice)
    p.disk_usage = 100
    db.session.commit()
    url = f"/v2/projects/{p.id}/transfer"

    login(client, "alice", "Alice123!")
    transfer_id = _post(client, url, {"workspace": "dst"}).json["id"]
    login(client, "bob", "Bob12345!")
    resp = _post(client, f"/v2/transfers/{transfer_id}/accept")
    assert resp.status_code == 422
    assert resp.json["code"] == "StorageLimitHit"
    # target declines
    assert client.delete(f"/v2/transfers/{transfer_id}").status_code == 204

    # source cancels
    login(client, "alice", "Alice123!")
    transfer_id = _post(client, url, {"workspace": "dst"}).json["id"]
    assert client.delete(f"/v2/transfers/{transfer_id}").status_code == 204

    # expired request can not be accepted and is cleaned up
    transfer_id = _post(client, url, {"workspace": "dst"}).json["id"]
    transfer = db.session.get(ProjectTransfer, transfer_id)
    transfer.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    login(client, "bob", "Bob12345!")
    assert _post(client, f"/v2/transfers/{transfer_id}/accept").status_code == 404
    # new request replaces expired one
    login(client, "alice", "Alice123!")
    assert _post(client, url, {"workspace": "dst"}).status_code == 201
    transfer = ProjectTransfer.query.first()
    transfer.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    remove_expired_transfers()
    assert ProjectTransfer.query.count() == 0
