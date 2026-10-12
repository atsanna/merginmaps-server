# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Registration of the add-on into a Community Edition Flask application.

All the integration with CE goes through its public extension points, CE files are never modified:
- application.ws_handler / application.project_handler replacement
- additional Connexion APIs and Flask blueprints
- blinker signals (user_created, ...)
- alembic version locations (add-on migrations form the "enterprise" branch)
"""

import functools
import os

from flask import Blueprint, Flask, jsonify

from .config import Configuration

this_dir = os.path.dirname(os.path.realpath(__file__))
# alembic script directory of CE, add-on keeps its own versions next to it
CE_MIGRATIONS_DIR = os.path.abspath(os.path.join(this_dir, os.pardir, "migrations"))
MIGRATIONS_DIR = CE_MIGRATIONS_DIR
PLUS_VERSIONS_DIR = os.path.join(this_dir, "migrations")
# config keys exposed to clients on /config in addition to CE ones
PUBLIC_KEYS = ["USER_WORKSPACES_ALLOWED"]


def configure_migrations(app: Flask):
    """Add alembic 'enterprise' branch (add-on migrations) next to the 'community' one"""
    migrate = app.extensions["migrate"].migrate

    @migrate.configure
    def add_enterprise_versions(config):
        locations = [os.path.join(CE_MIGRATIONS_DIR, "community"), PLUS_VERSIONS_DIR]
        config.set_main_option("version_locations", ":".join(locations))
        return config


def extend_public_config(app: Flask):
    """Add add-on settings to CE /config endpoint response"""
    view = app.view_functions.get("config")
    if not view or getattr(view, "_plus_extended", False):
        return

    @functools.wraps(view)
    def config():
        resp, status = view()
        data = resp.get_json()
        data.update({key.lower(): app.config.get(key) for key in PUBLIC_KEYS})
        return jsonify(data), status

    config._plus_extended = True
    app.view_functions["config"] = config


def register(app: Flask):
    """Plug enterprise features into CE application"""
    from mergin.stats.config import Configuration as StatsConfiguration
    from .workspace.handler import WorkspaceHandler
    from .workspace.listeners import register_listeners
    from .workspace.project_handler import ProjectHandler

    app.config.from_object(Configuration)
    # clients (QGIS plugin, mobile app) enable workspace features only for "ee" servers
    app.config["SERVER_TYPE"] = "ee"
    # this fork must never report itself to Mergin Maps as an Enterprise Edition installation
    app.config["COLLECT_STATISTICS"] = False
    StatsConfiguration.COLLECT_STATISTICS = False
    app.ws_handler = WorkspaceHandler()
    app.project_handler = ProjectHandler()

    for name, spec in (
        ("plus_workspace", "api.yaml"),
        ("plus_members", "members_api.yaml"),
    ):
        app.connexion_app.add_api(
            os.path.join(this_dir, "workspace", spec),
            base_path="/",
            options={"swagger_ui": False, "serve_spec": False},
            validate_responses=True,
        )
        app.blueprints["/"].name = name
        app.blueprints[name] = app.blueprints.pop("/")

    # e-mail templates
    app.register_blueprint(Blueprint("plus", __name__, template_folder="templates"))
    register_listeners()
    extend_public_config(app)
    configure_migrations(app)
