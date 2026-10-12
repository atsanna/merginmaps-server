# Enterprise features — work plan

Plan to bring the self-hosted Enterprise Edition capabilities listed in [ee-features.md](ee-features.md) into this open-source fork, building on the extension points in [ce-inventory.md](ce-inventory.md).

**Ground rules**

- Clean-room: everything is written from **public documentation and the public CE code**. No proprietary EE code, images (`*-ee`) or hosted Mergin services (e.g. `tiles-ee.merginmaps.com`) are used.
- Same licence as CE (AGPL-3.0).
- **Client compatibility first**: QGIS plugin, mobile app and `python-api-client` already speak the EE API. Where public docs or the public client describe an endpoint, we match its path and payload so existing clients work unchanged.
- CE behaviour stays the default: every feature sits behind a config flag and the CE test suite must keep passing.

## 1. Gap analysis

| # | Feature | CE today | Target | Priority |
|---|---|---|---|---|
| 1 | Multiple workspaces | interfaces only, `GlobalWorkspaceHandler` | real `Workspace` table + handler, create/close/switch | **foundation** |
| 2 | Workspace roles (guest…owner) | global `GLOBAL_*` flags | per-user workspace role, multiple owners | foundation |
| 3 | Members & invitations | none | invitations with expiry/resend, members API, guests | high |
| 4 | Editor role restrictions | role exists at project level | enforce file rules (no `.qgs/.qgz/mergin-config.json`, no non-diff `.gpkg`) — check what CE already enforces | high |
| 5 | Per-workspace storage & seat limits | global `GLOBAL_STORAGE` | per-workspace quota, contributor cap, admin override | high |
| 6 | Admin "Workspaces" tab | none | list/detail/limits/(de)activate/delete/create | high |
| 7 | Project transfer | none | request → accept/decline, expiry | medium |
| 8 | SSO SAML/OIDC | stubs | Ory Polis (open source) bridge, domain routing, JIT users | medium |
| 9 | Web maps | `map.tab` slot only | QGIS Server + own extractor worker + OpenLayers map tab | medium (largest) |
| 10 | Audit log viewer | events → `NullSink` | DB sink + admin API/UI (*not documented for EE — fork extra*) | low |
| 11 | Webhooks | signals only | outgoing webhooks per workspace (*fork extra*) | low |
| 12 | Branding | `MERGIN_LOGO_URL`, dormant `DASHBOARD_LOGO_URL` | expose dashboard logo/name (*fork extra*) | low |
| 13 | Map links / embed / OGC API | none | *Cloud early-access only — optional, last* | optional |

Out of scope: mandatory telemetry, SaaS billing/subscriptions, Mergin-hosted basemaps and support services.

## 2. Architecture

### Backend

- New Python package **`server/mergin_ee/`** (name to confirm), an *app extension* registered on top of `mergin.create_app`:
  - replaces `application.ws_handler` / `application.project_handler` (`server/mergin/app.py` ~438) with `WorkspaceHandler` / `ProjectHandler` implementations backed by real tables;
  - registers its own Connexion API specs (`/v1/workspace*`, `/v2/workspaces/*`, `/app/...` private endpoints, admin endpoints);
  - plugs into CE signals (`project_access_granted`, `push_finished`, `project_version_created`, `user_created`, `user_account_closed`…) for e-mails, maps, audit, webhooks;
  - adds Celery tasks to the existing beat schedule (expired invitations/transfers, closed workspace purge, overview generation).
- Activation: `ENTERPRISE_ENABLED=true` (or `SERVER_TYPE=ee`, see open question Q1) in `server/application.py`; with it off, the package is not loaded and the server is pure CE.
- Database: Alembic **`enterprise` branch** on top of `community` (already supported by `alembic.ini` `version_locations`). First migration creates `workspace` for every existing `project.workspace_id` (the global workspace id=1 becomes a real row), then adds the FK.
- Minimal, upstream-friendly patches to CE only where a hook is missing (each one listed in the PR and kept small so upstream merges stay easy).

