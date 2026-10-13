# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import JSONB

from mergin.app import db


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SsoGrant(db.Model):
    """Short-lived one-time SSO secrets: login requests in progress ("state") and authorization codes ("code").
    Only hashes of the tokens are stored.
    """

    __tablename__ = "sso_grant"

    token_hash = db.Column(db.String(64), primary_key=True)
    kind = db.Column(db.String(16), nullable=False)
    data = db.Column(JSONB, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    @classmethod
    def create(cls, kind: str, data: dict, ttl: int) -> str:
        """Store grant and return its secret token, does not commit"""
        token = secrets.token_urlsafe(32)
        db.session.add(
            cls(
                token_hash=_hash(token),
                kind=kind,
                data=data,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl),
            )
        )
        return token

    @classmethod
    def consume(cls, kind: str, token: Optional[str]) -> Optional[dict]:
        """Return data of valid grant and remove it (one-time use), does not commit.
        A single DELETE ... RETURNING makes concurrent use of the same token impossible.
        """
        if not token:
            return None
        row = db.session.execute(
            delete(cls)
            .where(cls.token_hash == _hash(token), cls.kind == kind)
            .returning(cls.data, cls.expires_at)
        ).first()
        if not row or row.expires_at < datetime.utcnow():
            return None
        return row.data
