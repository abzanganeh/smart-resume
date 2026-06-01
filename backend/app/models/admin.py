"""SQLAlchemy ORM models for the admin domain (Step 35 / IMPLEMENTATION_PLAN section 8.4).

Mirrors the schemas in:
- ``docs/SYSTEM_DESIGN_PHASE_2.md`` section 19.7 (AdminUser, FeatureFlag,
  Announcement) and the harder rules in IMPLEMENTATION_PLAN section 8.4.

All Postgres ENUM types listed below are owned by Alembic migration
``0013_admin``; ``create_type=False`` keeps the model layer from trying
to (re)create them.

The ``admin_audit_log`` table itself is declared in
``app.models.billing`` because the billing layer needed to write
``stripe_event_needs_review`` audit rows from Step 6.  We re-export it
from this module for convenience so admin handlers can ``from
app.models.admin import AdminAuditLog``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.billing import AdminAuditLog  # re-exported below


# ---------------------------------------------------------------------------
# Enums (DDL owned by 0013_admin)
# ---------------------------------------------------------------------------


class AdminRole(str, enum.Enum):
    """Role membership for an admin user (section 8.4.1).

    Names use the snake_case values that match the Postgres ENUM
    members.  The IMPLEMENTATION_PLAN spells them ``super-admin`` and
    ``support-agent`` in prose; we use snake_case at the type-system
    boundary because Postgres enum values cannot contain hyphens
    without quoting and downstream JSON contracts already use the
    snake_case spellings.
    """

    super_admin = "super_admin"
    admin = "admin"
    support_agent = "support_agent"
    read_only_analyst = "read_only_analyst"


class AnnouncementSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"
    maintenance = "maintenance"


class AnnouncementAudience(str, enum.Enum):
    all = "all"
    subscribed = "subscribed"
    admin = "admin"


class FeatureFlagVisibility(str, enum.Enum):
    public = "public"
    internal = "internal"


def _pg_enum(py_enum: type[enum.Enum], name: str) -> PGEnum:
    return PGEnum(
        py_enum,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


_ADMIN_ROLE_PG = _pg_enum(AdminRole, "admin_role")
_ANNOUNCEMENT_SEVERITY_PG = _pg_enum(AnnouncementSeverity, "announcement_severity")
_ANNOUNCEMENT_AUDIENCE_PG = _pg_enum(AnnouncementAudience, "announcement_audience")
_FEATURE_FLAG_VISIBILITY_PG = _pg_enum(FeatureFlagVisibility, "feature_flag_visibility")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# AdminUser
# ---------------------------------------------------------------------------


class AdminUser(Base):
    """One row per admin operator.

    Differences from ``app.models.user.User``:

    - role is an admin role (not a tier).
    - 2FA is mandatory: ``totp_secret`` becomes non-null and
      ``totp_recovery_codes`` becomes a 10-element list at first login.
    - ``must_change_password`` and ``must_enroll_2fa`` gate access to
      anything beyond the bootstrap-completion endpoints.
    - There is no email-verification surface; admin email is set by
      bootstrap or by a super-admin invite and is trusted at insert.
    """

    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
    role: Mapped[AdminRole] = mapped_column(
        _ADMIN_ROLE_PG, nullable=False, index=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    totp_secret: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    totp_recovery_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    must_enroll_2fa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_via: Mapped[str] = mapped_column(
        String(32), nullable=False, default="invite", server_default="invite"
    )
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    @property
    def is_suspended(self) -> bool:
        return self.suspended_at is not None

    @property
    def has_totp(self) -> bool:
        return self.totp_secret is not None and len(self.totp_recovery_codes) > 0


# ---------------------------------------------------------------------------
# AdminInvite
# ---------------------------------------------------------------------------


class AdminInvite(Base):
    """Single-use invite issued by a super-admin.

    The plaintext invite token only leaves the backend in the invite
    email.  We persist the SHA-256 hash so a leaked DB cannot mint a
    valid acceptance.  Acceptance flips ``accepted_at`` and binds the
    new admin user via ``accepted_admin_id``; revocation flips
    ``revoked_at``.
    """

    __tablename__ = "admin_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[AdminRole] = mapped_column(_ADMIN_ROLE_PG, nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    invited_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    @property
    def is_active(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > _utcnow()
        )


# ---------------------------------------------------------------------------
# FeatureFlag
# ---------------------------------------------------------------------------


class FeatureFlag(Base):
    """Admin-managed boolean toggle with optional rollout / allowlist.

    Resolution rules used by ``GET /api/feature-flags``:

    1. If ``visibility = internal`` -> excluded from the public response.
    2. ``blocklist_emails`` always wins (return ``enabled=False``).
    3. ``allowlist_emails`` always grants (return ``enabled=True``).
    4. Else: ``enabled AND user_id_hash % 100 < rollout_percent``.
    """

    __tablename__ = "feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    rollout_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    variant: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    allowlist_emails: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    blocklist_emails: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    visibility: Mapped[FeatureFlagVisibility] = mapped_column(
        _FEATURE_FLAG_VISIBILITY_PG,
        nullable=False,
        default=FeatureFlagVisibility.public,
        server_default=FeatureFlagVisibility.public.value,
    )
    updated_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "rollout_percent BETWEEN 0 AND 100",
            name="ck_feature_flags_rollout_pct",
        ),
    )


# ---------------------------------------------------------------------------
# Announcement
# ---------------------------------------------------------------------------


class Announcement(Base):
    """Admin-managed banner active inside ``[starts_at, ends_at]``."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_markdown: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    severity: Mapped[AnnouncementSeverity] = mapped_column(
        _ANNOUNCEMENT_SEVERITY_PG,
        nullable=False,
        default=AnnouncementSeverity.info,
        server_default=AnnouncementSeverity.info.value,
    )
    audience: Mapped[AnnouncementAudience] = mapped_column(
        _ANNOUNCEMENT_AUDIENCE_PG,
        nullable=False,
        default=AnnouncementAudience.all,
        server_default=AnnouncementAudience.all.value,
    )
    cta_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    cta_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "ends_at >= starts_at", name="ck_announcements_window"
        ),
    )


__all__ = [
    "AdminAuditLog",
    "AdminInvite",
    "AdminRole",
    "AdminUser",
    "Announcement",
    "AnnouncementAudience",
    "AnnouncementSeverity",
    "FeatureFlag",
    "FeatureFlagVisibility",
]