### Frontend

- New package **`web-app/packages/ee-lib`** with views/stores/components, consumed by `app` and `admin-app` shells.
- Fill the existing slots: `AppHeaderTemplate.invitationsIcon` (workspace switcher + invitations), `LoginViewTemplate.additionalButtons` (SSO), `ProjectViewTemplate` `map.tab` (web map), `ProjectCollaboratorsViewTemplate` / `ProjectShareDialogTemplate` (guests, invitations), `FullStorageWarningTemplate`, admin `SettingsViewTemplate`; new routes through `RouteOverrides`.
- Behaviour switches on `server_type` / feature flags returned by `GET /config`.

### Deployment

- `deployment/enterprise-oss/` (name TBD) with `docker-compose.yml` using **images built from this repo**, plus optional `docker-compose.sso.yml` (Ory Polis, Apache-2.0) and `docker-compose.maps.yml` (upstream `qgis/qgis-server` + our extractor worker).

## 3. Milestones

Ordered by dependency; each milestone is one or more PRs, merged only with green CI.

### M0 — Foundations
- Package skeleton, `ENTERPRISE_ENABLED` flag, app-extension registration, `enterprise` Alembic branch (empty head), test fixtures running the suite in both CE and EE modes, `ee-lib` frontend package wired into the shells.
- CI: run `auto_tests` twice (CE mode, EE mode) + migration test for the `enterprise` branch.
- **Done when**: CE tests green in both modes; `flask db upgrade enterprise@head` works on a fresh and on an existing CE DB.

### M1 — Workspaces core
- Models `Workspace` (name immutable, description, storage, active, soft-delete timestamp) and `WorkspaceMember` (user, role).
- `WorkspaceHandler` implementation: `get`, `get_by_name`, `list_user_workspaces`, `filter_projects`, `projects_query`, `project_access`, counts used by stats.
- Migration of the global workspace and of `GLOBAL_READ/WRITE/ADMIN` into member rows.
- API: `GET /v1/workspaces`, `POST /v1/workspace`, `GET /v1/workspace/{id}`, `GET /v1/workspace/{id}/service`, `GET /v1/workspace/{id}/usage`; edit description; close (soft delete) + purge task after `WORKSPACE_EXPIRATION`; `USER_WORKSPACES_ALLOWED`.
- Roles matrix from ee-features.md §3 enforced in project create/delete/access endpoints; multiple owners, "last owner" protection.
- UI: workspace switcher (recent), Manage workspaces page, Workspace settings tab, close dialog.
- **Tests**: handler unit tests, role-matrix parametrized tests, API tests, migration test, purge task test, python-api-client smoke test (`workspaces_list`, `create_workspace`).

### M2 — Members, guests, invitations
- Model `WorkspaceInvitation` (email lower-cased, role, projects for guests, inviter, expires).
- API: `POST /v2/workspaces/{id}/invitations`, members `GET/PATCH/DELETE /v2/workspaces/{id}/members[/{user_id}]` (`role`, `reset_projects_roles`), accept/decline/resend/delete invitations, `list_user_invitations`; `POST /v2/users` honours `workspace_id`/`workspace_role`.
- Registration through an invitation even if `USER_SELF_REGISTRATION=false`; `WORKSPACE_INVITATION_EXPIRATION`; e-mail templates; sharing a project with a non-member creates a guest invitation.
- Editor role restrictions on push (verify existing CE checks first).
- UI: Members tab (table, sidebar with `last_signed_in`, contributor vs read-only), invitation notifications in header.
- **Tests**: invitation lifecycle incl. expiry and case-insensitive match, guest visibility, editor push rules, e-mail rendering.

### M3 — Quotas and admin Workspaces tab
- Per-workspace storage (`WORKSPACE_STORAGE_SIZE` default) and contributor limit; enforce on push and on member/role changes (`StorageLimitHit` path already exists); exclude projects scheduled for deletion.
- Admin API + `admin-app` Workspaces tab: list/sort/search, detail with members, update limits, activate/deactivate, delete (scheduled), create by name.
- **Tests**: quota enforcement on push, seat limit on invite/role change, admin endpoints permission tests.

