# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Entry point of the server with enterprise features.

It loads the unmodified Community Edition entry point (server/application.py) and plugs the add-on into it.
Use it instead of the CE one:

    gunicorn mergin_plus.wsgi:application
    celery -A mergin_plus.wsgi.celery worker / beat
    FLASK_APP=mergin_plus.wsgi flask db upgrade heads
"""

from celery.schedules import crontab

from application import application, celery  # CE entry point
from . import register
from .audit.tasks import remove_old_audit_events
from .maps import tasks as maps_tasks  # noqa: F401 (registers map overview task)
from .webhooks import delivery  # noqa: F401 (registers webhook delivery task)
from .sso.tasks import remove_expired_sso_grants
from .transfer.tasks import remove_expired_transfers
from .workspace.tasks import remove_closed_workspaces, remove_expired_invitations

register(application)


@celery.on_after_finalize.connect
def setup_plus_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=4, minute=0),
        remove_closed_workspaces,
        name="remove closed workspaces",
    )
    sender.add_periodic_task(
        crontab(hour=4, minute=30),
        remove_expired_invitations,
        name="remove expired workspace invitations",
    )
    sender.add_periodic_task(
        crontab(hour=4, minute=45),
        remove_expired_transfers,
        name="remove expired project transfers",
    )
    sender.add_periodic_task(
        crontab(hour=5, minute=0),
        remove_old_audit_events,
        name="remove old audit events",
    )
    sender.add_periodic_task(
        crontab(minute=30),
        remove_expired_sso_grants,
        name="remove expired sso grants",
    )
