# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from mergin.app import db
from mergin.celery import celery
from mergin.sync.models import Project
from .overview import build_overview, remove_overview


@celery.task(ignore_result=True)
def build_map_overview(project_id: str, version: int):
    project = db.session.get(Project, project_id)
    if not project or project.removed_at or not project.storage_params:
        remove_overview(project_id)
        return
    # a newer version was pushed meanwhile, its own task will process it
    if project.latest_version != version:
        return
    build_overview(project)
