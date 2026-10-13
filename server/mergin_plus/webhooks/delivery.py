# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Signed delivery of webhook payloads.

Every request carries:
- X-Webhook-Event: event type (e.g. "project.version.created")
- X-Webhook-Delivery: unique delivery id
- X-Webhook-Signature: "sha256=" + HMAC-SHA256 of the raw body with the webhook secret

Unless WEBHOOKS_ALLOW_PRIVATE_URLS is set, URLs resolving to private, loopback, link-local or reserved
addresses are refused, so workspace admins can not use webhooks to reach internal services:
- the URL is parsed by urllib3, the library which sends the request (no parser differentials),
  URLs with credentials, backslashes or control characters are refused;
- the host name is resolved once and the connection is made to the checked address
  (keeping Host header, TLS server name and certificate verification), so DNS rebinding does not help;
- no proxies, no redirects, and only the response status is stored.
"""

import hashlib
import hmac
import ipaddress
import json
import re
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

import urllib3
from flask import current_app
from urllib3.util import parse_url

from mergin.app import db
from mergin.celery import celery
from .models import Webhook

FORBIDDEN_URL_CHARS = re.compile(r"[\\\s\x00-\x1f\x7f]")


class WebhookUrlError(ValueError):
    pass


@dataclass
class DeliveryResponse:
    status_code: int


def _target(url: str) -> Tuple[str, str, int, str, str]:
    """Validate url, return (scheme, host, port, request path, address to connect to)"""
    if not url or FORBIDDEN_URL_CHARS.search(url):
        raise WebhookUrlError("Webhook URL contains invalid characters")
    try:
        parsed = parse_url(url)
    except Exception:
        raise WebhookUrlError("Invalid webhook URL")
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise WebhookUrlError("Webhook URL must be an http(s) URL")
    if parsed.auth:
        raise WebhookUrlError("Webhook URL can not contain credentials")
    host = parsed.host.strip("[]")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise WebhookUrlError(f"Can not resolve host {host}")
    addresses = [info[4][0] for info in infos]
    if not current_app.config["WEBHOOKS_ALLOW_PRIVATE_URLS"]:
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global or ip.is_multicast:
                raise WebhookUrlError("Webhook URL must point to a public address")
    return parsed.scheme, host, port, parsed.request_uri or "/", addresses[0]


def validate_url(url: str) -> None:
    """Raise WebhookUrlError if url can not be used as webhook target"""
    _target(url)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _http_post(
    scheme: str, host: str, port: int, path: str, address: str, body: bytes, headers
):
    """POST to the already validated address"""
    timeout = urllib3.Timeout(total=current_app.config["WEBHOOKS_TIMEOUT"])
    host_header = host if port in (80, 443) else f"{host}:{port}"
    if ":" in host and not host.startswith("["):
        host_header = f"[{host}]" if port in (80, 443) else f"[{host}]:{port}"
    if scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            address,
            port,
            server_hostname=host,
            assert_hostname=host,
            cert_reqs="CERT_REQUIRED",
            timeout=timeout,
            retries=False,
        )
    else:
        pool = urllib3.HTTPConnectionPool(address, port, timeout=timeout, retries=False)
    try:
        resp = pool.urlopen(
            "POST",
            path,
            body=body,
            headers={**headers, "Host": host_header},
            redirect=False,
            preload_content=False,
        )
        resp.release_conn()
        return DeliveryResponse(status_code=resp.status)
    finally:
        pool.close()


def send(webhook: Webhook, event_type: str, payload: dict) -> DeliveryResponse:
    scheme, host, port, path, address = _target(webhook.url)
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "merginmaps-server-webhooks",
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery": str(uuid.uuid4()),
        "X-Webhook-Signature": sign(webhook.secret, body),
    }
    return _http_post(scheme, host, port, path, address, body, headers)


def _record(webhook: Webhook, status=None, error=None) -> None:
    webhook.last_delivery_at = datetime.utcnow()
    webhook.last_status = status
    webhook.last_error = error[:200] if error else None
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
    except (urllib3.exceptions.HTTPError, OSError) as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * 2**self.request.retries)
        _record(webhook, error=f"Connection failed: {type(e).__name__}")
        return
    if resp.status_code >= 500 and self.request.retries < self.max_retries:
        raise self.retry(countdown=60 * 2**self.request.retries)
    ok = 200 <= resp.status_code < 300
    # response body is never stored: it could expose content of the target service
    _record(
        webhook,
        status=resp.status_code,
        error=None if ok else f"HTTP {resp.status_code}",
    )
