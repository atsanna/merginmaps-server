# mergin_plus

Open source reimplementation of features of the Mergin Maps Enterprise Edition, written from public documentation only (see [docs/enterprise](../../docs/enterprise)). Not affiliated with, sponsored or endorsed by Mergin Maps / Lutra Consulting.

The package plugs into the Community Edition application through its extension points:
it replaces `application.ws_handler` with workspaces stored in database, adds its own API and an alembic `enterprise` migration branch.
Without `ENTERPRISE_ENABLED` nothing is loaded and the server behaves exactly as Community Edition.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ENTERPRISE_ENABLED` | `false` | Enable the package |
| `WORKSPACE_STORAGE_SIZE` | `GLOBAL_STORAGE` | Storage quota (bytes) of new workspaces |
| `WORKSPACE_EXPIRATION` | `7` | Days a closed workspace is kept before permanent removal |
| `USER_WORKSPACES_ALLOWED` | `true` | Regular users can create workspaces (otherwise superusers only) |
| `WORKSPACE_INVITATION_EXPIRATION` | `14` | Days a workspace invitation is valid |

With the package enabled:
- `/config` reports `server_type: "ee"`, which QGIS plugin and mobile app need to show workspace features;
- usage statistics are never sent to Mergin Maps (`COLLECT_STATISTICS` is forced off).

## Database

Upgrade both branches (community first):

```bash
ENTERPRISE_ENABLED=1 flask db upgrade community@head
ENTERPRISE_ENABLED=1 flask db upgrade enterprise@head
# or simply
ENTERPRISE_ENABLED=1 flask db upgrade heads
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
| `GET/POST /v2/workspaces/{id}/invitations` | List / create invitations (`email`, `role`) (admin) |
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
TEST_ENTERPRISE=1 pytest mergin/tests          # CE suite on db workspaces
```
