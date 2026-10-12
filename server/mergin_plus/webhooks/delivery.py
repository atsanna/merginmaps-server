# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Signed delivery of webhook payloads.

Every request carries:
- X-Webhook-Event: event type (e.g. "project.version.created")
- X-Webhook-Delivery: unique delivery id
- X-Webhook-Signature: "sha256=" + HMAC-SHA256 of the raw body with the webhook secret
Unless WEBHOOKS_ALLOW_PRIVATE_URLS is set, URLs resolving to private, loopback, link-local or reserved
addresses are refused, so workspace admins can not use webhooks to reach internal services.
"""

import hashlib
import hmac
import ipaddress
import json
import socket
import uuid
from datetime import datetime
from urllib.parse import urlparse

import requests
from flask import current_app

from mergin.app import db
from mergin.celery import celery
from .models import Webhook


class WebhookUrlError(ValueError):
    pass


def validate_url(url: str) -> None:
    """Raise WebhookUrlError if url can not be used as webhook target"""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebhookUrlError("Webhook URL must be an http(s) URL")
    if current_app.config["WEBHOOKS_ALLOW_PRIVATE_URLS"]:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror:
        raise WebhookUrlError(f"Can not resolve host {parsed.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise WebhookUrlError("Webhook URL must point to a public address")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def send(webhook: Webhook, event_type: str, payload: dict) -> requests.Response:
    validate_url(webhook.url)
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "merginmaps-server-webhooks",
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery": str(uuid.uuid4()),
        "X-Webhook-Signature": sign(webhook.secret, body),
    }
    return requests.post(
        webhook.url,
        data=body,
        headers=headers,
        timeout=current_app.config["WEBHOOKS_TIMEOUT"],
        allow_redirects=False,
    )


def _record(webhook: Webhook, status=None, error=None) -> None:
    webhook.last_delivery_at = datetime.utcnow()
    webhook.last_status = status
    webhook.last_error = error[:500] if error else None
    if error:
        webhook.failures += 1
        if webhook.failures >= current_app.config["WEBHOOKS_MAX_FAILURES"]:
            webhook.active = False
    else:
        webhook.failures = 0
    db.session.commit()


@celery.task(bind=True, max_retries=3, ignore_result=True)
def deliver_webhook(self, webhook_id: int, event_type: str, payload: dict):
    """Deliver payload, retried with growing delay on network errors and 5xx responses"""
    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or not webhook.active:
        return
    try:
        resp = send(webhook, event_type, payload)
    except WebhookUrlError as e:
        _record(webhook, error=str(e))
        return
    except requests.RequestException as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * 2**self.request.retries)
        _record(webhook, error=str(e))
        return
    if resp.status_code >= 500 and self.request.retries < self.max_retries:
        raise self.retry(countdown=60 * 2**self.request.retries)
    ok = 200 <= resp.status_code < 300
    _record(webhook, status=resp.status_code, error=None if ok else resp.text or "")