### M4 — Project transfer
- Model `ProjectTransferRequest`, `PROJECT_TRANSFER_EXPIRATION`; request by admin/owner or project owner; accept/decline by target workspace owner/admin; move project (storage path, collaborators reset policy), notifications, expiry task.
- UI: Transfer section in project settings, incoming requests in target workspace.
- **Tests**: full lifecycle, permission checks, quota check on target, name clash in target workspace.

### M5 — SSO (SAML/OIDC)
- Integration with **Ory Polis** via `SSO_*` env vars: discover connection by e-mail domain (tenant) and product id, OAuth code flow, JIT user creation (no password), session lifetime `SSO_SESSION_EXPIRATION`.
- Client flows: dashboard "Continue with SSO", and the callback URLs used by mobile/QGIS (`http://localhost:10042` etc.) — needs study of the public QGIS plugin / mobile code to match the exact exchange.
- Admin link "SSO Administration"; `sso_connections_count()` real value; workspace settings section.
- **Tests**: mocked Polis server (unit), docker-compose integration test with Polis + a test OIDC IdP (e.g. Keycloak / mock-oauth2-server) in a separate CI job.

### M6 — Web maps
- Our own extractor worker (Celery queue `extractor`): on `project_version_created` read the QGIS project with PyQGIS, produce an "overview" (layer list, legend, themes, extent, packaged-data-only layer filter) in `OVERVIEW_DATA`, table `map_overview`.
- QGIS Server (upstream image) serving WMS/WMTS from the overview's QGIS file; nginx; backend proxy with permission checks.
- Frontend map tab with OpenLayers: layers panel, legend, themes, basemap selection (**open default**, e.g. OSM or a configurable `VECTOR_TILES_URL`), auto-refresh, feature identify → attribute form.
- **Tests**: extractor unit tests on sample QGIS projects (fixtures in repo), API/permission tests, maps CI job with QGIS Server container.

### M7 — Fork extras (beyond documented EE)
- Audit log: DB sink, retention, admin + workspace API/UI.
- Webhooks: per-workspace endpoints, signed payloads (HMAC), retries via Celery, events from CE signals.
- Branding: expose `DASHBOARD_LOGO_URL`, instance name.
- Optional: public map links / embed / OGC API (Cloud early-access features).

## 4. Testing strategy

- Backend: pytest, reuse CE fixtures; every feature ships unit + API tests and an Alembic migration test; CE suite runs in CE and EE mode.
- Frontend: add Vitest for `ee-lib` stores/components (CE has none today), keep ESLint.
- Compatibility: CI job using the public `mergin-client` (python-api-client) against the server for workspace/member/invitation endpoints.
- Integration jobs (SSO, maps) separate and allowed to run only on relevant path changes.

## 5. Open questions (need your decision)

1. **Edition flag**: report `server_type: "ee"` on `/config` (needed for QGIS plugin / mobile to show workspace UI) or a new value (e.g. `"ee-oss"`) and accept that clients may hide features? Reporting `ee` could confuse users and Mergin's support/telemetry.
2. **Telemetry**: keep CE's optional statistics but **disable by default** in EE mode, so this fork never reports itself to Mergin as an Enterprise install?
3. **Package name / branding**: `mergin_ee` vs a neutral name (e.g. `mergin_plus`) to avoid confusion with the commercial product name.
4. **Fork extras (M7)**: include audit log / webhooks / branding, or keep strictly to documented EE features?
5. **Web maps basemap default**: OSM raster tiles (with attribution), or require the admin to configure one?
6. **Branch workflow**: one PR per milestone into `main`, or longer-lived feature branches?
7. **Upstream sync**: how often to merge from `MerginMaps/server` (their sync-API rewrite is in progress and may move the hooks).
