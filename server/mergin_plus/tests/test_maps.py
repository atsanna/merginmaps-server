# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import os
import shutil
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from flask import current_app

from mergin.app import db
from mergin.sync.interfaces import WorkspaceRole
from mergin.tests.utils import add_user, create_project, login, push_change
from mergin_plus.maps.models import MapOverview
from mergin_plus.maps.qgis_project import datasource_file, find_qgis_file, parse_project
from mergin_plus.maps.tasks import build_map_overview
from mergin_plus.workspace.models import Workspace

CE_TEST_PROJECT = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    os.pardir,
    "mergin",
    "tests",
    "test_projects",
    "test",
)

QGS = """<!DOCTYPE qgis>
<qgis projectname="Survey" version="3.34.0">
  <title>Survey</title>
  <projectCrs><spatialrefsys><authid>EPSG:3857</authid></spatialrefsys></projectCrs>
  <layer-tree-group>
    <layer-tree-group name="Data" checked="Qt::Checked">
      <layer-tree-layer id="points_1" name="points" checked="Qt::Checked"/>
      <layer-tree-layer id="db_1" name="db" checked="Qt::Unchecked"/>
    </layer-tree-group>
    <layer-tree-layer id="ortho_1" name="ortho" checked="Qt::Unchecked"/>
  </layer-tree-group>
  <ProjectViewSettings><DefaultViewExtent xmin="0" ymin="0" xmax="100" ymax="50"/></ProjectViewSettings>
  <projectlayers>
    <maplayer type="vector" geometry="Point">
      <id>points_1</id><layername>points</layername><provider>ogr</provider>
      <datasource>./base.gpkg|layername=simple</datasource>
      <srs><spatialrefsys><authid>EPSG:4326</authid></spatialrefsys></srs>
      <extent><xmin>1</xmin><ymin>2</ymin><xmax>3</xmax><ymax>4</ymax></extent>
    </maplayer>
    <maplayer type="vector" geometry="Polygon">
      <id>db_1</id><layername>db</layername><provider>postgres</provider>
      <datasource>dbname='gis' host=db table="public"."parcels"</datasource>
    </maplayer>
    <maplayer type="raster">
      <id>ortho_1</id><layername>ortho</layername><provider>gdal</provider>
      <datasource>rasters/ortho.tif</datasource>
    </maplayer>
  </projectlayers>
  <visibility-presets>
    <visibility-preset name="only points"><layer id="points_1" visible="1"/></visibility-preset>
  </visibility-presets>
</qgis>
"""


@pytest.mark.parametrize(
    "provider,source,expected",
    [
        ("ogr", "./data.gpkg|layername=a", "data.gpkg"),
        ("ogr", "sub/x.shp", "sub/x.shp"),
        ("gdal", "/abs/x.tif", None),
        ("gdal", "../outside.tif", None),
        ("ogr", "C:/data/x.gpkg", None),
        ("postgres", "dbname='gis'", None),
        ("wms", "type=xyz&url=https://tile", None),
        ("vectortile", "type=mbtiles&url=./tiles.mbtiles", "tiles.mbtiles"),
    ],
)
def test_datasource_file(provider, source, expected):
    assert datasource_file(provider, source) == expected


def test_parse_project(tmp_path):
    path = tmp_path / "survey.qgs"
    path.write_text(QGS)
    config = parse_project(str(path), ["survey.qgs", "base.gpkg"])
    assert config["title"] == "Survey"
    assert config["crs"] == "EPSG:3857"
    assert config["extent"] == [0.0, 0.0, 100.0, 50.0]
    layers = {layer["id"]: layer for layer in config["layers"]}
    assert [layer["id"] for layer in config["layers"]] == [
        "points_1",
        "db_1",
        "ortho_1",
    ]
    assert layers["points_1"]["packaged"] and layers["points_1"]["visible"]
    assert layers["points_1"]["groups"] == ["Data"]
    assert layers["points_1"]["extent"] == [1.0, 2.0, 3.0, 4.0]
    assert not layers["db_1"]["packaged"]
    # file referenced but not part of the project
    assert layers["ortho_1"]["file"] == "rasters/ortho.tif"
    assert not layers["ortho_1"]["packaged"] and not layers["ortho_1"]["visible"]
    assert config["themes"] == {"only points": ["points_1"]}
    assert config["tree"][0]["name"] == "Data"

    # .qgz is a zip with the .qgs inside
    qgz = tmp_path / "survey.qgz"
    with zipfile.ZipFile(qgz, "w") as z:
        z.writestr("survey.qgs", QGS)
    assert parse_project(str(qgz), [])["title"] == "Survey"
    assert find_qgis_file(["a/b.qgs", "z.qgz", "survey.qgs"]) == "survey.qgs"


