# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from flask import current_app

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.tests import json_headers
from mergin.tests.utils import add_user, create_project, login
from mergin_plus.audit.models import AuditLog
from mergin_plus.webhooks.delivery import (
    WebhookUrlError,
    deliver_webhook,
    sign,
    validate_url,
)
from mergin_plus.webhooks.models import Webhook
from mergin_plus.workspace.models import Workspace


def _workspace(name, owner) -> Workspace:
    ws = Workspace(name=name, storage=1024 * 1024)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    db.session.commit()
    return ws


def _post(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), headers=json_headers)


@pytest.fixture
def public_dns():
    """Resolve every host to a public address, no real DNS lookups in tests"""
    with patch(
        "mergin_plus.webhooks.delivery.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 443))],
    ):
        yield


def test_audit_log(client):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    login(client, "owner", "Owner123!")
    ws_id = _post(client, "/v1/workspace", {"name": "audited"}).json["id"]
    ws = db.session.get(Workspace, ws_id)
    ws.set_role(reader.id, WorkspaceRole.READER)
    db.session.commit()
    client.patch(
        f"/v2/workspaces/{ws_id}/members/{reader.id}",
        data=json.dumps({"role": "writer"}),
        headers=json_headers,
    )

    resp = client.get(f"/v2/workspaces/{ws_id}/audit")
    assert resp.status_code == 200
    types = [e["event_type"] for e in resp.json["items"]]
    assert types[:2] == ["workspace.member.updated", "workspace.created"]
    updated = resp.json["items"][0]
    assert updated["actor_email"] == "owner@mergin.com"
    assert updated["metadata"]["new_role"] == "writer"
    resp = client.get(f"/v2/workspaces/{ws_id}/audit?event_type=workspace.member")
    assert resp.json["count"] == 1
    assert client.get(f"/v2/workspaces/{ws_id}/audit?since=bad").status_code == 400

    # only admins of the workspace, server log only for superusers
    login(client, "reader", "Reader123!")
    assert client.get(f"/v2/workspaces/{ws_id}/audit").status_code == 403
    assert client.get("/app/admin/audit").status_code == 403
    login(client, "mergin", "ilovemergin")
    resp = client.get("/app/admin/audit?event_type=user.login")
    assert resp.status_code == 200
    assert resp.json["count"] >= 3
    assert {e["event_type"] for e in resp.json["items"]} == {"user.login.succeeded"}
    assert (
        client.get(f"/app/admin/audit?workspace_id={ws_id}").json["count"]
        == AuditLog.query.filter_by(target_workspace_id=ws_id).count()
    )


@patch("mergin_plus.webhooks.delivery.deliver_webhook.delay")
def test_webhooks_api_and_dispatch(delay_mock, client, public_dns):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("hooks", owner)
    url = f"/v2/workspaces/{ws.id}/webhooks"
    login(client, "owner", "Owner123!")

    assert _post(client, url, {"url": "ftp://example.com"}).status_code == 400
    resp = _post(
        client, url, {"url": "https://example.com/hook", "events": ["project"]}
    )
    assert resp.status_code == 201
    assert len(resp.json["secret"]) == 64
    hook_id = resp.json["id"]
    assert "secret" not in client.get(url).json[0]

    # project events of the workspace are dispatched, others are filtered by prefix
    project = create_project("p", ws, owner)
    calls = [c.args for c in delay_mock.call_args_list]
    assert any(
        c[0] == hook_id and c[1] == "project.created" and c[2]["workspace_id"] == ws.id
        for c in calls
    )
    delay_mock.reset_mock()
    client.patch(
        f"/v1/workspace/{ws.id}",
        data=json.dumps({"description": "x"}),
        headers=json_headers,
    )
    assert not delay_mock.called

    resp = client.patch(
        f"{url}/{hook_id}",
        data=json.dumps({"active": False, "regenerate_secret": True}),
        headers=json_headers,
    )
    assert resp.status_code == 200
    assert resp.json["active"] is False
    assert "secret" in resp.json
    create_project("p2", ws, owner)
    assert not delay_mock.called
    assert client.delete(f"{url}/{hook_id}").status_code == 204
    assert client.delete(f"{url}/{hook_id}").status_code == 404

    # other users can not manage webhooks
    add_user("other", "Other1234!")
    login(client, "other", "Other1234!")
    assert client.get(url).status_code == 403


def test_webhook_delivery(app, public_dns):
    owner = add_user("owner", "Owner123!")
    ws = _workspace("hooks", owner)
    hook = Webhook(ws.id, "https://example.com/hook")
    db.session.add(hook)
    db.session.commit()

    ok = MagicMock(status_code=200, text="")
    with patch("mergin_plus.webhooks.delivery.requests.post", return_value=ok) as post:
        deliver_webhook.apply(
            args=(hook.id, "project.created", {"event": "project.created"})
        )
    body = post.call_args.kwargs["data"]
    headers = post.call_args.kwargs["headers"]
    assert headers["X-Webhook-Event"] == "project.created"
    expected = (
        "sha256=" + hmac.new(hook.secret.encode(), body, hashlib.sha256).hexdigest()
    )
    assert headers["X-Webhook-Signature"] == expected == sign(hook.secret, body)
    assert post.call_args.kwargs["allow_redirects"] is False
    db.session.refresh(hook)
    assert hook.last_status == 200 and hook.failures == 0

    # client errors are recorded, webhook is disabled after too many failures
    current_app.config["WEBHOOKS_MAX_FAILURES"] = 2
    try:
        bad = MagicMock(status_code=404, text="not found")
        with patch("mergin_plus.webhooks.delivery.requests.post", return_value=bad):
            for _ in range(2):
                deliver_webhook.apply(args=(hook.id, "x", {}))
        db.session.refresh(hook)
        assert hook.failures == 2 and hook.active is False
        assert hook.last_error == "not found"
    finally:
        current_app.config["WEBHOOKS_MAX_FAILURES"] = 20

    # network errors are retried
    hook.active = True
    hook.failures = 0
    db.session.commit()
    with patch(
        "mergin_plus.webhooks.delivery.requests.post",
        side_effect=requests.ConnectionError("down"),
    ) as post, patch.object(
        deliver_webhook, "retry", side_effect=RuntimeError("retry")
    ):
        result = deliver_webhook.apply(args=(hook.id, "x", {}))
    assert isinstance(result.result, RuntimeError)


def test_webhook_url_validation(app):
    with patch(
        "mergin_plus.webhooks.delivery.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 80))],
    ):
        with pytest.raises(WebhookUrlError):
            validate_url("http://localhost/hook")
        current_app.config["WEBHOOKS_ALLOW_PRIVATE_URLS"] = True
        try:
            validate_url("http://localhost/hook")
        finally:
            current_app.config["WEBHOOKS_ALLOW_PRIVATE_URLS"] = False
    with pytest.raises(WebhookUrlError):
        validate_url("javascript:alert(1)")


def test_branding_config(client):
    current_app.config["INSTANCE_NAME"] = "Acme maps"
    try:
        resp = client.get("/config")
        assert resp.json["instance_name"] == "Acme maps"
        assert "dashboard_logo_url" in resp.json
    finally:
        current_app.config["INSTANCE_NAME"] = ""
