"""application_tracker: applications, rounds, offers, attachments

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-31

Implements Step 29 of ``docs/IMPLEMENTATION_PLAN.md`` and
``SYSTEM_DESIGN_PHASE_2.md`` §19.4.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

APPLICATION_STATUS_ENUM = "application_status"
INTERVIEW_FORMAT_ENUM = "interview_format"
INTERVIEW_OUTCOME_ENUM = "interview_outcome"
OFFER_DECISION_ENUM = "offer_decision"
REJECTION_REASON_ENUM = "rejection_reason"


def upgrade() -> None:
    bind = op.get_bind()

    application_status = postgresql.ENUM(
        "draft",
        "applied",
        "interviewing",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        name=APPLICATION_STATUS_ENUM,
        create_type=True,
    )
    interview_format = postgresql.ENUM(
        "phone",
        "video",
        "onsite",
        "take_home",
        "other",
        name=INTERVIEW_FORMAT_ENUM,
        create_type=True,
    )
    interview_outcome = postgresql.ENUM(
        "pending",
        "passed",
        "failed",
        "no_show",
        name=INTERVIEW_OUTCOME_ENUM,
        create_type=True,
    )
    offer_decision = postgresql.ENUM(
        "pending",
        "accepted",
        "declined",
        name=OFFER_DECISION_ENUM,
        create_type=True,
    )
    rejection_reason = postgresql.ENUM(
        "ghosted",
        "explicit_rejection",
        "position_filled",
        "withdrew",
        "other",
        name=REJECTION_REASON_ENUM,
        create_type=True,
    )

    application_status.create(bind, checkfirst=True)
    interview_format.create(bind, checkfirst=True)
    interview_outcome.create(bind, checkfirst=True)
    offer_decision.create(bind, checkfirst=True)
    rejection_reason.create(bind, checkfirst=True)

    # Forward-compatible column for Step 31 reminder scheduling.
    op.add_column(
        "notifications",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_scheduled_at",
        "notifications",
        ["scheduled_at"],
        postgresql_where=sa.text("scheduled_at IS NOT NULL"),
    )

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resume_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resume_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("jd_title", sa.String(500), nullable=False, server_default=""),
        sa.Column("jd_company", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "applied",
                "interviewing",
                "offer",
                "accepted",
                "rejected",
                "withdrawn",
                name=APPLICATION_STATUS_ENUM,
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("applied_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("job_url", sa.String(2048), nullable=True),
        sa.Column(
            "rejection_reason",
            postgresql.ENUM(
                "ghosted",
                "explicit_rejection",
                "position_filled",
                "withdrew",
                "other",
                name=REJECTION_REASON_ENUM,
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("rejection_notes", sa.Text(), nullable=True),
        sa.Column(
            "status_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_user_status", "applications", ["user_id", "status"])
    op.create_index(
        "ix_applications_resume_record_id",
        "applications",
        ["resume_record_id"],
        unique=True,
        postgresql_where=sa.text("resume_record_id IS NOT NULL"),
    )

    op.create_table(
        "interview_rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "format",
            postgresql.ENUM(
                "phone",
                "video",
                "onsite",
                "take_home",
                "other",
                name=INTERVIEW_FORMAT_ENUM,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "interviewers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "outcome",
            postgresql.ENUM(
                "pending",
                "passed",
                "failed",
                "no_show",
                name=INTERVIEW_OUTCOME_ENUM,
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_interview_rounds_application_id",
        "interview_rounds",
        ["application_id"],
    )

    op.create_table(
        "offer_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_salary_usd", sa.Integer(), nullable=True),
        sa.Column("bonus_usd", sa.Integer(), nullable=True),
        sa.Column("equity_description", sa.Text(), nullable=True),
        sa.Column("sign_on_usd", sa.Integer(), nullable=True),
        sa.Column("benefits", sa.Text(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decision",
            postgresql.ENUM(
                "pending",
                "accepted",
                "declined",
                name=OFFER_DECISION_ENUM,
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "application_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachment_size_positive"),
        sa.CheckConstraint(
            "size_bytes <= 5242880", name="ck_attachment_size_under_5mb"
        ),
    )
    op.create_index(
        "ix_application_attachments_application_id",
        "application_attachments",
        ["application_id"],
    )

    # Enforce max 5 attachments per application at DB level via constraint trigger.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_application_attachment_limit()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (SELECT COUNT(*) FROM application_attachments
                WHERE application_id = NEW.application_id) > 5 THEN
                RAISE EXCEPTION 'max_attachments_exceeded';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_application_attachment_limit
        AFTER INSERT ON application_attachments
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION check_application_attachment_limit();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_application_attachment_limit "
        "ON application_attachments"
    )
    op.execute("DROP FUNCTION IF EXISTS check_application_attachment_limit()")

    op.drop_index(
        "ix_application_attachments_application_id",
        table_name="application_attachments",
    )
    op.drop_table("application_attachments")
    op.drop_table("offer_details")
    op.drop_index("ix_interview_rounds_application_id", table_name="interview_rounds")
    op.drop_table("interview_rounds")
    op.drop_index("ix_applications_resume_record_id", table_name="applications")
    op.drop_index("ix_applications_user_status", table_name="applications")
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")

    op.drop_index("ix_notifications_scheduled_at", table_name="notifications")
    op.drop_column("notifications", "scheduled_at")

    bind = op.get_bind()
    postgresql.ENUM(name=REJECTION_REASON_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=OFFER_DECISION_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=INTERVIEW_OUTCOME_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=INTERVIEW_FORMAT_ENUM).drop(bind, checkfirst=True)
    postgresql.ENUM(name=APPLICATION_STATUS_ENUM).drop(bind, checkfirst=True)
