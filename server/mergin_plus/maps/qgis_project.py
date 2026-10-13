# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Read the map configuration of a QGIS project file (.qgs XML or .qgz zip) without QGIS libraries.

Only what the web map needs is extracted: title, CRS, extent, layers (with their position in the layer tree
and whether their data are packaged in the project), and map themes.
"""

import os
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Optional

QGIS_EXTENSIONS = (".qgs", ".qgz")
# data formats which can be part of a Mergin Maps project
PACKAGED_EXTENSIONS = (
    ".gpkg",
    ".shp",
    ".mbtiles",
    ".tif",
    ".tiff",
    ".geojson",
    ".json",
    ".csv",
    ".sqlite",
    ".jpg",
    ".png",
)
FILE_PROVIDERS = ("ogr", "gdal", "spatialite", "vectortile", "delimitedtext", "wms")


def find_qgis_file(paths: List[str]) -> Optional[str]:
    """QGIS project file in the project root (Mergin Maps projects have one)"""
    candidates = sorted(
        p for p in paths if p.lower().endswith(QGIS_EXTENSIONS) and "/" not in p
    )
    return candidates[0] if candidates else None


# maximum size of the .qgs document (also when unpacked from .qgz)
MAX_QGS_SIZE = 50 * 1024 * 1024


class InvalidProjectError(ValueError):
    pass


def _qgz_member(z: zipfile.ZipFile) -> zipfile.ZipInfo:
    info = next((i for i in z.infolist() if i.filename.lower().endswith(".qgs")), None)
    if info is None:
        raise InvalidProjectError("QGIS project archive without .qgs file")
    if info.file_size > MAX_QGS_SIZE:
        raise InvalidProjectError("QGIS project file is too large")
    return info


def read_xml(path: str) -> ET.Element:
    if path.lower().endswith(".qgz"):
        with zipfile.ZipFile(path) as z:
            info = _qgz_member(z)
            with z.open(info) as f:
                # declared size can not be trusted, read at most the limit
                data = f.read(MAX_QGS_SIZE + 1)
            if len(data) > MAX_QGS_SIZE:
                raise InvalidProjectError("QGIS project file is too large")
            return ET.fromstring(data)
    if os.path.getsize(path) > MAX_QGS_SIZE:
        raise InvalidProjectError("QGIS project file is too large")
    return ET.parse(path).getroot()


def _write_xml(root: ET.Element, path: str) -> None:
    """Replace project file (a hard link to project storage, so unlink it first)"""
    data = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    data = b"<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n" + data
    if path.lower().endswith(".qgz"):
        with zipfile.ZipFile(path) as z:
            info = _qgz_member(z)
            others = [
                (i, z.read(i))
                for i in z.infolist()
                if i.filename != info.filename and i.file_size <= MAX_QGS_SIZE
            ]
        os.unlink(path)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(info.filename, data)
            for i, content in others:
                z.writestr(i, content)
        return
    os.unlink(path)
    with open(path, "wb") as f:
        f.write(data)


# project properties which can contain Python code
UNSAFE_PROPERTIES = ("Macros", "ExpressionFunctions", "PythonInit")


def sanitize_project(path: str, project_files: List[str]) -> List[str]:
    """Make the copy of a QGIS project used by QGIS Server safe to open.

    Project writers control the .qgs, so every layer whose data are not a file of the project is removed
    (absolute paths, other projects' data, databases, web services: they could read server files or
    reach internal hosts through QGIS Server), as well as embedded layers and stored Python code.
    Returns ids of removed layers.
    """
    root = read_xml(path)
    files = set(project_files)
    qgis_dir = posixpath.dirname(os.path.basename(path))
    removed = []
    for container in root.iter("projectlayers"):
        for ml in list(container):
            if ml.tag != "maplayer":
                continue
            data_file = datasource_file(
                _text(ml, "provider", ""), _text(ml, "datasource", "")
            )
            if data_file and qgis_dir:
                data_file = posixpath.normpath(posixpath.join(qgis_dir, data_file))
            if ml.get("embedded") == "1" or not data_file or data_file not in files:
                removed.append(_text(ml, "id"))
                container.remove(ml)
    removed_ids = set(removed)

    def prune(parent: ET.Element):
        for child in list(parent):
            if child.tag == "layer-tree-layer" and (
                child.get("id") in removed_ids or child.get("embedded") == "1"
            ):
                parent.remove(child)
            elif child.tag == "layer-tree-group" and child.get("embedded") == "1":
                parent.remove(child)
            else:
                prune(child)

    prune(root)
    for props in root.iter("properties"):
        for child in list(props):
            if child.tag in UNSAFE_PROPERTIES:
                props.remove(child)
    _write_xml(root, path)
    return removed


def _text(el: Optional[ET.Element], path: str, default=None):
    found = el.find(path) if el is not None else None
    return found.text if found is not None and found.text is not None else default


def _float_extent(values) -> Optional[List[float]]:
    try:
        extent = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(extent) != 4 or extent[0] >= extent[2] or extent[1] >= extent[3]:
        return None
    return extent


def datasource_file(provider: str, datasource: str) -> Optional[str]:
    """Relative path of the data file of a layer, None for non file based or absolute sources"""
    if not datasource or provider not in FILE_PROVIDERS:
        return None
    source = datasource
    if provider == "vectortile" or (provider == "wms" and "mbtiles" in source):
        match = re.search(r"url=([^&]+\.mbtiles)", source)
        if not match:
            return None
        source = match.group(1)
    elif provider == "delimitedtext":
        source = re.sub(r"^file://", "", source.split("?")[0])
    elif provider == "wms":
        return None
    source = source.split("|")[0].strip()
    if source.startswith("./"):
        source = source[2:]
    if not source or os.path.isabs(source) or re.match(r"^[a-zA-Z]+:", source):
        return None
    normalized = posixpath.normpath(source.replace("\\", "/"))
    if normalized.startswith(".."):
        return None
    return normalized


def _layer_tree(group: ET.Element, layers: dict, parents: List[str]) -> list:
    nodes = []
    for child in group:
        if child.tag == "layer-tree-layer":
            layer_id = child.get("id")
            if layer_id in layers:
                layers[layer_id]["visible"] = child.get("checked") == "Qt::Checked"
                layers[layer_id]["groups"] = parents
                nodes.append({"type": "layer", "id": layer_id})
        elif child.tag == "layer-tree-group":
            name = child.get("name")
            nodes.append(
                {
                    "type": "group",
                    "name": name,
                    "visible": child.get("checked") == "Qt::Checked",
                    "children": _layer_tree(child, layers, parents + [name]),
                }
            )
    return nodes


def _flatten(nodes: list) -> List[str]:
    order = []
    for node in nodes:
        if node["type"] == "layer":
            order.append(node["id"])
        else:
            order.extend(_flatten(node["children"]))
    return order


def parse_project(path: str, project_files: List[str]) -> dict:
    """Map configuration of QGIS project; project_files are relative paths of files present in the project"""
    root = read_xml(path)
    files = set(project_files)
    qgis_dir = posixpath.dirname(os.path.basename(path))

    layers = {}
    for ml in root.iter("maplayer"):
        layer_id = _text(ml, "id")
        if not layer_id:
            continue
        provider = _text(ml, "provider", "")
        datasource = _text(ml, "datasource", "")
        data_file = datasource_file(provider, datasource)
        if data_file and qgis_dir:
            data_file = posixpath.normpath(posixpath.join(qgis_dir, data_file))
        extent_el = ml.find("extent")
        layers[layer_id] = {
            "id": layer_id,
            "name": _text(ml, "layername", layer_id),
            "type": ml.get("type"),
            "geometry": ml.get("geometry") or ml.get("wkbType"),
            "provider": provider,
            "crs": _text(ml, "srs/spatialrefsys/authid"),
            "extent": _float_extent(
                [_text(extent_el, k) for k in ("xmin", "ymin", "xmax", "ymax")]
            ),
            "file": data_file,
            # only layers with data inside the project can be shown on the web map
            "packaged": bool(data_file and data_file in files),
            "visible": True,
            "groups": [],
        }

    tree_root = root.find("layer-tree-group")
    tree = _layer_tree(tree_root, layers, []) if tree_root is not None else []
    order = _flatten(tree) or list(layers)

    themes = {}
    for preset in root.iter("visibility-preset"):
        themes[preset.get("name")] = [
            el.get("id")
            for el in preset.findall("layer")
            if el.get("visible", "1") == "1" and el.get("id") in layers
        ]

    view = root.find(".//DefaultViewExtent")
    extent = None
    if view is not None:
        extent = _float_extent([view.get(k) for k in ("xmin", "ymin", "xmax", "ymax")])
    if extent is None:
        wms = root.find("properties/WMSExtent")
        if wms is not None:
            extent = _float_extent([v.text for v in wms.findall("value")])
    if extent is None:
        canvas = root.find("mapcanvas/extent")
        extent = _float_extent(
            [_text(canvas, k) for k in ("xmin", "ymin", "xmax", "ymax")]
        )

    return {
        "title": _text(root, "title") or root.get("projectname") or "",
        "crs": _text(root, "projectCrs/spatialrefsys/authid"),
        "extent": extent,
        "layers": [layers[i] for i in order if i in layers],
        "tree": tree,
        "themes": themes,
    }
