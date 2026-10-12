# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from sqlalchemy.dialects.postgresql import JSONB, UUID

from mergin.app import db


class AuditLog(db.Model):
    """Stored audit event (see mergin.audit), written by AuditSink"""

    __tablename__ = "audit_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String, nullable=False, index=True)
    happened_at = db.Column(db.DateTime, nullable=False, index=True)
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    actor_email = db.Column(db.String, nullable=True)
    actor_ip = db.Column(db.String, nullable=True)
    actor_ua = db.Column(db.String, nullable=True)
    actor_device = db.Column(db.String, nullable=True)
    target_user_id = db.Column(db.Integer, nullable=True)
    target_project_id = db.Column(UUID(as_uuid=True), nullable=True, index=True)
    target_workspace_id = db.Column(db.Integer, nullable=True, index=True)
    # "metadata" is reserved by SQLAlchemy declarative classes
    meta = db.Column("metadata", JSONB, nullable=False, server_default="{}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "happened_at": self.happened_at.isoformat() + "Z",
            "actor_id": self.actor_id,
            "actor_email": self.actor_email,
            "actor_ip": self.actor_ip,
            "actor_ua": self.actor_ua,
            "actor_device": self.actor_device,
            "target_user_id": self.target_user_id,
            "target_project_id": (
                str(self.target_project_id) if self.target_project_id else None
            ),
            "target_workspace_id": self.target_workspace_id,
            "metadata": self.meta,
        }