@pytest.fixture
def maps(app, tmp_path):
    cfg = current_app.config
    old = {k: cfg[k] for k in ("MAPS_ENABLED", "OVERVIEW_DATA", "QGIS_SERVER_URL")}
    cfg.update(
        MAPS_ENABLED=True,
        OVERVIEW_DATA=str(tmp_path / "overviews"),
        QGIS_SERVER_URL="http://qgis/ows/",
    )
    yield tmp_path
    cfg.update(old)


def _map_project(owner, tmp_path):
    ws = Workspace(name="maps", storage=10 * 1024 * 1024)
    db.session.add(ws)
    db.session.flush()
    ws.set_role(owner.id, WorkspaceRole.OWNER)
    db.session.commit()
    project = create_project("survey", ws, owner)
    src = tmp_path / "src"
    src.mkdir()
    (src / "survey.qgs").write_text(QGS)
    shutil.copy(os.path.join(CE_TEST_PROJECT, "base.gpkg"), src / "base.gpkg")
    with patch("mergin_plus.maps.tasks.build_map_overview.delay") as delay:
        push_change(project, "added", "base.gpkg", str(src))
        push_change(project, "added", "survey.qgs", str(src))
    return ws, project, delay


def test_overview_and_map_api(client, maps):
    owner = add_user("owner", "Owner123!")
    ws, project, delay = _map_project(owner, maps)
    login(client, "owner", "Owner123!")
    url = f"/v2/projects/{project.id}/map"
    assert client.get(url).status_code == 404

    build_map_overview(str(project.id), project.latest_version)
    overview = db.session.get(MapOverview, project.id)
    assert overview.error is None and overview.version == 2
    assert os.path.exists(os.path.join(overview.data_dir, "survey.qgs"))
    assert os.path.exists(os.path.join(overview.data_dir, "base.gpkg"))

    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json["qgis_file"] == "survey.qgs"
    assert resp.json["wms_url"] == f"/v2/projects/{project.id}/map/wms"
    assert "openstreetmap" in resp.json["basemap"]["url"]
    assert [layer["name"] for layer in resp.json["layers"] if layer["packaged"]] == [
        "points"
    ]

    # outsiders have no access
    add_user("other", "Other1234!")
    login(client, "other", "Other1234!")
    assert client.get(url).status_code == 403


def test_wms_proxy(client, maps):
    owner = add_user("owner", "Owner123!")
    ws, project, _ = _map_project(owner, maps)
    build_map_overview(str(project.id), project.latest_version)
    overview = db.session.get(MapOverview, project.id)
    login(client, "owner", "Owner123!")
    url = f"/v2/projects/{project.id}/map/wms"

    assert client.get(f"{url}?REQUEST=GetPrint").status_code == 400
    upstream = MagicMock(status_code=200, headers={"Content-Type": "image/png"})
    upstream.iter_content.return_value = [b"PNG"]
    with patch("mergin_plus.maps.views.requests.get", return_value=upstream) as get:
        resp = client.get(f"{url}?request=GetMap&LAYERS=points&MAP=/etc/passwd")
    assert resp.status_code == 200
    assert resp.data == b"PNG"
    assert resp.headers["Content-Type"] == "image/png"
    params = get.call_args.kwargs["params"]
    # MAP can not be overridden by clients
    assert params["MAP"] == os.path.join(overview.data_dir, "survey.qgs")
    assert params["SERVICE"] == "WMS" and params["LAYERS"] == "points"
    assert get.call_args.args[0] == "http://qgis/ows/"


