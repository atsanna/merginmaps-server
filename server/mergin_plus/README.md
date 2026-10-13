# mergin_plus

Open source reimplementation of features of the Mergin Maps Enterprise Edition, written from public documentation only (see [docs/enterprise](../../docs/enterprise)). Not affiliated with, sponsored or endorsed by Mergin Maps / Lutra Consulting.

It is an **add-on**: Community Edition files are never modified, so the fork can keep following upstream releases.
The add-on plugs into the CE application only through its extension points (`application.ws_handler` /
`application.project_handler`, extra Connexion APIs and blueprints, blinker signals, alembic version locations),
see [app.py](app.py). Its alembic migrations live in [migrations](migrations) and form the `enterprise` branch.

## Running

The add-on has its own entry point, which loads the unmodified CE `application.py` and registers the add-on.
Use it in place of the CE one; with the CE entry point the server is plain Community Edition.

```bash
gunicorn mergin_plus.wsgi:application
celery -A mergin_plus.wsgi.celery worker
celery -A mergin_plus.wsgi.celery beat
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `WORKSPACE_STORAGE_SIZE` | `GLOBAL_STORAGE` | Storage quota (bytes) of new workspaces |
| `WORKSPACE_EXPIRATION` | `7` | Days a closed workspace is kept before permanent removal |
| `USER_WORKSPACES_ALLOWED` | `true` | Regular users can create workspaces (otherwise superusers only) |
| `WORKSPACE_INVITATION_EXPIRATION` | `14` | Days a workspace invitation is valid |
| `WORKSPACE_CONTRIBUTORS_LIMIT` | `0` | Maximum contributors of new workspaces (`0` = unlimited) |
| `PROJECT_TRANSFER_EXPIRATION` | `7` | Days a project transfer request is valid |
| `AUDIT_LOG_ENABLED` | `true` | Store audit events in database |
| `AUDIT_LOG_RETENTION` | `365` | Days audit events are kept |
| `WEBHOOKS_ALLOW_PRIVATE_URLS` | `false` | Allow webhooks to private / loopback addresses |
| `WEBHOOKS_TIMEOUT` | `10` | Webhook request timeout (seconds) |
| `WEBHOOKS_MAX_FAILURES` | `20` | Consecutive failed deliveries disabling a webhook |
| `SSO_ENABLED` | `false` | Enable single sign-on |
| `SSO_SERVER_URL` | | Public URL of Ory Polis |
| `SSO_SERVER_API_URL` | `SSO_SERVER_URL` | Polis URL reachable from the server |
| `SSO_SERVER_API_KEY` | | Polis API key (one of its `JACKSON_API_KEYS`) |
| `SSO_SERVER_PRODUCT_ID` | `mergin-maps-product` | Polis product of the connections |
| `SSO_SESSION_EXPIRATION` | `1209600` | Lifetime (seconds) of tokens issued after SSO login |
| `SSO_TENANT_FLOW` | `multi` | `multi`: connection chosen by e-mail domain, `single`: `SSO_DEFAULT_TENANT` for everybody |
| `SSO_ALLOWED_REDIRECT_URIS` | QGIS (`http://localhost:10042/` …) and mobile app | Client redirect URI prefixes, comma separated |
| `MAPS_ENABLED` | `false` | Enable web maps |
| `OVERVIEW_DATA` | `<LOCAL_PROJECTS>/map_overviews` | Directory with versions prepared for QGIS Server (shared volume) |
| `QGIS_SERVER_DATA` | | Path of `OVERVIEW_DATA` inside the QGIS Server container, if different |
| `QGIS_SERVER_URL` | (`WMTS_SERVER_URL`) | QGIS Server OWS endpoint, e.g. `http://qgis-nginx/ows/` |
| `MAPS_BASEMAP_URL` | OpenStreetMap tiles | Default XYZ basemap of web maps |
| `MAPS_BASEMAP_ATTRIBUTION` | OpenStreetMap | Basemap attribution |
| `VECTOR_TILES_STYLE_URL` | | Optional vector tiles basemap style |
| `INSTANCE_NAME` | | Server name shown in the dashboard (`DASHBOARD_LOGO_URL` from CE is exposed too) |

