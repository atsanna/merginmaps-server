# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# Dashboard and admin panel with the add-on (plus-app, plus-admin-app).
# Same steps as the Community Edition web-app/Dockerfile, different packages.
# Build context: web-app/

FROM node:22-alpine AS builder
COPY . /mergin/web-app
WORKDIR /mergin/web-app
RUN yarn install --frozen-lockfile
RUN yarn link:dependencies
RUN yarn build:libs:prod
RUN yarn workspace @mergin/plus-app build
RUN PUBLIC_PATH=/admin/ yarn workspace @mergin/plus-admin-app build

FROM nginxinc/nginx-unprivileged:1.27
WORKDIR /usr/share/nginx/html
COPY --from=builder /mergin/web-app/packages/plus-app/dist ./app
COPY --from=builder /mergin/web-app/packages/plus-admin-app/dist ./admin
COPY ./nginx.proxy.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