def test_overview_failure_keeps_previous(client, maps):
    owner = add_user("owner", "Owner123!")
    ws, project, _ = _map_project(owner, maps)
    build_map_overview(str(project.id), project.latest_version)
    with patch(
        "mergin_plus.maps.overview.parse_project", side_effect=ValueError("broken")
    ):
        project.latest_version  # noqa: B018
        from mergin_plus.maps.overview import build_overview

        build_overview(project)
    overview = db.session.get(MapOverview, project.id)
    assert overview.error == "broken"
    assert overview.version == 2 and overview.config["title"] == "Survey"


def test_version_created_queues_overview(client, maps):
    from mergin.sync.models import ProjectVersion, project_version_created

    owner = add_user("owner", "Owner123!")
    _, project, _ = _map_project(owner, maps)
    version = ProjectVersion.query.filter_by(project_id=project.id, name=2).first()
    with patch("mergin_plus.maps.tasks.build_map_overview.delay") as delay:
        project_version_created.send(version)
        assert delay.call_args.args == (str(project.id), 2)
        current_app.config["MAPS_ENABLED"] = False
        project_version_created.send(version)
        assert delay.call_count == 1
    assert client.get(f"/v2/projects/{project.id}/map").status_code == 404


def test_shared_map_link_and_ogc(client, maps):
    owner = add_user("owner", "Owner123!")
    reader = add_user("reader", "Reader123!")
    ws, project, _ = _map_project(owner, maps)
    ws.set_role(reader.id, WorkspaceRole.READER)
    db.session.commit()
    build_map_overview(str(project.id), project.latest_version)
    link_url = f"/v2/projects/{project.id}/map/link"

    # readers can not share the map
    login(client, "reader", "Reader123!")
    assert client.put(link_url, json={}).status_code == 403
    login(client, "owner", "Owner123!")
    assert client.get(link_url).json == {"enabled": False}
    resp = client.put(link_url, json={})
    assert resp.status_code == 200
    token = resp.json["token"]
    assert resp.json["url"].endswith(f"/maps/{token}")
    assert resp.json["ogc_enabled"] is False

    # anyone with the link sees the map, without project internals
    anonymous = current_app.test_client()
    from flask import g

    g.pop("_login_user", None)
    resp = anonymous.get(f"/v2/maps/{token}")
    assert resp.status_code == 200
    assert resp.json["wms_url"] == f"/v2/maps/{token}/wms"
    assert "project_id" not in resp.json
    assert anonymous.get("/v2/maps/wrong-token").status_code == 404

    upstream = MagicMock(status_code=200, headers={"Content-Type": "image/png"})
    upstream.iter_content.return_value = [b"PNG"]
    with patch("mergin_plus.maps.views.requests.get", return_value=upstream) as get:
        assert anonymous.get(f"/v2/maps/{token}/wms?REQUEST=GetMap").status_code == 200
        assert get.call_args.kwargs["headers"]["X-Qgis-Service-Url"].endswith(
            f"/v2/maps/{token}/wms"
        )
        # OGC services only when enabled, read-only WFS
        assert (
            anonymous.get(
                f"/v2/maps/{token}/ogc?SERVICE=WFS&REQUEST=GetFeature"
            ).status_code
            == 404
        )
        g.pop("_login_user", None)
        login(client, "owner", "Owner123!")
        resp = client.put(link_url, json={"ogc_enabled": True})
        assert resp.json["ogc_url"].endswith(f"/v2/maps/{token}/ogc")
        g.pop("_login_user", None)
        assert (
            anonymous.get(
                f"/v2/maps/{token}/ogc?SERVICE=WFS&REQUEST=GetFeature"
            ).status_code
            == 200
        )
        assert get.call_args.kwargs["params"]["SERVICE"] == "WFS"
        assert (
            anonymous.get(
                f"/v2/maps/{token}/ogc?SERVICE=WFS&REQUEST=Transaction"
            ).status_code
            == 400
        )

    # regenerated link invalidates the old one, deleted link stops working
    login(client, "owner", "Owner123!")
    new_token = client.put(link_url, json={"regenerate": True}).json["token"]
    assert new_token != token
    g.pop("_login_user", None)
    assert anonymous.get(f"/v2/maps/{token}").status_code == 404
    login(client, "owner", "Owner123!")
    assert client.delete(link_url).status_code == 204
    g.pop("_login_user", None)
    assert anonymous.get(f"/v2/maps/{new_token}").status_code == 404
