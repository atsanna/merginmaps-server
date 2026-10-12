# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Web map endpoints: map configuration and WMS proxy to QGIS Server with project permission checks"""

import os

import requests
from flask import Blueprint, Response, abort, current_app, jsonify, request

from mergin.app import db
from mergin.auth import auth_required
from mergin.sync.permissions import ProjectPermissions, require_project_by_uuid
from .models import MapOverview
from .tasks import build_map_overview

bp = Blueprint("plus_maps", __name__)

WMS_REQUESTS = {"getmap", "getlegendgraphic", "getfeatureinfo", "getcapabilities"}
# response headers passed from QGIS Server to the client
PASS_HEADERS = ("Content-Type", "Content-Disposition")


def _enabled():
    if not current_app.config["MAPS_ENABLED"]:
        abort(404, "Web maps are not enabled")


def _overview(project) -> MapOverview:
    overview = db.session.get(MapOverview, project.id)
    if not overview or not overview.config:
        abort(404, "Map config does not exist")
    return overview


@bp.route("/v2/projects/<uuid:id>/map", methods=["GET"])
@auth_required
def project_map(id):
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Read)
    overview = _overview(project)
    cfg = current_app.config
    return jsonify(
        {
            "project_id": str(project.id),
            "version": overview.version,
            "latest_version": project.latest_version,
            "qgis_file": overview.qgis_file,
            "error": overview.error,
            "updated": overview.updated.isoformat() + "Z",
            "wms_url": f"/v2/projects/{project.id}/map/wms",
            "basemap": {
                "url": cfg["MAPS_BASEMAP_URL"],
                "attribution": cfg["MAPS_BASEMAP_ATTRIBUTION"],
                "vector_style_url": cfg["VECTOR_TILES_STYLE_URL"] or None,
            },
            **overview.config,
        }
    )


@bp.route("/v2/projects/<uuid:id>/map/refresh", methods=["POST"])
@auth_required
def refresh_project_map(id):
    """Queue processing of the latest version (e.g. after a failed one)"""
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Upload)
    build_map_overview.delay(str(project.id), project.latest_version)
    return jsonify({"version": project.latest_version}), 202


@bp.route("/v2/projects/<uuid:id>/map/wms", methods=["GET"])
@auth_required
def project_map_wms(id):
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Read)
    overview = _overview(project)
    params = {k.upper(): v for k, v in request.args.items()}
    if params.get("REQUEST", "").lower() not in WMS_REQUESTS:
        abort(400, "Unsupported WMS request")
    params.pop("MAP", None)
    params["SERVICE"] = "WMS"
    map_path = os.path.join(overview.data_dir, overview.qgis_file)
    server_data = current_app.config["QGIS_SERVER_DATA"]
    if server_data:
        map_path = os.path.join(
            server_data,
            os.path.relpath(map_path, current_app.config["OVERVIEW_DATA"]),
        )
    params["MAP"] = map_path
    try:
        resp = requests.get(
            current_app.config["QGIS_SERVER_URL"],
            params=params,
            timeout=current_app.config["QGIS_SERVER_TIMEOUT"],
            stream=True,
        )
    except requests.RequestException:
        abort(502, "Map server is not available")
    headers = {h: resp.headers[h] for h in PASS_HEADERS if h in resp.headers}
    headers["Cache-Control"] = "private, max-age=300"
    return Response(
        resp.iter_content(chunk_size=64 * 1024),
        status=resp.status_code,
        headers=headers,
    )
