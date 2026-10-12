# Mergin Maps Enterprise Edition — features missing from Community Edition

Research snapshot (2026-10-12) of what the self-hosted **Enterprise Edition (EE)** offers beyond **Community Edition (CE)**, compiled only from **public** sources: the documentation source repository `MerginMaps/docs` (release 2026.10.0), the public `MerginMaps/server` repository (`deployment/`, CE code), GitHub release notes, the public Python client, and search snippets of merginmaps.com pages (the website itself was not reachable from the research environment).

No proprietary code or EE images were inspected. This document describes **behaviour**, to support an independent clean-room reimplementation.

Legend: **[Doc]** stated by public docs/release notes · **[Inf]** inferred from config, deployment files or CE code shape.

## 0. Editions

- EE variants: Cloud (app.merginmaps.com), Private-Cloud, On-Premises. CE is AGPL-3.0 (or commercial); EE under a commercial licence. [Doc]
- Edition flag `SERVER_TYPE` = `ce` | `ee`, exposed as `server_type` on `GET /config` and in `flask server check`. [Doc]
- EE adds its own Alembic branch: upgrades run `flask db upgrade community@<rev>` then `enterprise@<rev>`. Known EE table: `map_overview` (id, project_id, version, config JSON, data_location, qgis_file). [Doc]
- EE licence makes telemetry mandatory. **Out of scope** for this fork: it is a contractual term, not a feature. [Doc]

## 1. Multiple workspaces

- CE: a single global workspace (`GLOBAL_WORKSPACE`, `GLOBAL_STORAGE`). [Doc]
- EE: users create and own many workspaces (name + description). Name is **immutable** after creation. `USER_WORKSPACES_ALLOWED=false` restricts creation to superusers. [Doc]
- Workspace switcher in the dashboard header (recently viewed), in mobile and QGIS plugin. [Doc]
- "Manage workspaces" page: list workspaces where the user is guest/member/owner; create, leave, accept/decline invitations. [Doc]
- Settings tab: admins/owners see SSO and early-access toggles; owners can edit description and **close** the workspace (type name to confirm). [Doc]
- Closing = soft delete with its projects; purged after `WORKSPACE_EXPIRATION` days (default 7). [Doc]
- API (public Python client): `GET /v1/workspaces`, `POST /v1/workspace {name}`, `GET /v1/workspace/{id}/service`, `GET /v1/workspace/{id}/usage`. [Doc]
- CE partial: `AbstractWorkspace` / `WorkspaceHandler` interfaces exist; only `GlobalWorkspaceHandler` is implemented.

## 2. Members, guests, invitations

- **Members** see all workspace projects at their role; **guests** only see projects explicitly shared with them. [Doc]
- Invite: emails + role (guest/reader/editor/writer/admin/owner); guests also get a project list. Email link + dashboard notification for existing users. [Doc]
- Expiry `WORKSPACE_INVITATION_EXPIRATION` (days; docs say default 14). Expired invitations can be deleted, pending ones resent. Case-insensitive email matching. Invitees may register even when `USER_SELF_REGISTRATION=false`. [Doc]
- Members tab (admins/owners): email, username, name, role, contributor vs read-only, pending invites; change role, resend, remove; sidebar with `last_signed_in`. [Doc]
- Sharing a project with a non-member makes them a workspace guest; sharing can extend an existing invitation. [Doc]
- API (server ≥ 2025.2, "Cloud and EE"):
  - `POST /v2/workspaces/{id}/invitations`
  - `GET /v2/workspaces/{id}/members`
  - `GET|PATCH|DELETE /v2/workspaces/{id}/members/{user_id}` (`PATCH`: `role`, `reset_projects_roles`)
  - `POST /v2/users` accepts `workspace_id`, `workspace_role` (ignored by CE). [Doc]

## 3. Roles and permissions

| Capability | Reader | Editor | Writer | Admin | Owner |
|---|---|---|---|---|---|
| See all projects, data, history | ✓ | ✓ | ✓ | ✓ | ✓ |
| Add/edit/delete features | | ✓ | ✓ | ✓ | ✓ |
| Change layers, QGIS project settings | | | ✓ | ✓ | ✓ |
| Create projects | | | | ✓ | ✓ |
| Delete / transfer projects | | | | ✓ | ✓ |
| Manage project access and members | | | | ✓ | ✓ |
| Configure SSO | | | | ✓ | ✓ |
| Close workspace, edit description | | | | | ✓ |

- Multiple owners allowed; at least one must remain. [Doc]
- Project roles (reader/editor/writer/owner) can **raise** a member's workspace role on a single project. [Doc]
- Editor restrictions: cannot touch `*.qgs`, `*.qgz`, `mergin-config.json`; cannot make non-diff `.gpkg` changes or delete `.gpkg`. [Doc]
- **Contributors** = members/guests with editor+ access; readers unlimited. Drives seat limits. [Doc]
- CE: global `GLOBAL_READ/WRITE/ADMIN` flags + per-project collaborators and access requests. [Doc]

## 4. Project transfer between workspaces

- Admin/owner or project owner requests transfer to a target workspace by name; the target owner accepts/declines in the dashboard; collaborators re-download afterwards. [Doc]
- Expiry `PROJECT_TRANSFER_EXPIRATION` (days, default 7). A `ProjectTransferRequest` entity exists. [Doc]

## 5. Single sign-on (SAML / OIDC)

