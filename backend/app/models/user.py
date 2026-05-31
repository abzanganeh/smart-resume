"""SQLAlchemy ORM models for the identity surface.

Mirrors the schemas defined in:
- SYSTEM_DESIGN_PHASE_2 §18.2 (User, RefreshToken)
- SYSTEM_DESIGN_PHASE_2 §19.7 (AuthAuditLog)
- SYSTEM_DESIGN_PHASE_2 §18.3 (CreditTransaction — registration grant only;
  full billing surface lands in Step 6 / migration 0002_billing)

These models intentionally use Postgres-specific types (JSONB, native ENUMs)
because the deployment target is Postgres + pgvector and the matching enums
are owned by ``alembic/versions/0001_base.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Python-side enums (kept in lockstep with the Postgres enums created in
# ``0001_base``).  ``create_type=False`` ensures SQLAlchemy never tries to
# create or drop the type implicitly — migrations are the source of truth.
# ---------------------------------------------------------------------------


class AuthProvider(str, enum.Enum):
    email = "email"
    google = "google"
    github = "github"


class UserTier(str, enum.Enum):
    free = "free"
    pro = "pro"


class AuthAuditEvent(str, enum.Enum):
    login_success = "login_success"
    login_failure = "login_failure"
    logout = "logout"
    password_reset = "password_reset"
    tfa_enroll = "2fa_enroll"
    tfa_disable = "2fa_disable"
    suspicious_login = "suspicious_login"
    account_locked = "account_locked"


class CreditTransactionAction(str, enum.Enum):
    registration_grant = "registration_grant"
    resume_build = "resume_build"
    ats_recalc = "ats_recalc"
    cover_letter = "cover_letter"
    section_regen = "section_regen"
    llm_upgrade_pack = "llm_upgrade_pack"
    llm_upgrade_pack_use = "llm_upgrade_pack_use"
    admin_grant = "admin_grant"
    admin_revoke = "admin_revoke"
    refund_reverse = "refund_reverse"


_AUTH_PROVIDER_PG = PGEnum(
    AuthProvider,
    name="user_auth_provider",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_USER_TIER_PG = PGEnum(
    UserTier,
    name="user_tier",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_AUTH_EVENT_PG = PGEnum(
    AuthAuditEvent,
    name="auth_audit_event",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_CREDIT_ACTION_PG = PGEnum(
    CreditTransactionAction,
    name="credit_transaction_action",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_bounced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    display_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )
    auth_provider: Mapped[AuthProvider] = mapped_column(
        _AUTH_PROVIDER_PG, nullable=False
    )
    provider_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    tier: Mapped[UserTier] = mapped_column(
        _USER_TIER_PG, nullable=False, default=UserTier.free
    )
    credit_balance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    byok_api_key: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True
    )
    byok_provider: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    byok_key_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    totp_secret: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True
    )
    # bcrypt-hashed recovery codes, JSONB list of strings.
    totp_recovery_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    trials_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    closure_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspension_reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    accepted_tos_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )
    marketing_opt_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    blocked_companies: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_users_provider_identity", "auth_provider", "provider_id"),
    )

    # Convenience flags ---------------------------------------------------

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def has_totp(self) -> bool:
        return self.totp_secret is not None

    @property
    def is_suspended(self) -> bool:
        return self.suspended_at is not None

    @property
    def is_closure_pending(self) -> bool:
        return self.closure_requested_at is not None


# ---------------------------------------------------------------------------
# RefreshToken — rotation chain + reuse detection
# ---------------------------------------------------------------------------


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex digest of the opaque random token.  Never store the
    # plaintext token at rest.
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    device_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Self-reference: points at the token that this token rotated from.
    # Used so reuse detection can walk a chain backwards if needed.
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > _utcnow()


# ---------------------------------------------------------------------------
# AuthAuditLog
# ---------------------------------------------------------------------------


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable because failed-login records for unknown emails still need
    # to be auditable, and because suspicious_login can fire before a user
    # is resolved.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event: Mapped[AuthAuditEvent] = mapped_column(_AUTH_EVENT_PG, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(
        String(512), nullable=False, default=""
    )
    # ``metadata`` is a reserved SQLAlchemy attribute name — store under
    # ``event_metadata`` and surface in the response model layer as needed.
    event_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_auth_audit_log_user_event_time", "user_id", "event", "created_at"),
        Index("ix_auth_audit_log_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# CreditTransaction (minimal slice — Step 6 fills out the billing surface)
# ---------------------------------------------------------------------------


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[CreditTransactionAction] = mapped_column(
        _CREDIT_ACTION_PG, nullable=False
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    user: Mapped["User"] = relationship(back_populates="credit_transactions")


__all__ = [
    "AuthAuditEvent",
    "AuthAuditLog",
    "AuthProvider",
    "CreditTransaction",
    "CreditTransactionAction",
    "RefreshToken",
    "User",
    "UserTier",
]
