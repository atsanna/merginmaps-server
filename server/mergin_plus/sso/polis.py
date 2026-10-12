# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Minimal client of Ory Polis (formerly BoxyHQ SAML Jackson), an open source SAML/OIDC to OAuth 2.0 bridge.

The server is an OAuth 2.0 client of Polis using the "dummy" client with tenant and product,
so SSO connections are configured only in Polis (tenant = e-mail domain, product = SSO_SERVER_PRODUCT_ID).
"""

from typing import Optional
from urllib.parse import urlencode

import requests
from flask import current_app

TIMEOUT = 10


class PolisError(Exception):
    pass


def _cfg(key):
    return current_app.config[key]


def _api(path: str) -> str:
    return f"{_cfg('SSO_SERVER_API_URL')}{path}"


def _api_headers() -> dict:
    return {"Authorization": f"Api-Key {_cfg('SSO_SERVER_API_KEY')}"}


def connections(tenant: Optional[str] = None) -> list:
    """SSO connections of tenant (or of the whole product)"""
    params = {"product": _cfg("SSO_SERVER_PRODUCT_ID")}
    path = "/api/v1/sso/product"
    if tenant:
        params["tenant"] = tenant
        path = "/api/v1/sso"
    try:
        resp = requests.get(
            _api(path), params=params, headers=_api_headers(), timeout=TIMEOUT
        )
    except requests.RequestException as e:
        raise PolisError(str(e))
    if resp.status_code == 404:
        return []
    if not resp.ok:
        raise PolisError(f"Polis API error {resp.status_code}")
    data = resp.json()
    # paginated responses wrap the list
    if isinstance(data, dict):
        data = data.get("data", [])
    return data


def authorize_url(tenant: str, redirect_uri: str, state: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": "dummy",
        "tenant": tenant,
        "product": _cfg("SSO_SERVER_PRODUCT_ID"),
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{_cfg('SSO_SERVER_URL')}/api/oauth/authorize?{urlencode(params)}"


def exchange_code(tenant: str, code: str, redirect_uri: str, verifier: str) -> str:
    """Return access token for authorization code"""
    data = {
        "grant_type": "authorization_code",
        # with the dummy client, tenant and product are passed url encoded as client_id
        "client_id": urlencode(
            {"tenant": tenant, "product": _cfg("SSO_SERVER_PRODUCT_ID")}
        ),
        "client_secret": "dummy",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    try:
        resp = requests.post(_api("/api/oauth/token"), data=data, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise PolisError(str(e))
    if not resp.ok or "access_token" not in resp.json():
        raise PolisError(f"Token exchange failed ({resp.status_code})")
    return resp.json()["access_token"]


def userinfo(access_token: str) -> dict:
    try:
        resp = requests.get(
            _api("/api/oauth/userinfo"),
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise PolisError(str(e))
    if not resp.ok:
        raise PolisError(f"Userinfo failed ({resp.status_code})")
    return resp.json()
