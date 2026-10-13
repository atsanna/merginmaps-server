# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Single sign-on endpoints.

The server is an OAuth 2.0 authorization server (code flow with PKCE) for Mergin Maps clients,
and an OAuth 2.0 client of Ory Polis, which talks SAML / OIDC to the identity providers:

  client (QGIS plugin, mobile app)          server                         Polis / IdP
  GET /v2/sso/authorize (PKCE) ----------->  stores request, redirects -->  login at IdP
                                             GET /v2/sso/callback  <------  code
                                             code -> token -> userinfo, JIT user
  <------------- redirect_uri?code&state --  one-time authorization code
  POST /v2/sso/token (code_verifier) ----->  Mergin bearer token

The dashboard uses GET /v2/sso/login, the callback then signs the user in with a session cookie.
"""

import base64
import re
import hashlib
import secrets
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, urlparse

from flask import Blueprint, abort, current_app, jsonify, redirect, request, session
from flask_login import login_user
from sqlalchemy import func

from mergin.app import db
from mergin.audit import emit
from mergin.audit.listeners import request_context
from mergin.auth.app import generate_bearer_token, user_created
from mergin.auth.events import AuthEventType
from mergin.auth.models import LoginHistory, User
from . import polis
from .models import SsoGrant

bp = Blueprint("plus_sso", __name__)

REQUEST_TTL = 600  # seconds to complete login at identity provider
CODE_TTL = 120  # seconds to exchange authorization code


def _enabled():
    if not current_app.config["SSO_ENABLED"]:
        abort(404, "SSO is not enabled")


def _multi_tenant() -> bool:
    return current_app.config["SSO_TENANT_FLOW"] != "single"


def _tenant_for(email: Optional[str]) -> Optional[str]:
    if not _multi_tenant():
        return current_app.config["SSO_DEFAULT_TENANT"]
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower()


def _has_connection(tenant: str) -> bool:
    try:
        return bool(polis.connections(tenant))
    except polis.PolisError:
        abort(502, "SSO server is not available")


UNSAFE_URL_CHARS = re.compile(r"[\\\s\x00-\x1f\x7f]")


def _redirect_allowed(uri: str) -> bool:
    if not uri or UNSAFE_URL_CHARS.search(uri):
        return False
    target = urlparse(uri)
    if not target.scheme or not target.netloc or "@" in target.netloc:
        return False
    # no dot segments: browsers would resolve them outside the allowed path
    if any(part in (".", "..") for part in target.path.split("/")):
        return False
    path = target.path or "/"
    for allowed in current_app.config["SSO_ALLOWED_REDIRECT_URIS"]:
        a = urlparse(allowed.strip())
        allowed_path = a.path or "/"
        if (
            a.scheme == target.scheme
            and a.netloc == target.netloc
            and (
                path == allowed_path
                or path.startswith(allowed_path.rstrip("/") + "/")
                or allowed_path.endswith("/")
                and path.startswith(allowed_path)
            )
        ):
            return True
    return False


def _safe_next(value: Optional[str]) -> str:
    """Local path to go to after dashboard login, anything else falls back to /"""
    if not value or UNSAFE_URL_CHARS.search(value):
        return "/"
    parsed = urlparse(value)
    if (
        parsed.scheme
        or parsed.netloc
        or not value.startswith("/")
        or value.startswith("//")
    ):
        return "/"
    return value


def _callback_url() -> str:
    return f"{current_app.config['MERGIN_BASE_URL'].rstrip('/')}/v2/sso/callback"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _start_login(tenant: str, data: dict):
    verifier = secrets.token_urlsafe(48)
    state = SsoGrant.create(
        "state", {**data, "tenant": tenant, "verifier": verifier}, REQUEST_TTL
    )
    db.session.commit()
    return redirect(
        polis.authorize_url(tenant, _callback_url(), state, _pkce_challenge(verifier))
    )


def _provision_user(info: dict, tenant: str) -> User:
    email = (info.get("email") or "").strip().lower()
    if not email:
        abort(400, "Identity provider did not return e-mail")
    # tenant identity provider can only sign in users of its own domain
    if _multi_tenant() and _tenant_for(email) != tenant:
        abort(403, "E-mail domain does not match SSO connection")
    user = User.query.filter(func.lower(User.email) == email).first()
    if user:
        if not user.active:
            abort(403, "Account is not active")
        # an unverified e-mail could have been set by someone else on their own account
        if not user.verified_email:
            abort(
                409,
                "An account with this e-mail exists but the e-mail is not verified, "
                "please verify it first",
            )
        return user
    username = User.generate_username(email)
    db.session.info["audit_user_creation_source"] = "sso"
    user = User(username, email)  # no password, SSO account
    user.active = True
    user.verified_email = True
    user.first_name = info.get("firstName") or info.get("given_name")
    user.last_name = info.get("lastName") or info.get("family_name")
    db.session.add(user)
    db.session.commit()
    user_created.send(user, source="sso")
    return user


def _signed_in(user: User, method: str) -> None:
    LoginHistory.add_record(user.id, request)
    emit(
        AuthEventType.USER_LOGIN_SUCCEEDED,
        actor_id=user.id,
        actor_email=user.email,
        **request_context(),
        target_user_id=user.id,
        login_method=method,
    )


@bp.route("/v2/sso/config", methods=["GET"])
def sso_config():
    _enabled()
    if _multi_tenant():
        return jsonify({"tenant_flow_type": "multi"})
    return jsonify(
        {
            "tenant_flow_type": "single",
            "client_id": current_app.config["SSO_DEFAULT_TENANT"],
        }
    )


@bp.route("/v2/sso/connections", methods=["GET"])
def sso_connections():
    """OAuth client id to use for e-mail, 404 if its domain has no SSO connection"""
    _enabled()
    tenant = _tenant_for(request.args.get("email"))
    if not tenant or not _has_connection(tenant):
        abort(404, "SSO connection not found")
    return jsonify({"id": tenant})


@bp.route("/v2/sso/authorize", methods=["GET"])
def sso_authorize():
    """OAuth 2.0 authorization endpoint for clients (code flow with PKCE S256)"""
    _enabled()
    args = request.args
    if args.get("response_type") != "code":
        abort(400, "Unsupported response_type")
    redirect_uri = args.get("redirect_uri")
    if not _redirect_allowed(redirect_uri):
        abort(400, "redirect_uri is not allowed")
    if not args.get("code_challenge") or args.get("code_challenge_method") != "S256":
        abort(400, "PKCE with S256 is required")
    tenant = args.get("client_id") if _multi_tenant() else _tenant_for(None)
    if not tenant or not _has_connection(tenant):
        abort(400, "Unknown client_id")
    return _start_login(
        tenant,
        {
            "client": "oauth",
            "client_id": args.get("client_id"),
            "redirect_uri": redirect_uri,
            "client_state": args.get("state"),
            "challenge": args.get("code_challenge"),
        },
    )


@bp.route("/v2/sso/login", methods=["GET"])
def sso_login():
    """Dashboard sign in, user ends up with a session cookie"""
    _enabled()
    tenant = _tenant_for(request.args.get("email"))
    if not tenant or not _has_connection(tenant):
        abort(404, "SSO connection not found")
    # bind the login to this browser (no login CSRF with a callback URL started by someone else)
    nonce = secrets.token_urlsafe(16)
    session["plus_sso_nonce"] = nonce
    return _start_login(
        tenant,
        {
            "client": "dashboard",
            "next": _safe_next(request.args.get("next")),
            "nonce": nonce,
        },
    )


@bp.route("/v2/sso/callback", methods=["GET"])
def sso_callback():
    """Redirect target of Polis after the user signed in at the identity provider"""
    _enabled()
    data = SsoGrant.consume("state", request.args.get("state"))
    db.session.commit()
    if not data:
        abort(400, "Invalid or expired SSO login")
    if request.args.get("error") or not request.args.get("code"):
        if data["client"] == "oauth":
            return redirect(
                f"{data['redirect_uri']}?"
                + urlencode(
                    {"error": "access_denied", "state": data["client_state"] or ""}
                )
            )
        abort(401, request.args.get("error_description") or "SSO login failed")
    try:
        token = polis.exchange_code(
            data["tenant"], request.args["code"], _callback_url(), data["verifier"]
        )
        info = polis.userinfo(token)
    except polis.PolisError:
        abort(502, "SSO server error")
    if data["client"] == "dashboard" and not secrets.compare_digest(
        session.pop("plus_sso_nonce", ""), data.get("nonce", "-")
    ):
        abort(400, "SSO login was started in another browser")
    user = _provision_user(info, data["tenant"])

    if data["client"] == "dashboard":
        login_user(user)
        _signed_in(user, "sso")
        return redirect(_safe_next(data["next"]))

    code = SsoGrant.create(
        "code",
        {
            "user_id": user.id,
            "client_id": data["client_id"],
            "redirect_uri": data["redirect_uri"],
            "challenge": data["challenge"],
        },
        CODE_TTL,
    )
    db.session.commit()
    params = {"code": code}
    if data["client_state"]:
        params["state"] = data["client_state"]
    return redirect(f"{data['redirect_uri']}?{urlencode(params)}")


def _token_error(error: str, status=400):
    return jsonify({"error": error}), status


@bp.route("/v2/sso/token", methods=["POST"])
def sso_token():
    """OAuth 2.0 token endpoint: authorization code + PKCE verifier -> Mergin bearer token"""
    _enabled()
    form = request.form
    if form.get("grant_type") != "authorization_code":
        return _token_error("unsupported_grant_type")
    data = SsoGrant.consume("code", form.get("code"))
    db.session.commit()
    if not data:
        return _token_error("invalid_grant")
    verifier = form.get("code_verifier") or ""
    if (
        form.get("redirect_uri") != data["redirect_uri"]
        or (form.get("client_id") and form.get("client_id") != data["client_id"])
        or not secrets.compare_digest(_pkce_challenge(verifier), data["challenge"])
    ):
        return _token_error("invalid_grant")
    user = db.session.get(User, data["user_id"])
    if not user or not user.active:
        return _token_error("invalid_grant")
    expiration = current_app.config["SSO_SESSION_EXPIRATION"]
    token, expire = generate_bearer_token(current_app, user, expiration)
    _signed_in(user, "sso")
    resp = jsonify(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": int((expire - datetime.now(expire.tzinfo)).total_seconds()),
        }
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


def sso_connections_count() -> int:
    if not current_app.config["SSO_ENABLED"]:
        return 0
    try:
        return len(polis.connections())
    except polis.PolisError:
        return 0
