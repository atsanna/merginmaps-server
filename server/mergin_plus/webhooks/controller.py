# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Workspace webhooks management (workspace admins)"""

from datetime import datetime

import requests
from flask import abort, current_app, request
from flask_login import current_user

from mergin.app import db
from mergin.auth import auth_required
from .delivery import WebhookUrlError, send, validate_url
from .models import Webhook


def _workspace(id: int):
    ws = current_app.ws_handler.get(id)
    if not ws or not ws.is_active:
        abort(404, "Workspace not found")
    if not ws.user_has_permissions(current_user, "admin"):
        abort(403, "You do not have permissions for this workspace")
    return ws


def _webhook(ws, webhook_id: int) -> Webhook:
    webhook = Webhook.query.filter_by(id=webhook_id, workspace_id=ws.id).first()
    if not webhook:
        abort(404, "Webhook not found")
    return webhook


def _check_url(url: str) -> None:
    try:
        validate_url(url)
    except WebhookUrlError as e:
        abort(400, str(e))


def _events(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(e, str) for e in value):
        abort(400, "events must be a list of event types")
    return [e.strip() for e in value if e.strip()]


@auth_required
def list_webhooks(id: int):
    ws = _workspace(id)
    hooks = Webhook.query.filter_by(workspace_id=ws.id).order_by(Webhook.id).all()
    return [h.to_dict() for h in hooks], 200


@auth_required
def create_webhook(id: int):
    """Create webhook, its secret is returned only here"""
    ws = _workspace(id)
    url = (request.json.get("url") or "").strip()
    _check_url(url)
    webhook = Webhook(ws.id, url, _events(request.json.get("events")), current_user.id)
    db.session.add(webhook)
    db.session.commit()
    return webhook.to_dict(with_secret=True), 201


@auth_required
def update_webhook(id: int, webhook_id: int):
    ws = _workspace(id)
    webhook = _webhook(ws, webhook_id)
    data = request.json
    if "url" in data:
        url = (data["url"] or "").strip()
        _check_url(url)
        webhook.url = url
    if "events" in data:
        webhook.events = _events(data["events"])
    if "active" in data:
        webhook.active = bool(data["active"])
        if webhook.active:
            webhook.failures = 0
    if data.get("regenerate_secret"):
        webhook.secret = Webhook(ws.id, webhook.url).secret
    db.session.commit()
    return webhook.to_dict(with_secret=bool(data.get("regenerate_secret"))), 200


@auth_required
def delete_webhook(id: int, webhook_id: int):
    ws = _workspace(id)
    db.session.delete(_webhook(ws, webhook_id))
    db.session.commit()
    return "", 204


@auth_required
def ping_webhook(id: int, webhook_id: int):
    """Send a test "ping" event synchronously and report the result"""
    ws = _workspace(id)
    webhook = _webhook(ws, webhook_id)
    payload = {
        "event": "ping",
        "happened_at": datetime.utcnow().isoformat() + "Z",
        "workspace_id": ws.id,
        "data": {"webhook_id": webhook.id},
    }
    try:
        resp = send(webhook, "ping", payload)
    except WebhookUrlError as e:
        return {"ok": False, "status": None, "error": str(e)}, 200
    except requests.RequestException as e:
        return {"ok": False, "status": None, "error": str(e)}, 200
    return {"ok": 200 <= resp.status_code < 300, "status": resp.status_code}, 200
