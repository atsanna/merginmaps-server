# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Open source reimplementation of Mergin Maps Enterprise Edition features.

Not affiliated with, sponsored or endorsed by Mergin Maps / Lutra Consulting.
Plugs into the Community Edition application through its extension points.
"""


def register(app):
    """Plug the add-on into a CE Flask application (see mergin_plus.app.register)"""
    from .app import register as _register

    return _register(app)
