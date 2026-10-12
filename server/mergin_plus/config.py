# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from decouple import config

from mergin.config import Configuration as MainConfiguration


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
