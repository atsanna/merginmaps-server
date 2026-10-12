# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import os

from decouple import Csv, config

from mergin.config import Configuration as MainConfiguration
from mergin.sync.config import Configuration as SyncConfiguration


class Configuration(object):
    # default storage quota (bytes) of newly created workspaces
    WORKSPACE_STORAGE_SIZE = config(
        "WORKSPACE_STORAGE_SIZE", default=MainConfiguration.GLOBAL_STORAGE, cast=int
    )
    # days a closed workspace is kept before it is permanently removed
    WORKSPACE_EXPIRATION = config("WORKSPACE_EXPIRATION", default=7, cast=int)
    # whether regular users can create workspaces, otherwise only superusers can
    USER_WORKSPACES_ALLOWED = config("USER_WORKSPACES_ALLOWED", default=True, cast=bool)
    # days a workspace invitation is valid
    WORKSPACE_INVITATION_EXPIRATION = config(
        "WORKSPACE_INVITATION_EXPIRATION", default=14, cast=int
    )
    # default maximum of contributors of newly created workspaces, 0 means unlimited
    WORKSPACE_CONTRIBUTORS_LIMIT = config(
        "WORKSPACE_CONTRIBUTORS_LIMIT", default=0, cast=int
    )
    # days a project transfer request is valid
    PROJECT_TRANSFER_EXPIRATION = config(
        "PROJECT_TRANSFER_EXPIRATION", default=7, cast=int
    )
    # store audit events in database
    AUDIT_LOG_ENABLED = config("AUDIT_LOG_ENABLED", default=True, cast=bool)
    # days audit events are kept
    AUDIT_LOG_RETENTION = config("AUDIT_LOG_RETENTION", default=365, cast=int)
    # webhooks may target private / loopback addresses (only for trusted setups)
    WEBHOOKS_ALLOW_PRIVATE_URLS = config(
        "WEBHOOKS_ALLOW_PRIVATE_URLS", default=False, cast=bool
    )
    WEBHOOKS_TIMEOUT = config("WEBHOOKS_TIMEOUT", default=10, cast=int)
    # webhook is disabled after this number of consecutive failed deliveries
    WEBHOOKS_MAX_FAILURES = config("WEBHOOKS_MAX_FAILURES", default=20, cast=int)
    # name of this server shown in the dashboard (branding)
    INSTANCE_NAME = config("INSTANCE_NAME", default="")
    # single sign-on through Ory Polis (SAML / OIDC bridge)
    SSO_ENABLED = config("SSO_ENABLED", default=False, cast=bool)
    # public URL of Polis (browser redirects)
    SSO_SERVER_URL = config("SSO_SERVER_URL", default="").rstrip("/")
    # URL of Polis reachable from the server (API calls), defaults to public one
    SSO_SERVER_API_URL = config("SSO_SERVER_API_URL", default=SSO_SERVER_URL).rstrip(
        "/"
    )
    SSO_SERVER_API_KEY = config("SSO_SERVER_API_KEY", default="")
    SSO_SERVER_PRODUCT_ID = config(
        "SSO_SERVER_PRODUCT_ID", default="mergin-maps-product"
    )
    # lifetime of tokens issued after SSO login (seconds), default 14 days
    SSO_SESSION_EXPIRATION = config(
        "SSO_SESSION_EXPIRATION", default=14 * 24 * 3600, cast=int
    )
    # "multi": identity provider chosen by e-mail domain (tenant), "single": one tenant for everybody
    SSO_TENANT_FLOW = config("SSO_TENANT_FLOW", default="multi")
    SSO_DEFAULT_TENANT = config("SSO_DEFAULT_TENANT", default="")
    # client redirect URIs allowed in the OAuth2 flow (QGIS plugin, mobile app), comma separated prefixes
    SSO_ALLOWED_REDIRECT_URIS = config(
        "SSO_ALLOWED_REDIRECT_URIS",
        default="http://localhost:10042/,http://127.0.0.1:10042/,http://[::1]:10042/,"
        "https://hello.merginmaps.com/mobile/sso-redirect",
        cast=Csv(),
    )
    # web maps of projects (QGIS Server)
    MAPS_ENABLED = config("MAPS_ENABLED", default=False, cast=bool)
    # directory with project data prepared for QGIS Server, shared with the QGIS Server container
    OVERVIEW_DATA = config(
        "OVERVIEW_DATA",
        default=os.path.join(SyncConfiguration.LOCAL_PROJECTS, "map_overviews"),
    )
    # path of OVERVIEW_DATA as seen by QGIS Server (when mounted elsewhere)
    QGIS_SERVER_DATA = config("QGIS_SERVER_DATA", default="")
    # QGIS Server OWS endpoint
    QGIS_SERVER_URL = config(
        "QGIS_SERVER_URL", default=config("WMTS_SERVER_URL", default="")
    )
    QGIS_SERVER_TIMEOUT = config("QGIS_SERVER_TIMEOUT", default=60, cast=int)
    # default basemap of web maps (XYZ raster tiles), OpenStreetMap unless configured
    MAPS_BASEMAP_URL = config(
        "MAPS_BASEMAP_URL", default="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    )
    MAPS_BASEMAP_ATTRIBUTION = config(
        "MAPS_BASEMAP_ATTRIBUTION",
        default='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    )
    # optional vector tiles basemap (Mapbox GL style URL)
    VECTOR_TILES_STYLE_URL = config("VECTOR_TILES_STYLE_URL", default="")
