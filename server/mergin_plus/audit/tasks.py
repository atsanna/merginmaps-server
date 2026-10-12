# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime, timedelta

from flask import current_app

from mergin.app import db
from mergin.celery import celery
from .models import AuditLog


@celery.task
def remove_old_audit_events():
    """Remove audit events older than AUDIT_LOG_RETENTION days"""
    cutoff = datetime.utcnow() - timedelta(
        days=current_app.config["AUDIT_LOG_RETENTION"]
    )
    AuditLog.query.filter(AuditLog.happened_at < cutoff).delete()
    db.session.commit()
