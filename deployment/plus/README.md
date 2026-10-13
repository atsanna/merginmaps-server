# Mergin Maps server with the open source enterprise add-on

Docker deployment of this fork with the `mergin_plus` add-on (see [server/mergin_plus](../../server/mergin_plus)).
Images are built locally from the repository; nothing is pulled from Mergin Maps registries.

| Image | Built from |
|---|---|
| `merginmaps-server-ce:local` | unmodified Community Edition `server/Dockerfile` |
| `merginmaps-server-plus:local` | `server.Dockerfile`: CE image + `mergin_plus` |
| `merginmaps-web-plus:local` | `web.Dockerfile`: `plus-app` (dashboard) and `plus-admin-app` (admin panel) |

## Quick start

```bash
cd deployment/plus
./build.sh                       # build the three images
cp .env.template .prod.env       # then replace every "fixme" (random secrets) and MERGIN_BASE_URL
mkdir -p projects diagnostic_logs && sudo chown -R 901:999 projects diagnostic_logs
./init.sh admin@example.com      # create tables, mark migrations as applied, create superuser (password is printed)
docker compose up -d
```

The dashboard is at `http://localhost:8080`, the admin panel at `http://localhost:8080/admin`.
Superusers create workspaces from the admin panel (or any user from *Manage workspaces*, see `USER_WORKSPACES_ALLOWED`).

Upgrades: rebuild the images, then `docker compose run --rm server "flask db upgrade heads"` and `docker compose up -d`.

## Web maps

```bash
# .prod.env: MAPS_ENABLED=true
docker compose -f docker-compose.yml -f docker-compose.maps.yml up -d
```

QGIS Server (official `qgis/qgis-server` image) reads the project versions prepared by the add-on in
`projects/map_overviews`. The default basemap is OpenStreetMap (`MAPS_BASEMAP_URL`); please respect the
[OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) or configure your own tiles.

## Single sign-on

```bash
cp .sso.env.template .sso.env    # set JACKSON_API_KEYS, NEXTAUTH_SECRET, NEXTAUTH_ADMIN_CREDENTIALS
# .prod.env: SSO_ENABLED=true, SSO_SERVER_API_KEY=<one of JACKSON_API_KEYS>, SSO_SERVER_URL=<public URL of Polis>
docker compose -f docker-compose.yml -f docker-compose.sso.yml up -d
```

In the Polis admin UI (`http://localhost:8081`) create SAML or OIDC connections with tenant = e-mail domain,
product = `mergin-maps-product` and redirect URL `<MERGIN_BASE_URL>/v2/sso/callback`.

## Notes

- `nginx.proxy.conf` of the web image and `../common/nginx.conf` listen on IPv4 and IPv6, as in the Community Edition;
  on hosts without IPv6 remove the `listen [::]:8080;` lines.
- Usage statistics are never sent to Mergin Maps by the add-on.
- Shared maps (`/maps/<token>`) can be embedded in other sites with an iframe. If you put the server behind a proxy
  sending `Content-Security-Policy: frame-ancestors 'self'` (like `../common/ssl-proxy.conf`), relax it for `/maps/`
  and `/v2/maps/`.
