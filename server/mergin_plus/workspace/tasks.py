# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from datetime import datetime, timedelta

from flask import current_app

from mergin.celery import celery
from .models import Workspace


@celery.task
def remove_closed_workspaces():
    """Permanently remove workspaces closed longer than WORKSPACE_EXPIRATION days"""
    cutoff = datetime.utcnow() - timedelta(
        days=current_app.config["WORKSPACE_EXPIRATION"]
    )
    workspaces = Workspace.query.filter(
        Workspace.removed_at < cutoff, Workspace.deleted.is_(False)
    ).all()
    for ws in workspaces:
        logging.info(f"Removing closed workspace {ws.name} (id {ws.id})")
        ws.purge()