- Separate stack running **Ory Polis** (ex BoxyHQ Jackson) as SAML/OIDC bridge, own DB schema, proxied on port 8081. [Doc]
- Env: `SSO_ENABLED`, `SSO_SERVER_URL`, `SSO_SERVER_API_KEY`, `SSO_SERVER_API_URL`, `SSO_SERVER_INTERNAL_URL`, `SSO_SESSION_EXPIRATION` (default 14 days), `SSO_SERVER_PRODUCT_ID` (default `mergin-maps-product`). [Doc]
- Connection setup in Polis admin (linked from Mergin admin "SSO Administration"); **tenant = email domain**; redirect URLs include the server URL and client callbacks `http://localhost:10042`, `http://127.0.0.1:10042`, `http://[::1]:10042`. [Doc]
- UX: "Continue with SSO" on login; works in dashboard, mobile, QGIS plugin; accounts created (JIT) on first login; removing a user at the IdP does not end the session. No SCIM. [Doc]
- CE: `User.passwd` nullable, `sso_connections_count() = 0`.

## 6. Server admin panel — EE additions

- Shared with CE: overview, accounts, projects, settings, usage report. [Doc]
- EE-only **Workspaces tab**: list/sort/search, detail with members, **update limits** (storage + contributor caps), activate/deactivate, delete (scheduled), create by name. [Doc]
- EE-only **SSO Administration** link. [Doc]

## 7. Per-workspace quotas

- `WORKSPACE_STORAGE_SIZE` = default quota for new workspaces (latest version only counts); admin override per workspace; contributor (seat) limit per workspace; projects scheduled for deletion don't count. Usage at `/v1/workspace/{id}/usage`. [Doc]
- CE: single `GLOBAL_STORAGE`, no seat limit.

## 8. Web maps

- Project "Map" tab (EE 2025.3.0): project layers over a basemap, only packaged data (GPKG, SHP, MBTiles, GeoTIFF), legend + visibility, **map themes** switcher, custom raster/vector basemaps, extent from QGIS project, auto-refresh on new versions, feature click → attribute form. [Doc]
- Deployment: QGIS Server (FastCGI) + nginx + a Celery **extractor** worker (queue `extractor`) that turns each version into an "overview" in a shared volume; `finish_overview` task back on the main queue. [Doc]
- Env: `MAPS_ENABLED`, `OVERVIEW_DATA`, `VECTOR_TILES_URL`, `VECTOR_TILES_STYLE_URL`, `WMTS_SERVER_URL`, `OVERVIEW_MAX_FILE_SIZE`. [Doc]
- The default EE basemap is a hosted Mergin service → **not usable** here; the fork must default to an open basemap (e.g. OSM / self-hosted tiles).
- Cloud early-access only (not promised for EE): public map links, iframe embed, `map-script.js` apps, OGC services (WMS/WMTS/WFS/OGC API Features). [Doc]

## 9. Not documented for EE (verify before building)

- **Audit log UI/API**: CE emits audit events to a `NullSink`; no public doc of an EE viewer. [Inf]
- **Webhooks**: no public documentation for any edition.
- **Branding**: only `MERGIN_LOGO_URL` (both editions); custom branding/domain is a SaaS contract item.
- Email notifications for invitations, transfers, access requests are implied by the flows above. [Inf]
- Redis Sentinel hints in the EE env template (`BROKER_TRANSPORT_OPTIONS master_name`). [Inf]

## 10. Summary

| Feature | CE | EE self-hosted |
|---|---|---|
| Workspaces | 1 global | many, user-created (configurable) |
| Invitations | no | email, expiry, resend, API |
| Workspace member API | no | `/v2/workspaces/{id}/members` |
| Roles | global flags | guest/reader/editor/writer/admin/owner per user |
| Per-project permissions | yes | yes + guests |
| Project transfer | no | request/accept with expiry |
| SSO SAML/OIDC | no | yes, via Ory Polis, routed by email domain |
| Admin workspaces tab + limits | no | yes |
| Storage quota | global | per workspace + override |
| Seat limits | no | per workspace |
| Web maps | no | QGIS Server + extractor |
| Map sharing / embed / OGC | no | Cloud early access only |
| Audit log | null sink | not documented |
| Webhooks | no | not documented |

## Sources

- Docs (source of merginmaps.com/docs): https://github.com/MerginMaps/docs — `src/server/**` (install/ee, environment, administer, dashboard, sso-deployment, upgrade), `src/manage/**` (workspaces, permissions, project-advanced, sso, dashboard-maps, webmaps-*), `src/dev/integration`, `src/misc/licensing`; releases https://github.com/MerginMaps/docs/releases
- Server: https://github.com/MerginMaps/server — README, `deployment/enterprise/*` (`.env.template`, `docker-compose*.yml`, `sso/`), `server/mergin/sync/{workspace.py,interfaces.py}`, `server/mergin/audit/`; releases https://github.com/MerginMaps/server/releases
- Python client: https://github.com/MerginMaps/python-api-client/blob/master/mergin/client.py
- Search snippets only: https://merginmaps.com/pricing, https://merginmaps.com/pricing-for-ce-and-ee, https://merginmaps.com/enterprise-features, https://merginmaps.com/blog/introducing-mergin-maps-community-and-enterprise-editions, https://wishlist.merginmaps.com/changelog/webmaps-now-available-for-self-hosted-enterprise-users
