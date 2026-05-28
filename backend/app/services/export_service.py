from __future__ import annotations

import io
import os
from pathlib import Path

import structlog
from docx import Document
from docx.shared import Pt
from jinja2 import Environment, FileSystemLoader

from app.models.session import Session

log = structlog.get_logger()

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))


def _resume_to_html(session: Session) -> str:
    template = _jinja_env.get_template("resume.html")
    output = session.phase3_output
    user = session.user_info
    return template.render(
        contact=output.contact,
        summary=output.summary,
        skills=output.skills,
        experience=output.experience,
        projects=output.projects,
        education=output.education,
        certifications=output.certifications,
        user=user,
    )


async def render_pdf(session: Session) -> bytes:
    """Render the tailored resume to PDF via Puppeteer (pyppeteer)."""
    try:
        from pyppeteer import launch

        html = _resume_to_html(session)
        browser = await launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = await browser.newPage()
        await page.setContent(html, {"waitUntil": "networkidle0"})
        pdf_bytes = await page.pdf({
            "format": "Letter",
            "printBackground": True,
            "margin": {"top": "0.5in", "right": "0.5in", "bottom": "0.5in", "left": "0.5in"},
        })
        await browser.close()
        return pdf_bytes
    except Exception as e:
        log.error("pdf_render_error", error=str(e))
        # Fallback: return HTML as bytes if Puppeteer fails
        return _resume_to_html(session).encode()


def render_docx(session: Session) -> bytes:
    """Render the tailored resume to DOCX via python-docx."""
    output = session.phase3_output
    user = session.user_info
    doc = Document()

    # Title / Contact
    contact = output.contact
    name = contact.get("name", user.name if user else "") if isinstance(contact, dict) else ""
    email = contact.get("email", user.email if user else "") if isinstance(contact, dict) else ""
    github = contact.get("github", "") if isinstance(contact, dict) else ""

    title = doc.add_heading(name, level=0)
    doc.add_paragraph(f"{email}  |  {github}")

    # Summary
    if output.summary:
        doc.add_heading("Summary", level=1)
        doc.add_paragraph(output.summary)

    # Skills
    if output.skills:
        doc.add_heading("Skills", level=1)
        doc.add_paragraph(", ".join(output.skills))

    # Experience
    if output.experience:
        doc.add_heading("Experience", level=1)
        for entry in output.experience:
            p = doc.add_paragraph()
            p.add_run(f"{entry.title} — {entry.company}").bold = True
            p.add_run(f"  ({entry.dates})")
            for bullet in entry.bullets:
                doc.add_paragraph(bullet, style="List Bullet")

    # Projects
    if output.projects:
        doc.add_heading("Projects", level=1)
        for proj in output.projects:
            if isinstance(proj, dict):
                p = doc.add_paragraph()
                p.add_run(proj.get("name", "")).bold = True
                if proj.get("url"):
                    p.add_run(f"  {proj['url']}")
                for bullet in proj.get("bullets", []):
                    doc.add_paragraph(bullet, style="List Bullet")

    # Education
    if output.education:
        doc.add_heading("Education", level=1)
        for edu in output.education:
            if isinstance(edu, dict):
                doc.add_paragraph(f"{edu.get('degree', '')} — {edu.get('institution', '')} ({edu.get('year', '')})")

    # Certifications
    if output.certifications:
        doc.add_heading("Certifications", level=1)
        doc.add_paragraph(", ".join(output.certifications))

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def render_txt(session: Session) -> str:
    """Plain-text resume for copy-paste."""
    output = session.phase3_output
    user = session.user_info
    lines: list[str] = []

    contact = output.contact if isinstance(output.contact, dict) else {}
    name = contact.get("name", user.name if user else "")
    email = contact.get("email", user.email if user else "")
    github = contact.get("github", "")
    linkedin = contact.get("linkedin", "")

    lines += [name.upper(), email, github or "", linkedin or "", ""]

    if output.summary:
        lines += ["SUMMARY", "-------", output.summary, ""]

    if output.skills:
        lines += ["SKILLS", "------", ", ".join(output.skills), ""]

    if output.experience:
        lines += ["EXPERIENCE", "----------"]
        for entry in output.experience:
            lines += [f"{entry.title} | {entry.company} | {entry.dates}"]
            for bullet in entry.bullets:
                lines.append(f"  • {bullet}")
            lines.append("")

    if output.projects:
        lines += ["PROJECTS", "--------"]
        for proj in output.projects:
            if isinstance(proj, dict):
                lines.append(proj.get("name", ""))
                for bullet in proj.get("bullets", []):
                    lines.append(f"  • {bullet}")
                lines.append("")

    if output.education:
        lines += ["EDUCATION", "---------"]
        for edu in output.education:
            if isinstance(edu, dict):
                lines.append(f"{edu.get('degree', '')} — {edu.get('institution', '')} ({edu.get('year', '')})")
        lines.append("")

    if output.certifications:
        lines += ["CERTIFICATIONS", "--------------", ", ".join(output.certifications), ""]

    return "\n".join(lines)
