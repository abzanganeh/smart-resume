"""PDF export layout regressions — bullets must stay attached across page breaks."""

from __future__ import annotations

import asyncio
import io
import re

import pytest
from pdfminer.high_level import extract_pages, extract_text
from pdfminer.layout import LTTextLineHorizontal

from app.models.rewrite import TailoredEducationEntry, TailoredExperienceEntry, TailoredResumeOutput
from app.models.session import Session
from app.services.export_service import _resume_to_html, render_pdf

# Letter page width minus @page right margin (0.65in ≈ 46.8pt).
_PAGE_RIGHT_EDGE_PT = 612.0 - 46.8


def _normalize_hyphens(text: str) -> str:
    return text.replace("\u2011", "-").replace("\u2010", "-").replace("\u00ad", "-")


def _walk_text_lines(page_layout, page_width: float) -> list[tuple[float, float, str]]:
    lines: list[tuple[float, float, str]] = []

    def walk(obj) -> None:
        if isinstance(obj, LTTextLineHorizontal):
            lines.append((obj.x0, obj.x1, obj.get_text().strip()))
        elif hasattr(obj, "__iter__"):
            for child in obj:
                walk(child)

    walk(page_layout)
    return lines


def _full_resume_session() -> Session:
    """Resume shaped like a real tailored export (2 pages, dense bullets)."""
    return Session(
        session_id="layout-test",
        phase3_output=TailoredResumeOutput(
            contact={
                "name": "ALI BARZIN",
                "email": "abarzinzanganeh@gmail.com",
                "location": "Camas, WA",
                "phone": "(360) 947-7777",
                "linkedin": "https://linkedin.com/in/example",
                "github": "https://github.com/example",
                "website": "https://example.com",
            },
            summary=(
                "Software engineer with 10+ years in identity and security software, specializing in "
                "Python and TypeScript. Experienced in customer deployments and technical evaluations, "
                "delivering integrations for enterprise environments. Proven ability to build and support "
                "agentic AI systems in cloud and on-prem settings."
            ),
            skills=[
                "Programming Languages: Python, TypeScript, Java, Go, Rust",
                "Cloud Infrastructure: AWS, Docker, Kubernetes, CI/CD pipelines",
                "Security & Identity: OAuth2, OIDC, SSO, MFA, SIEM",
                "Engineering Practices: Automated testing, Deployment tooling, technical documentation",
                "AI & Machine Learning: agentic AI, coding agents, eval harnesses",
            ],
            experience=[
                TailoredExperienceEntry(
                    company="IdMe24",
                    title="Software Engineer · AI Engineer",
                    dates="May 2025 – Present",
                    bullets=[
                        "Built and integrated Rai (agentic AI layer) into a 5-product, 13+ microservice identity platform (Trust, Asar, Rai, TrustMobile, idMe24) via FastAPI APIs and gateway routes.",
                        "Delivered enterprise identity integrations consumed by workforce, mobile, and admin products: OAuth2/OIDC/SAML, MFA, and directory sync across multi-tenant deployments.",
                        "Deployed LLM/embeddings paths on AWS Bedrock with Kubernetes canary staging; owned release gates with 1,200+ pytest cases (unit, integration, chaos, load) before promote.",
                        "Architected shared security policy APIs and IdP foundations (OAuth2/OIDC/SAML, MFA, passkeys, RBAC) with 467+ Go unit tests.",
                        "Championed quality ownership across multiple stacks — automated tests, CI release gates, and documentation for repeatable enterprise deployment.",
                    ],
                ),
                TailoredExperienceEntry(
                    company="SecureAuth Corporation",
                    title="Senior Software QA Engineer",
                    dates="Jan 2022 – Apr 2025",
                    bullets=[
                        "Validated and shipped production ML risk engines in enterprise authentication workflows across a multi-tenant SaaS platform.",
                        "Built Python REST/API observability services and CI/CD release gates on AWS-hosted staging; defined deployment guidelines for ML-based authentication services.",
                        "Integrated ML risk outputs into live auth paths via automated validation frameworks.",
                    ],
                ),
                TailoredExperienceEntry(
                    company="Acceptto Corporation",
                    title="Software Engineer — Identity & Security",
                    dates="Sep 2016 – Jan 2022",
                    bullets=[
                        "Built Java Android SDK modules and backend services for a cognitive authentication platform — cross-device identity verification and REST APIs.",
                        "Delivered full-stack identity features across mobile SDK, Java backend, and React web clients.",
                        "Engineered Python validation and automation for ML-integrated authentication pipelines.",
                    ],
                ),
            ],
            projects=[
                {
                    "name": "FlintApply",
                    "bullets": [
                        "Developed AI-powered job-search SaaS: master resume, JD tailoring, cover letters, job match, Playwright E2E, Docker deployment.",
                    ],
                },
                {
                    "name": "Movie Agent Service",
                    "bullets": [
                        "Engineered production-grade agentic AI with tool-calling, RAG, and session-based memory isolation.",
                    ],
                },
                {
                    "name": "Flint — Meeting Co-Pilot",
                    "bullets": [
                        "Built local-first AI desktop co-pilot with Whisper transcription and on-device RAG.",
                    ],
                },
                {
                    "name": "FlintStrike",
                    "bullets": [
                        "Built and shipped an end-to-end TypeScript platform that embeds LLM research into live workflows via a Chrome MV3 extension.",
                    ],
                },
            ],
            education=[
                TailoredEducationEntry(
                    degree="AI/ML Software Engineering Program",
                    institution="IK",
                    year="2026",
                ),
                TailoredEducationEntry(
                    degree="Certificate, Web Development and Design",
                    institution="Portland Community College",
                    year="2017",
                ),
                TailoredEducationEntry(
                    degree="Executive MBA",
                    institution="Industrial Management Institute",
                    year="2011",
                ),
            ],
        ),
    )


