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
