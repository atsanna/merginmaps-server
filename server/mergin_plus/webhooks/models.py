# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import secrets
from datetime import datetime

from sqlalchemy.dialects.postgresql import ARRAY

from mergin.app import db


class Webhook(db.Model):
    """Workspace webhook: audit events of the workspace are POSTed to url, signed with secret"""

    __tablename__ = "webhook"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url = db.Column(db.String, nullable=False)
    secret = db.Column(db.String, nullable=False)
    # event type prefixes, e.g. "project.version" ; empty list means all events
    events = db.Column(ARRAY(db.String), nullable=False, server_default="{}")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    last_delivery_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.Integer, nullable=True)
    last_error = db.Column(db.String, nullable=True)
    # consecutive failed deliveries
    failures = db.Column(db.Integer, nullable=False, default=0)

    def __init__(self, workspace_id: int, url: str, events=None, created_by=None):
        self.workspace_id = workspace_id
        self.url = url
        self.events = events or []
        self.active = True
        self.created = datetime.utcnow()
        self.created_by = created_by
        self.failures = 0
        self.secret = secrets.token_hex(32)

    def matches(self, event_type: str) -> bool:
        return not self.events or any(
            event_type == e or event_type.startswith(e + ".") for e in self.events
        )

    def to_dict(self, with_secret=False) -> dict:
        data = {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "url": self.url,
            "events": self.events,
            "active": self.active,
            "created": self.created.isoformat() + "Z",
            "last_delivery_at": (
                self.last_delivery_at.isoformat() + "Z"
                if self.last_delivery_at
                else None
            ),
            "last_status": self.last_status,
            "last_error": self.last_error,
            "failures": self.failures,
        }
        if with_secret:
            data["secret"] = self.secret
        return data
