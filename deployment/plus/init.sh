#!/bin/bash
# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# First start: create database tables (Community and add-on), mark migrations as applied,
# create the superuser (its generated password is printed). Upgrades: docker compose run --rm server "flask db upgrade heads"
set -euo pipefail
cd "$(dirname "$0")"
EMAIL="${1:-$(grep -E '^CONTACT_EMAIL=' .prod.env | cut -d= -f2)}"
mkdir -p projects diagnostic_logs mergin_db
docker compose up -d db redis
sleep 5
docker compose run --rm server "flask init --email $EMAIL && flask db stamp heads"
