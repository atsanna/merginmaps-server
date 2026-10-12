# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import logging

from flask import current_app

from mergin.sync.models import project_deleted, project_version_created


def on_version_created(version, **kwargs):
    if not current_app.config["MAPS_ENABLED"]:
        return
    from .tasks import build_map_overview

    try:
        build_map_overview.delay(str(version.project_id), version.name)
    except Exception:
        logging.warning("Failed to queue map overview", exc_info=True)


def on_project_deleted(project, **kwargs):
    from .overview import remove_overview

    remove_overview(project.id)


def register_listeners():
    project_version_created.connect(on_version_created)
    project_deleted.connect(on_project_deleted)
