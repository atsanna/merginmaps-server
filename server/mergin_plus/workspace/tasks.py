# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from datetime import datetime, timedelta

from flask import current_app

from mergin.app import db
from mergin.celery import celery
from .models import Workspace, WorkspaceInvitation


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


@celery.task
def remove_expired_invitations():
    """Remove workspace invitations expired more than WORKSPACE_INVITATION_EXPIRATION days ago.
    Recently expired ones are kept, so admins can see and resend them.
    """
    cutoff = datetime.utcnow() - timedelta(
        days=current_app.config["WORKSPACE_INVITATION_EXPIRATION"]
    )
    WorkspaceInvitation.query.filter(WorkspaceInvitation.expires_at < cutoff).delete()
    db.session.commit()
