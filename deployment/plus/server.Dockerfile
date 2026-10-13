# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
#
# Backend with the mergin_plus add-on. It extends the image built from the unmodified
# Community Edition Dockerfile (server/Dockerfile), see build.sh.
# Build context: server/

ARG BASE_IMAGE=merginmaps-server-ce:local
FROM ${BASE_IMAGE}

USER root
COPY --chown=root:root mergin_plus /app/mergin_plus
USER mergin

# default: API server with enterprise features (celery commands are set in docker-compose)
ENV FLASK_APP=mergin_plus.wsgi
CMD ["gunicorn --config config.py mergin_plus.wsgi:application"]
