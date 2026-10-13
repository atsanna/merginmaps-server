# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Web map endpoints: map configuration and WMS proxy to QGIS Server with project permission checks"""

import os
import secrets
from typing import Optional

import requests
from flask import Blueprint, Response, abort, current_app, jsonify, request
from flask_login import current_user

from mergin.app import db
from mergin.auth import auth_required
from mergin.sync.permissions import ProjectPermissions, require_project_by_uuid
from .models import MapLink, MapOverview
from .tasks import build_map_overview

bp = Blueprint("plus_maps", __name__)

WMS_REQUESTS = {"getmap", "getlegendgraphic", "getfeatureinfo", "getcapabilities"}
# read-only WFS (no transactions)
WFS_REQUESTS = {"getcapabilities", "describefeaturetype", "getfeature"}
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


def _proxy(overview: MapOverview, allowed: dict, service_url: str):
    """Forward OGC request to QGIS Server for the prepared project version.

    allowed: service -> set of allowed (lower case) requests
    """
    params = {k.upper(): v for k, v in request.args.items()}
    service = params.get("SERVICE", "WMS").upper()
    if params.get("REQUEST", "").lower() not in allowed.get(service, set()):
        abort(400, "Unsupported OGC request")
    # clients can not choose the QGIS project file
    params.pop("MAP", None)
    params["SERVICE"] = service
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
            # capabilities documents advertise the public URL, not QGIS Server one
            headers={"X-Qgis-Service-Url": service_url},
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


def _public_url(path: str) -> str:
    return f"{current_app.config['MERGIN_BASE_URL'].rstrip('/')}{path}"


@bp.route("/v2/projects/<uuid:id>/map/wms", methods=["GET"])
@auth_required
def project_map_wms(id):
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Read)
    overview = _overview(project)
    return _proxy(
        overview,
        {"WMS": WMS_REQUESTS},
        _public_url(f"/v2/projects/{project.id}/map/wms"),
    )


# public map links


def _link_dict(link: Optional[MapLink]) -> dict:
    if not link:
        return {"enabled": False}
    base = current_app.config["MERGIN_BASE_URL"].rstrip("/")
    return {
        "enabled": True,
        "token": link.token,
        "url": f"{base}/maps/{link.token}",
        "ogc_enabled": link.ogc_enabled,
        "ogc_url": f"{base}/v2/maps/{link.token}/ogc" if link.ogc_enabled else None,
        "created": link.created.isoformat() + "Z",
    }


@bp.route("/v2/projects/<uuid:id>/map/link", methods=["GET"])
@auth_required
def get_map_link(id):
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Update)
    return jsonify(_link_dict(db.session.get(MapLink, project.id)))


@bp.route("/v2/projects/<uuid:id>/map/link", methods=["PUT"])
@auth_required
def set_map_link(id):
    """Enable map link (project owners, workspace admins), optionally with OGC services or a new token"""
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Update)
    data = request.get_json(silent=True) or {}
    link = db.session.get(MapLink, project.id)
    if not link:
        link = MapLink(
            project_id=project.id,
            token=secrets.token_urlsafe(24),
            ogc_enabled=False,
            created_by=current_user.id,
        )
        db.session.add(link)
    elif data.get("regenerate"):
        # old link stops working
        link.token = secrets.token_urlsafe(24)
    if "ogc_enabled" in data:
        link.ogc_enabled = bool(data["ogc_enabled"])
    db.session.commit()
    return jsonify(_link_dict(link))


@bp.route("/v2/projects/<uuid:id>/map/link", methods=["DELETE"])
@auth_required
def delete_map_link(id):
    _enabled()
    project = require_project_by_uuid(str(id), ProjectPermissions.Update)
    MapLink.query.filter_by(project_id=project.id).delete()
    db.session.commit()
    return "", 204


def _shared_overview(token: str):
    _enabled()
    link = MapLink.query.filter_by(token=token).first()
    if not link or not link.project or link.project.removed_at:
        abort(404, "Map not found")
    ws = current_app.ws_handler.get(link.project.workspace_id)
    if not ws or not ws.is_active:
        abort(404, "Map not found")
    return link, _overview(link.project)


@bp.route("/v2/maps/<token>", methods=["GET"])
def shared_map(token):
    """Map configuration for anyone with the link"""
    link, overview = _shared_overview(token)
    cfg = current_app.config
    return jsonify(
        {
            "name": link.project.name,
            "version": overview.version,
            "wms_url": f"/v2/maps/{token}/wms",
            "basemap": {
                "url": cfg["MAPS_BASEMAP_URL"],
                "attribution": cfg["MAPS_BASEMAP_ATTRIBUTION"],
                "vector_style_url": cfg["VECTOR_TILES_STYLE_URL"] or None,
            },
            **overview.config,
        }
    )


@bp.route("/v2/maps/<token>/wms", methods=["GET"])
def shared_map_wms(token):
    _, overview = _shared_overview(token)
    return _proxy(overview, {"WMS": WMS_REQUESTS}, _public_url(f"/v2/maps/{token}/wms"))


@bp.route("/v2/maps/<token>/ogc", methods=["GET"])
def shared_map_ogc(token):
    """Read-only OGC services (WMS, WFS) of a shared map, if enabled for the link"""
    link, overview = _shared_overview(token)
    if not link.ogc_enabled:
        abort(404, "OGC services are not enabled for this map")
    return _proxy(
        overview,
        {"WMS": WMS_REQUESTS, "WFS": WFS_REQUESTS},
        _public_url(f"/v2/maps/{token}/ogc"),
    )
