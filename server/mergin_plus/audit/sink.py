# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Audit sink replacing CE NullSink: events are stored and forwarded to workspace webhooks.

Events can be emitted from SQLAlchemy mapper events during a flush, so the session is not used here:
the event is written with its own connection and transaction.
"""

import logging

from flask import current_app
from sqlalchemy import select

from mergin.app import db
from mergin.audit.events import AuditEvent
from mergin.audit.sinks import AbstractSink
from ..webhooks.models import Webhook
from .models import AuditLog


def event_payload(event: AuditEvent) -> dict:
    return {
        "event": event.event_type,
        "happened_at": event.happened_at.isoformat() + "Z",
        "workspace_id": event.target_workspace_id,
        "project_id": str(event.target_project_id) if event.target_project_id else None,
        "user_id": event.target_user_id,
        "actor": {"id": event.actor_id, "email": event.actor_email},
        "data": event.metadata,
    }


class AuditSink(AbstractSink):
    def write(self, event: AuditEvent) -> None:
        from ..webhooks.delivery import deliver_webhook

        hooks = []
        with db.engine.begin() as conn:
            if current_app.config["AUDIT_LOG_ENABLED"]:
                conn.execute(
                    AuditLog.__table__.insert().values(
                        event_type=event.event_type,
                        happened_at=event.happened_at,
                        actor_id=event.actor_id,
                        actor_email=event.actor_email,
                        actor_ip=event.actor_ip,
                        actor_ua=event.actor_ua,
                        actor_device=event.actor_device,
                        target_user_id=event.target_user_id,
                        target_project_id=event.target_project_id,
                        target_workspace_id=event.target_workspace_id,
                        metadata=event.metadata,
                    )
                )
            if event.target_workspace_id:
                hooks = conn.execute(
                    select(Webhook.id, Webhook.events).where(
                        Webhook.workspace_id == event.target_workspace_id,
                        Webhook.active.is_(True),
                    )
                ).all()
        for hook_id, events in hooks:
            if not events or any(
                event.event_type == e or event.event_type.startswith(e + ".")
                for e in events
            ):
                try:
                    deliver_webhook.delay(
                        hook_id, event.event_type, event_payload(event)
                    )
                except Exception:
                    logging.warning(
                        "Failed to queue webhook %s", hook_id, exc_info=True
                    )
