"""Unit tests for resume chat patch schema."""

from app.models.chat import ResumePatch


def test_experience_title_and_dates_patch_fields() -> None:
    patch = ResumePatch(
        section="experience",
        company="SecureAuth",
        description="Correct employment dates",
        title_old="Senior Software Engineer",
        new_title="Senior Software Engineer",
        dates_old="2021 – 2024",
        new_dates="2022 – 2025",
    )
    assert patch.new_dates == "2022 – 2025"
    assert patch.new_title == "Senior Software Engineer"


def test_experience_bullet_patch_fields() -> None:
    patch = ResumePatch(
        section="experience",
        company="Acceptto",
        description="Stronger bullet",
        bullet_old="Built MFA flows.",
        bullet_new="Built MFA flows with metrics.",
    )
    assert patch.bullet_new == "Built MFA flows with metrics."


def test_projects_remove_patch_fields() -> None:
    patch = ResumePatch(
        section="projects",
        description="Remove mobile projects",
        remove_projects=["ENTROS — Mobile Companion for Asar", "IDME24"],
    )
    assert len(patch.remove_projects) == 2
