# Community Edition inventory — extension points for Enterprise features

Snapshot of the CE codebase (commit 281975c), made to plan the independent reimplementation of Enterprise features.

## Key finding

CE is designed so that EE plugs in by **runtime replacement**:

- `server/mergin/app.py` ~438: `application.ws_handler = GlobalWorkspaceHandler()` and `application.project_handler = ProjectHandler()`.
- Audit sink pluggable via `app.extensions["audit"]["sink"]` (CE: `NullSink`, `audit/app.py:10`; base `audit/sinks.py:10 AbstractSink`).
- Alembic ready for a separate `enterprise` branch on top of `community` (`server/migrations/alembic.ini` `version_locations`, `test_migrations/utils.py:95-120`).
- Web app ships `*Template.vue` components with slots + `RouteOverrides`.
- Upstream EE appears to be a separate Python package (`src.*`, e.g. `src.workspace.models`, `src.maps.tasks.finish_overview`) wrapping `mergin.create_app`.

## Backend

- Entrypoint `server/application.py`: forces `SERVER_TYPE = "ce"` (l.38), `USER_SELF_REGISTRATION = False` (l.39); exposes config keys on `/config` (l.41-54; `DASHBOARD_LOGO_URL` not exposed); celery beat schedule l.62-97.
- Modules: `auth/` (users, login, tokens, admin users, `register_permission` registry `auth/app.py:54`, signals `user_account_closed`, `user_created`), `sync/` (projects, versions, files, permissions, workspace abstraction, storages registry `Storages = {"local": DiskStorage}` `sync/models.py:62`), `audit/`, `stats/`, `otel/`, `templates/email/`.
- API specs (Connexion, OpenAPI 3): `api.yaml`, `auth/api.yaml`, `sync/public_api.yaml` (/v1), `sync/public_api_v2.yaml` (/v2), `sync/private_api.yaml` (/app — `/project/{id}/access` "Kept for EE"), `stats/api.yaml`.
- Models: `User` (passwd nullable = SSO user), `LoginHistory`, `Project` (`workspace_id` integer **without FK** → workspace table can live outside CE), `ProjectUser` (`project_member`, roles READER<EDITOR<WRITER<OWNER), versions/files/diffs, `AccessRequest`, stats. **No** workspace / invitation / transfer / SSO tables.
- Signals (`sync/models.py:63-67`): `project_deleted`, `project_soft_deleted`, `project_access_granted`, `push_finished`, `project_version_created` → natural hooks for webhooks/notifications.

## Workspace abstraction

- `sync/interfaces.py`: `AbstractWorkspace` (l.9), `WorkspaceHandler` (l.89; optional `list_user_invitations`, `workspace_count`, `monthly_contributors_count`, `server_editors_count`), `AbstractProjectHandler` (l.189), `WorkspaceRole` GUEST<READER<EDITOR<WRITER<ADMIN<OWNER (l.204).
- CE: `sync/workspace.py` `GlobalWorkspace` (id=1, roles from `GLOBAL_READ/WRITE/ADMIN`) and `GlobalWorkspaceHandler` (extra methods used by controllers: `filter_projects`, `projects_query`, `update_project_members`, `access_requests_query`, `project_access`, `server_editors_count`, `sso_connections_count() -> 0`).
- Storage quota: `StorageLimitHit` vs `ws.storage` (= `GLOBAL_STORAGE`).

## Frontend (`web-app/`, Vue 3 + Pinia + PrimeVue + Vite)

- Packages: `lib`, `admin-lib`, thin shells `app` and `admin-app`.
- Template slots usable for EE: `AppHeaderTemplate` (`invitationsIcon`), `SideBarTemplate` (`dashboard_logo_url` branding, dormant), `ProjectViewTemplate` (`map.tab` → web map), `LoginViewTemplate` (`additionalButtons` → SSO button), `ProjectCollaboratorsViewTemplate`, `ProjectShareDialogTemplate`, `FullStorageWarningTemplate`, admin `SettingsViewTemplate`.
- Types already invitation/workspace-aware (`project/types.ts:366-377`, `instance/types.ts:20 serverType`).

## deployment/enterprise (hints of EE components)

- EE images (proprietary, not usable): backend-ee, frontend-ee.
- SSO: `boxyhq/jackson` (SAML/OIDC bridge). Env: `SSO_ENABLED`, `SSO_SERVER_URL`, `SSO_SERVER_API_KEY`, `SSO_SERVER_API_URL`, `SSO_SERVER_INTERNAL_URL`, `SSO_SESSION_EXPIRATION`, `SSO_SERVER_PRODUCT_ID`.
- Maps: QGIS Server (WMS) + `qgis-extractor` celery worker (queue `extractor`), overviews volume. Env: `MAPS_ENABLED`, `OVERVIEW_DATA`, `VECTOR_TILES_URL`, `VECTOR_TILES_STYLE_URL`, `WMTS_SERVER_URL`, `OVERVIEW_MAX_FILE_SIZE`.
- Workspaces: `WORKSPACE_STORAGE_SIZE`, `WORKSPACE_INVITATION_EXPIRATION`, `PROJECT_TRANSFER_EXPIRATION`, `WORKSPACE_EXPIRATION`, `USER_WORKSPACES_ALLOWED`, `ORGANISATION_INVITATION_EXPIRATION`, `TRANSFER_EXPIRATION`.
- `LICENSES/EE-used-libs.json`: EE web map uses OpenLayers (`ol`, `ol-mapbox-style`, `geotiff`…); backend adds flask-caching, pydantic.

## Feature state in CE

| Feature | CE state |
|---|---|
| SSO (SAML/OIDC) | stubbed (nullable passwd, `sso_connections_count()=0`) |
| Webhooks | absent; signals available |
| Audit log | events + emit exist, sink is `NullSink` (no storage/API/UI) |
| Usage/statistics | exists (`/app/admin/usage`, `/app/admin/report`) |
| Storage quota | single global quota only |
| Branding | partial (`DASHBOARD_LOGO_URL` not exposed) |
| Web maps / WMS | absent (only `map.tab` slot) |
| Multi-workspace, invitations, project transfer | interfaces/types only |

## Tests / CI

- Backend: pytest (`server/pytest.ini`, `.test.env`, xdist per-worker DB), suites in `server/mergin/tests/`, migrations in `server/mergin/test_migrations/`.
- Frontend: no tests, only ESLint.
- CI: `auto_tests.yml` (server + migration, postgres:14), `code_style.yml` (black), `code_style_js.yml` (eslint).
