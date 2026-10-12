# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime

from mergin.app import db
from mergin.celery import celery
from .models import SsoGrant


@celery.task
def remove_expired_sso_grants():
    SsoGrant.query.filter(SsoGrant.expires_at < datetime.utcnow()).delete()
    db.session.commit()
