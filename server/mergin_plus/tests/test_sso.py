# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import base64
import hashlib
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from flask import current_app, g

from mergin.app import db
from mergin.auth.models import User
from mergin.tests.utils import add_user
from mergin_plus.sso import polis
from mergin_plus.sso.models import SsoGrant

REDIRECT = "http://localhost:10042/qgis"


def _challenge(verifier):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


@pytest.fixture
def sso(app):
    cfg = current_app.config
    old = {k: cfg[k] for k in ("SSO_ENABLED", "SSO_SERVER_URL", "SSO_SERVER_API_URL")}
    cfg.update(
        SSO_ENABLED=True,
        SSO_SERVER_URL="https://polis.example.com",
        SSO_SERVER_API_URL="http://polis:5225",
    )
    fake = MagicMock()
    fake.connections.side_effect = lambda tenant=None: (
        [{"clientID": "x"}] if tenant in (None, "acme.com") else []
    )
    fake.exchange_code.return_value = "polis-token"
    fake.userinfo.return_value = {
        "email": "Jane.Doe@acme.com",
        "firstName": "Jane",
        "lastName": "Doe",
    }
    with patch.multiple(
        polis,
        connections=fake.connections,
        exchange_code=fake.exchange_code,
        userinfo=fake.userinfo,
    ):
        yield fake
    cfg.update(old)


def _authorize(client, verifier="v" * 50, client_id="acme.com", redirect_uri=REDIRECT):
    return client.get(
        "/v2/sso/authorize",
        query_string={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": "client-state",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "login_hint": "jane.doe@acme.com",
        },
    )


def _polis_callback(client, resp, **extra):
    """Simulate identity provider sign in: follow Polis redirect back to our callback"""
    polis_url = urlparse(resp.headers["Location"])
    params = parse_qs(polis_url.query)
    assert polis_url.netloc == "polis.example.com"
    assert params["tenant"] == ["acme.com"]
    assert params["code_challenge_method"] == ["S256"]
    query = {"state": params["state"][0], "code": "polis-code", **extra}
    return client.get("/v2/sso/callback", query_string=query)


def test_disabled(client):
    assert client.get("/config").json["sso_enabled"] is False
    assert client.get("/v2/sso/config").status_code == 404


def test_discovery(client, sso):
    assert client.get("/config").json["sso_enabled"] is True
    assert client.get("/v2/sso/config").json == {"tenant_flow_type": "multi"}
    resp = client.get("/v2/sso/connections?email=someone@ACME.com")
    assert resp.json == {"id": "acme.com"}
    assert client.get("/v2/sso/connections?email=x@other.com").status_code == 404
    current_app.config.update(SSO_TENANT_FLOW="single", SSO_DEFAULT_TENANT="acme.com")
    try:
        assert client.get("/v2/sso/config").json == {
            "tenant_flow_type": "single",
            "client_id": "acme.com",
        }
    finally:
        current_app.config.update(SSO_TENANT_FLOW="multi", SSO_DEFAULT_TENANT="")