def test_resume_html_uses_flex_bullets_not_native_lists() -> None:
    html = _resume_to_html(_full_resume_session())
    assert "bullet-line" in html
    assert "<ul>" not in html
    assert "<li>" not in html


def test_resume_html_keeps_experience_dates_on_header_row() -> None:
    html = _resume_to_html(_full_resume_session())
    assert 'class="exp-dates">May 2025 – Present</span>' in html
    assert 'class="exp-dates">Jan 2022 – Apr 2025</span>' in html


@pytest.mark.asyncio
async def test_render_pdf_keeps_bullets_attached_to_text() -> None:
    pdf_bytes = await render_pdf(_full_resume_session())
    text = extract_text(io.BytesIO(pdf_bytes))

    orphan_lines = [line for line in text.splitlines() if line.strip() in {"•", "·", "-"}]
    assert orphan_lines == []

    flattened = re.sub(r"\s+", " ", _normalize_hyphens(text))
    assert "Built and integrated Rai" in flattened
    assert "FlintApply" in flattened
    assert "on-prem" in flattened


@pytest.mark.asyncio
async def test_render_pdf_text_stays_inside_printable_width() -> None:
    pdf_bytes = await render_pdf(_full_resume_session())
    for page_layout in extract_pages(io.BytesIO(pdf_bytes)):
        for _x0, x1, text in _walk_text_lines(page_layout, page_layout.width):
            if not text:
                continue
            assert x1 <= _PAGE_RIGHT_EDGE_PT + 1.0, (
                f"Text overflows printable width: {text!r} (x1={x1:.1f})"
            )


@pytest.mark.asyncio
async def test_render_pdf_keeps_compound_hyphens_together() -> None:
    session = Session(
        session_id="hyphen-test",
        phase3_output=TailoredResumeOutput(
            contact={"name": "Jane Doe", "email": "jane@example.com"},
            summary=(
                "Proven ability to build and support agentic AI systems in cloud and on-prem "
                "settings with enterprise customers."
            ),
        ),
    )
    pdf_bytes = await render_pdf(session)
    text = extract_text(io.BytesIO(pdf_bytes))
    assert "on-\n" not in text
    assert "on-prem" in text.replace("\u2011", "-")


@pytest.mark.asyncio
async def test_render_pdf_includes_all_visible_bullets() -> None:
    session = _full_resume_session()
    expected = [
        bullet
        for entry in session.phase3_output.experience
        for bullet in entry.bullets
        if bullet.strip()
    ]
    pdf_bytes = await render_pdf(session)
    flattened = re.sub(r"\s+", " ", _normalize_hyphens(extract_text(io.BytesIO(pdf_bytes))))
    for bullet in expected:
        snippet = re.sub(r"\s+", " ", _normalize_hyphens(bullet))[:48]
        assert snippet in flattened
