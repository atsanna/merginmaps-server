# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Pytest plugin running the unmodified Community Edition test suite on top of the add-on.

    pytest -p mergin_plus.ce_suite mergin/tests

CE test helpers are wrapped once CE conftest files are loaded:
- every app created by CE fixtures gets the add-on registered
- the CE global workspace (id 1) is created as a db workspace before CE testing data
Tests asserting CE single global workspace behaviour (GLOBAL_* settings) are skipped.
"""

import pytest


# CE tests relying on GLOBAL_READ/WRITE/ADMIN or GLOBAL_STORAGE, or on statistics sending
CE_ONLY_TESTS = {
    "test_auth.py::test_search_user",
    "test_config.py::test_config",
    "test_controller.py::test_server_updates",
    "test_permissions.py::test_project_permissions",
    "test_project_controller.py::test_clone_project",
    "test_project_controller.py::test_get_paginated_projects",
    "test_project_controller.py::test_inactive_project",
    "test_project_controller.py::test_exceed_data_limit",
    "test_public_api_v2.py::test_project_members",
    "test_public_api_v2.py::test_create_version_failures",
    "test_public_api_v2.py::test_create_version_permanent_error_takes_priority",
    "test_public_api_v2.py::test_list_projects_in_batch",
    "test_public_api_v2.py::test_list_workspace_projects",
    "test_statistics.py::test_send_statistics",
    "test_workspace.py::test_workspace",
}


@pytest.hookimpl(hookwrapper=True)
def pytest_load_initial_conftests(early_config, parser, args):
    # CE conftest files configure the environment (test env file, per xdist worker database),
    # so CE modules can be imported only after they are loaded
    yield
    import mergin.tests.fixtures as ce_fixtures
    import mergin.tests.utils as ce_utils
    from .testing import (
        create_app_with_plus,
        db_global_workspace,
        initialize_with_workspace,
    )

    # CE fixtures look these names up in their module globals when they run
    ce_fixtures.create_app = create_app_with_plus(ce_fixtures.create_app)
    ce_fixtures.initialize = initialize_with_workspace(ce_fixtures.initialize)
    # test modules import it from utils when collected
    ce_utils.create_workspace = db_global_workspace


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="relies on CE single global workspace")
    for item in items:
        if f"{item.path.name}::{item.originalname}" in CE_ONLY_TESTS:
            item.add_marker(skip)