def test_client_pkce_flow(app, sso):
    client = app.test_client()
    verifier = "my-secret-verifier-" + "x" * 30
    # invalid requests
    assert _authorize(client, redirect_uri="https://evil.com/cb").status_code == 400
    assert _authorize(client, client_id="other.com").status_code == 400

    resp = _authorize(client, verifier)
    assert resp.status_code == 302
    resp = _polis_callback(client, resp)
    assert resp.status_code == 302
    target = urlparse(resp.headers["Location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == REDIRECT
    params = parse_qs(target.query)
    assert params["state"] == ["client-state"]
    code = params["code"][0]
    sso.exchange_code.assert_called_once()

    # user created just in time
    user = User.query.filter_by(email="jane.doe@acme.com").first()
    assert user and user.passwd is None and user.verified_email
    assert user.first_name == "Jane"

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": "acme.com",
        "code_verifier": "wrong",
    }
    # wrong verifier burns the code
    assert client.post("/v2/sso/token", data=form).status_code == 400
    assert (
        client.post(
            "/v2/sso/token", data={**form, "code_verifier": verifier}
        ).status_code
        == 400
    )

    resp = _polis_callback(client, _authorize(client, verifier))
    code = parse_qs(urlparse(resp.headers["Location"]).query)["code"][0]
    resp = client.post(
        "/v2/sso/token", data={**form, "code": code, "code_verifier": verifier}
    )
    assert resp.status_code == 200
    assert resp.json["token_type"] == "Bearer"
    assert resp.json["expires_in"] > 13 * 24 * 3600
    # token works as Mergin bearer token and code is one-time
    # (tests share one app context, drop user cached by flask-login from previous requests)
    g.pop("_login_user", None)
    api = app.test_client()
    resp_user = api.get(
        "/v1/user/profile",
        headers={"Authorization": f"Bearer {resp.json['access_token']}"},
    )
    assert resp_user.status_code == 200
    assert resp_user.json["email"] == "jane.doe@acme.com"
    resp = client.post(
        "/v2/sso/token", data={**form, "code": code, "code_verifier": verifier}
    )
    assert resp.json == {"error": "invalid_grant"}


def test_identity_provider_checks(app, sso):
    client = app.test_client()
    # e-mail of a different domain than the tenant connection is refused
    sso.userinfo.return_value = {"email": "intruder@other.com"}
    assert _polis_callback(client, _authorize(client)).status_code == 403
    # inactive existing user
    user = add_user("jane", "Jane12345!")
    user.email = "jane.doe@acme.com"
    user.active = False
    db.session.commit()
    sso.userinfo.return_value = {"email": "jane.doe@acme.com"}
    assert _polis_callback(client, _authorize(client)).status_code == 403
    # state is one-time and must exist
    assert client.get("/v2/sso/callback?state=nope&code=x").status_code == 400
    # identity provider error is passed to the client
    resp = _polis_callback(client, _authorize(client), error="access_denied")
    assert "error=access_denied" in resp.headers["Location"]


def test_dashboard_login(app, sso):
    existing = add_user("jdoe", "Jdoe12345!")
    existing.email = "jane.doe@acme.com"
    db.session.commit()
    client = app.test_client()
    resp = client.get("/v2/sso/login?email=jane.doe@acme.com&next=//evil.com")
    resp = _polis_callback(client, resp)
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/"
    # existing account is used, session cookie signs the user in
    assert User.query.filter_by(email="jane.doe@acme.com").count() == 1
    assert client.get("/v1/user/profile").json["username"] == "jdoe"
    assert SsoGrant.query.count() == 0


def test_polis_http_contract(app):
    current_app.config.update(
        SSO_SERVER_URL="https://polis.example.com",
        SSO_SERVER_API_URL="http://polis:5225",
        SSO_SERVER_API_KEY="key",
    )
    url = urlparse(polis.authorize_url("acme.com", "https://m/cb", "st", "ch"))
    q = parse_qs(url.query)
    assert url.path == "/api/oauth/authorize"
    assert q["client_id"] == ["dummy"] and q["product"] == ["mergin-maps-product"]

    with patch("mergin_plus.sso.polis.requests") as requests_mock:
        requests_mock.RequestException = Exception
        requests_mock.get.return_value = MagicMock(
            ok=True, status_code=200, json=lambda: [{"clientID": "a"}]
        )
        assert polis.connections("acme.com") == [{"clientID": "a"}]
        args, kwargs = requests_mock.get.call_args
        assert args[0] == "http://polis:5225/api/v1/sso"
        assert kwargs["headers"] == {"Authorization": "Api-Key key"}
        assert kwargs["params"] == {
            "product": "mergin-maps-product",
            "tenant": "acme.com",
        }

        requests_mock.post.return_value = MagicMock(
            ok=True, json=lambda: {"access_token": "t"}
        )
        assert polis.exchange_code("acme.com", "c", "https://m/cb", "v") == "t"
        data = requests_mock.post.call_args.kwargs["data"]
        assert data["client_id"] == "tenant=acme.com&product=mergin-maps-product"
        assert data["client_secret"] == "dummy" and data["code_verifier"] == "v"