With the add-on:
- `/config` reports `server_type: "ee"`, which QGIS plugin and mobile app need to show workspace features;
- usage statistics are never sent to Mergin Maps (`COLLECT_STATISTICS` is forced off).

## Database

Upgrade both branches (community first):

```bash
export FLASK_APP=mergin_plus.wsgi
flask db upgrade community@head
flask db upgrade enterprise@head
# or simply
flask db upgrade heads
```

On an existing Community Edition database the global workspace (`GLOBAL_WORKSPACE`, id 1) becomes a regular workspace with `GLOBAL_STORAGE` quota; superusers become its owners and, depending on `GLOBAL_ADMIN` / `GLOBAL_WRITE` / `GLOBAL_READ`, all active users become admins / writers / readers.

## API

| Endpoint | Description |
|---|---|
| `POST /v1/workspace` | Create workspace (`name`, `description`), caller becomes owner |
| `GET /v1/workspaces`, `GET /v1/workspace/{id}` | Provided by CE, backed by db workspaces |
| `PATCH /v1/workspace/{id}` | Update description (owner), name is immutable |
| `DELETE /v1/workspace/{id}` | Close workspace (owner), purged after `WORKSPACE_EXPIRATION` days |
| `GET /v1/workspace/{id}/usage` | Storage, projects, members and contributors count (admin) |
| `GET /v2/workspaces/{id}/members` | Workspace members (admin) |
| `GET/PATCH/DELETE /v2/workspaces/{id}/members/{user_id}` | Member detail, role change (`workspace_role` or `role`, `reset_projects_roles`), removal; members can remove themselves |
| `GET/POST /v2/workspaces/{id}/invitations` | List / create invitations (`email`, `role`, `projects` with `id` and `role`; guests need projects) (admin) |
| `POST /v2/projects/{id}/invitations` | Share project with an e-mail: existing users get direct access, others are invited as guests (pending invitation is extended) |
| `DELETE /v2/workspaces/{id}/invitations/{uuid}`, `POST .../resend` | Revoke / renew and resend invitation (admin) |
| `GET /v2/invitations`, `POST /v2/invitations/{uuid}/accept`, `.../decline` | Invitations of session user |
| `POST /v2/invitations/{uuid}/register` | Create account from invitation link, works with `USER_SELF_REGISTRATION=false` |
| `POST /v2/users` | CE endpoint, `workspace_id` and `role` now create the membership |
| `GET/POST /app/admin/workspaces` | Superuser: list (paginated, `like`, `order_params`) / create workspace |
| `GET/PATCH/DELETE /app/admin/workspaces/{id}` | Superuser: detail with members, update `storage` / `contributors_limit` / `active`, schedule removal |
| `POST /app/admin/workspaces/{id}/restore` | Superuser: cancel scheduled removal |
| `GET/POST /v2/projects/{id}/transfer` | Pending transfer / request transfer to workspace `workspace` (project owners, workspace admins) |
| `GET /v2/workspaces/{id}/transfers` | Incoming and outgoing transfers (admin) |
| `POST /v2/transfers/{id}/accept` | Target workspace admin moves the project, optional new `name`; checks name clash and storage |
| `DELETE /v2/transfers/{id}` | Decline (target admins) or cancel (source side) |
| `GET /app/admin/audit` | Superuser: audit events (filters `event_type` prefix, `workspace_id`, `project_id`, `actor_id`, `since`, `until`) |
| `GET /v2/workspaces/{id}/audit` | Workspace admins: audit events of the workspace |
| `GET/POST /v2/workspaces/{id}/webhooks` | Workspace admins: list / create webhook (`url`, `events` prefixes), secret returned on creation |
| `PATCH/DELETE /v2/workspaces/{id}/webhooks/{webhook_id}` | Update `url` / `events` / `active` / `regenerate_secret`, delete |
| `POST /v2/workspaces/{id}/webhooks/{webhook_id}/ping` | Send a test event |

## Limits

