# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB, UUID

from mergin.app import db


class MapOverview(db.Model):
    """Web map configuration of the latest processed version of a project"""

    __tablename__ = "map_overview"

    project_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("project.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version = db.Column(db.Integer, nullable=False)
    # QGIS project file (relative project path) and directory with data prepared for QGIS Server
    qgis_file = db.Column(db.String, nullable=True)
    data_dir = db.Column(db.String, nullable=True)
    config = db.Column(JSONB, nullable=True)
    # processing error of the last version, map of previous version is kept
    error = db.Column(db.String, nullable=True)
    updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    project = db.relationship("Project")
