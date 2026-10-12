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
