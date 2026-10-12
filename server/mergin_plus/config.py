# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from decouple import config

from mergin.config import Configuration as MainConfiguration


class Configuration(object):
    # switch for the whole package, without it the server runs as plain Community Edition
    ENTERPRISE_ENABLED = config("ENTERPRISE_ENABLED", default=False, cast=bool)
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
