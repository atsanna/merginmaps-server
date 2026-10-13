#!/bin/bash
# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# Build the images used by docker-compose.yml from this repository:
#   merginmaps-server-ce:local    unmodified Community Edition backend (server/Dockerfile)
#   merginmaps-server-plus:local  backend with the mergin_plus add-on
#   merginmaps-web-plus:local     dashboard and admin panel with the add-on
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAG="${TAG:-local}"
BUILD_HASH="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"

docker build -t "merginmaps-server-ce:$TAG" --build-arg BUILD_HASH="$BUILD_HASH" \
  -f "$ROOT/server/Dockerfile" "$ROOT/server"
docker build -t "merginmaps-server-plus:$TAG" --build-arg BASE_IMAGE="merginmaps-server-ce:$TAG" \
  -f "$ROOT/deployment/plus/server.Dockerfile" "$ROOT/server"
docker build -t "merginmaps-web-plus:$TAG" \
  -f "$ROOT/deployment/plus/web.Dockerfile" "$ROOT/web-app"
