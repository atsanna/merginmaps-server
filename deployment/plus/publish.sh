#!/bin/bash
# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# Tag and push the images built by build.sh to a registry.
# Usage: ./publish.sh <registry/namespace> <version>
#   ./publish.sh ghcr.io/atsanna 2026.10.0
#   ./publish.sh docker.io/myuser 2026.10.0
# Log in first (docker login ghcr.io / docker login). Also pushes the "latest" tag unless LATEST=false.
set -euo pipefail
if [ $# -ne 2 ]; then
  echo "Usage: $0 <registry/namespace> <version>" >&2
  exit 1
fi
PREFIX="${1%/}"
VERSION="$2"
TAG="${TAG:-local}"
for image in merginmaps-server-plus merginmaps-web-plus; do
  docker image inspect "$image:$TAG" >/dev/null || { echo "$image:$TAG not found, run ./build.sh first" >&2; exit 1; }
  targets=("$PREFIX/$image:$VERSION")
  [ "${LATEST:-true}" = "true" ] && targets+=("$PREFIX/$image:latest")
  for target in "${targets[@]}"; do
    docker tag "$image:$TAG" "$target"
    docker push "$target"
  done
done
