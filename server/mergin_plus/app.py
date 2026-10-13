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
PUBLIC_KEYS = [
    "USER_WORKSPACES_ALLOWED",
    "DASHBOARD_LOGO_URL",
    "INSTANCE_NAME",
    # QGIS plugin and mobile app offer SSO login when sso_enabled is true
    "SSO_ENABLED",
    # admin panel links to the Polis admin UI
    "SSO_SERVER_URL",
    "MAPS_ENABLED",
]


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


def guard_create_user(app: Flask):
    """Validate workspace part of CE POST /v2/users before CE creates the user.

    CE only checks that the caller can add users to the workspace, the add-on also requires an active workspace,
    owner permission to create owners, no guest role (guests are invited to projects) and a free contributor seat.
    """
    from flask import abort, request
    from flask_login import current_user

    from mergin.sync.interfaces import WorkspaceRole
    from .workspace.limits import check_can_add_contributor
    from .workspace.models import CONTRIBUTOR_ROLES

    endpoint = next(
        (
            rule.endpoint
            for rule in app.url_map.iter_rules()
            if rule.rule == "/v2/users" and "POST" in rule.methods
        ),
        None,
    )
    view = app.view_functions.get(endpoint) if endpoint else None
    if not view or getattr(view, "_plus_guarded", False):
        return

    @functools.wraps(view)
    def create_user(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        if current_user.is_authenticated and "workspace_id" in data:
            ws = app.ws_handler.get(data.get("workspace_id"))
            if ws and ws.can_add_users(current_user):
                if not ws.is_active:
                    abort(404, "Workspace not found")
                role = data.get("role")
                if role == WorkspaceRole.GUEST.value:
                    abort(
                        400,
                        "Users can not be created as guests, invite them to projects",
                    )
                if role == WorkspaceRole.OWNER.value and not ws.user_has_permissions(
                    current_user, "owner"
                ):
                    abort(403, "Only workspace owners can manage owners")
                if role in CONTRIBUTOR_ROLES:
                    check_can_add_contributor(ws)
        return view(*args, **kwargs)

    create_user._plus_guarded = True
    app.view_functions[endpoint] = create_user


def register(app: Flask):
    """Plug enterprise features into CE application"""
    from mergin.stats.config import Configuration as StatsConfiguration
    from .audit.sink import AuditSink
    from .transfer import models as transfer_models  # noqa: F401 (tables)
    from .workspace.handler import WorkspaceHandler
    from .workspace.limits import (
        ContributorsLimitHit,
        handle_limit_hit,
        register_events as register_limits_events,
    )
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
        ("plus_workspace", "workspace/api.yaml"),
        ("plus_members", "workspace/members_api.yaml"),
        ("plus_admin", "workspace/admin_api.yaml"),
        ("plus_transfer", "transfer/api.yaml"),
        ("plus_audit", "audit/api.yaml"),
    ):
        app.connexion_app.add_api(
            os.path.join(this_dir, spec),
            base_path="/",
            options={"swagger_ui": False, "serve_spec": False},
            validate_responses=True,
        )
        app.blueprints["/"].name = name
        app.blueprints[name] = app.blueprints.pop("/")

    # single sign-on routes (plain Flask views: redirects and form encoded token endpoint)
    from mergin.app import csrf
    from .sso.views import bp as sso_bp

    csrf.exempt(sso_bp)
    app.register_blueprint(sso_bp)

    # web maps (WMS proxy streams binary responses, so plain Flask views too)
    from .maps.listeners import register_listeners as register_maps_listeners
    from .maps.views import bp as maps_bp

    app.register_blueprint(maps_bp)
    register_maps_listeners()

    # e-mail templates
    app.register_blueprint(Blueprint("plus", __name__, template_folder="templates"))
    register_listeners()
    register_limits_events()
    # store audit events and forward them to webhooks (CE default is NullSink)
    app.extensions["audit"]["sink"] = AuditSink()
    app.register_error_handler(ContributorsLimitHit, handle_limit_hit)
    extend_public_config(app)
    guard_create_user(app)
    configure_migrations(app)
