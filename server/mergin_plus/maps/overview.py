# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Preparation of project versions for the web map ("overviews").

For every new version with a QGIS project, the files of the version are linked (or copied) into
OVERVIEW_DATA/<project id>/v<version>, where QGIS Server can read them, and the map configuration is parsed.
Older prepared versions are removed afterwards.
"""

import logging
import os
import shutil
from datetime import datetime

from flask import current_app

from mergin.app import db
from mergin.sync.models import Project, ProjectVersion
from .models import MapOverview
from .qgis_project import find_qgis_file, parse_project, sanitize_project


def project_overview_dir(project_id) -> str:
    return os.path.join(current_app.config["OVERVIEW_DATA"], str(project_id))


def _link(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _materialize(project: Project, target: str) -> list:
    """Place latest files of project into target directory, return their paths"""
    paths = []
    for f in project.files:
        src = os.path.join(project.storage.project_dir, f.location)
        if not os.path.exists(src) and f.diff:
            # full geopackage of this version needs to be rebuilt from diffs
            project.storage.restore_versioned_file(f.path, project.latest_version)
        if not os.path.exists(src):
            logging.warning(f"Missing file {f.path} of project {project.id}")
            continue
        dst = os.path.normpath(os.path.join(target, f.path))
        if not dst.startswith(os.path.abspath(target) + os.sep):
            continue
        _link(src, dst)
        paths.append(f.path)
    return paths


def build_overview(project: Project) -> MapOverview:
    """Prepare latest project version for web map, commit result"""
    overview = db.session.get(MapOverview, project.id) or MapOverview(
        project_id=project.id, version=0
    )
    version = project.latest_version
    qgis_file = find_qgis_file([f.path for f in project.files])
    base = project_overview_dir(project.id)
    target = os.path.join(base, ProjectVersion.to_v_name(version))
    try:
        if not qgis_file:
            raise ValueError("Project has no QGIS project file")
        shutil.rmtree(target, ignore_errors=True)
        paths = _materialize(project, target)
        qgis_path = os.path.join(target, qgis_file)
        # configuration is read from the original, layers without project data are marked not packaged
        config = parse_project(qgis_path, paths)
        sanitize_project(qgis_path, paths)
    except Exception as e:  # keep previous map when processing fails
        logging.warning(f"Map overview of project {project.id} failed: {e}")
        shutil.rmtree(target, ignore_errors=True)
        overview.error = str(e)[:500]
        overview.updated = datetime.utcnow()
        db.session.add(overview)
        db.session.commit()
        return overview

    overview.version = version
    overview.qgis_file = qgis_file
    overview.data_dir = target
    overview.config = config
    overview.error = None
    overview.updated = datetime.utcnow()
    db.session.add(overview)
    db.session.commit()
    # remove previously prepared versions
    for name in os.listdir(base):
        if os.path.join(base, name) != target:
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)
    return overview


def remove_overview(project_id) -> None:
    shutil.rmtree(project_overview_dir(project_id), ignore_errors=True)
