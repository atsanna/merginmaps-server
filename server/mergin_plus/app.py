# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import os

from flask import Blueprint, Flask

from .config import Configuration

this_dir = os.path.dirname(os.path.realpath(__file__))
MIGRATIONS_DIR = os.path.join(this_dir, os.pardir, "migrations")


def configure_migrations(app: Flask):
    """Add alembic 'enterprise' branch next to the 'community' one"""
    migrate = app.extensions["migrate"].migrate

    @migrate.configure
    def add_enterprise_versions(config):
        locations = [
            os.path.abspath(os.path.join(MIGRATIONS_DIR, "community")),
            os.path.abspath(os.path.join(MIGRATIONS_DIR, "enterprise")),
        ]
        config.set_main_option("version_locations", ":".join(locations))
        return config


def register(app: Flask):
    """Plug workspaces implementation into CE application"""
    from .workspace.handler import WorkspaceHandler
    from .workspace.listeners import register_listeners
    from .workspace.project_handler import ProjectHandler

    app.config.from_object(Configuration)
    # clients (QGIS plugin, mobile app) enable workspace features only for "ee" servers
    app.config["SERVER_TYPE"] = "ee"
    # this fork must never report itself to Mergin Maps as an Enterprise Edition installation
    app.config["COLLECT_STATISTICS"] = False
    app.ws_handler = WorkspaceHandler()
    app.project_handler = ProjectHandler()

    app.connexion_app.add_api(
        os.path.join(this_dir, "workspace", "api.yaml"),
        base_path="/",
        options={"swagger_ui": False, "serve_spec": False},
        validate_responses=True,
    )
    app.blueprints["/"].name = "plus_workspace"
    app.blueprints["plus_workspace"] = app.blueprints.pop("/")

    app.connexion_app.add_api(
        os.path.join(this_dir, "workspace", "members_api.yaml"),
        base_path="/",
        options={"swagger_ui": False, "serve_spec": False},
        validate_responses=True,
    )
    app.blueprints["/"].name = "plus_members"
    app.blueprints["plus_members"] = app.blueprints.pop("/")

    # e-mail templates
    app.register_blueprint(Blueprint("plus", __name__, template_folder="templates"))
    register_listeners()

    configure_migrations(app)