- Storage quota is per workspace (`WORKSPACE_STORAGE_SIZE` default, changed by superusers).
- Contributors are users who can change data: members with editor or higher role and users with editor or higher
  direct access to workspace projects. The contributors limit is checked on every database flush,
  so it also covers CE endpoints (project collaborators, access requests); requests adding a contributor
  over the limit get `422 ContributorsLimitHit`. Changes not adding contributors are always allowed.

## Audit log and webhooks

The add-on replaces the CE audit `NullSink`: every audit event (CE ones like `user.login.succeeded`,
`project.version.created`, `project.member.added`, and add-on ones like `workspace.member.updated`,
`workspace.invitation.created`, `project.transfer_request.accepted`) is stored in `audit_log`.
Events of a workspace are also POSTed to its matching webhooks as JSON, with headers `X-Webhook-Event`,
`X-Webhook-Delivery` and `X-Webhook-Signature: sha256=<HMAC-SHA256 of the body with the webhook secret>`.

## Single sign-on

SSO connections (SAML or OIDC) are configured in [Ory Polis](https://github.com/ory/polis) (open source, Apache-2.0)
with **tenant = e-mail domain** (e.g. `acme.com`) and **product = `SSO_SERVER_PRODUCT_ID`**; the allowed redirect URL
of the connections is `<MERGIN_BASE_URL>/v2/sso/callback`. Users are created on their first SSO login (no password).

| Endpoint | Description |
|---|---|
| `GET /v2/sso/config` | `tenant_flow_type` (`multi`/`single`) and `client_id` for single tenant |
| `GET /v2/sso/connections?email=` | OAuth `id` (client id) for the e-mail domain, 404 without SSO connection |
| `GET /v2/sso/authorize` | OAuth 2.0 authorization endpoint for clients (code flow, PKCE S256 required) |
| `POST /v2/sso/token` | OAuth 2.0 token endpoint, returns a Mergin bearer token as `access_token` |
| `GET /v2/sso/login?email=&next=` | Dashboard sign in (session cookie) |
| `GET /v2/sso/callback` | Redirect target of Polis |

## Web maps

With `MAPS_ENABLED`, every new project version with a QGIS project file (`.qgs`/`.qgz` in the project root)
is processed by a Celery task: the files of the version are hard-linked (or copied) to
`OVERVIEW_DATA/<project id>/v<version>` and the QGIS project is read without QGIS libraries
(layers, layer tree, map themes, extent, whether layer data are packaged in the project).
QGIS Server (upstream `qgis/qgis-server` image) renders the maps from that directory.

| Endpoint | Description |
|---|---|
| `GET /v2/projects/{id}/map` | Map configuration (layers, tree, themes, extent, basemap, `wms_url`), 404 "Map config does not exist" |
| `POST /v2/projects/{id}/map/refresh` | Process latest version again (writers) |
| `GET /v2/projects/{id}/map/wms` | WMS proxy (GetMap, GetLegendGraphic, GetFeatureInfo, GetCapabilities) with project read permission |
| `GET/PUT/DELETE /v2/projects/{id}/map/link` | Public map link (project owners, workspace admins): create, `ogc_enabled`, `regenerate`, remove |
| `GET /v2/maps/{token}` | Map configuration for anyone with the link (dashboard page `/maps/{token}`, embeddable) |
| `GET /v2/maps/{token}/wms` | WMS of the shared map |
| `GET /v2/maps/{token}/ogc` | Read-only OGC services when enabled: WMS and WFS (GetCapabilities, DescribeFeatureType, GetFeature) |

## Roles

- Only owners can grant, change or remove the owner role; a workspace always keeps at least one owner.
- Guests are users without membership who have direct access to some workspace project.
- Editors can push data changes only: they can not add, update or remove `*.qgs`, `*.qgz` and `mergin-config.json`,
  can update geopackages only with diffs and can not remove geopackages.

## Tests

```bash
pytest mergin_plus/tests                       # package tests
pytest mergin_plus/test_migrations             # enterprise migration branch
python -m pytest -p mergin_plus.ce_suite mergin/tests   # unmodified CE suite on the add-on
```
