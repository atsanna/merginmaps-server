# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import uuid
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.dialects.postgresql import UUID

from mergin.app import db


class ProjectTransfer(db.Model):
    """Pending request to move a project to another workspace"""

    __tablename__ = "project_transfer"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    from_workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    project = db.relationship("Project")
    from_workspace = db.relationship("Workspace", foreign_keys=[from_workspace_id])
    to_workspace = db.relationship("Workspace", foreign_keys=[to_workspace_id])
    requester = db.relationship("User")

    def __init__(self, project, to_workspace, requester):
        self.id = uuid.uuid4()
        self.project = project
        self.project_id = project.id
        self.from_workspace_id = project.workspace_id
        self.to_workspace_id = to_workspace.id
        self.requested_by = requester.id
        self.created = datetime.utcnow()
        self.expires_at = self.created + timedelta(
            days=current_app.config["PROJECT_TRANSFER_EXPIRATION"]
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at < datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "project_id": str(self.project_id),
            "project_name": self.project.name,
            "from_workspace_id": self.from_workspace_id,
            "from_workspace": self.from_workspace.name,
            "to_workspace_id": self.to_workspace_id,
            "to_workspace": self.to_workspace.name,
            "requested_by": self.requester.username if self.requester else None,
            "created": self.created.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z",
            "expired": self.is_expired,
        }
