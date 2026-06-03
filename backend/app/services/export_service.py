from __future__ import annotations

import io
import re
from pathlib import Path

import structlog
from docx import Document
from docx.shared import Pt
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models.cover_letter import CoverLetterOutput
from app.models.session import Session

log = structlog.get_logger()

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

# Common placeholder names/emails that LLMs emit when they lack real data
_PLACEHOLDER_NAMES = {"john doe", "jane doe", "candidate name", "your name", "full name", ""}
_PLACEHOLDER_EMAILS = {
    "john.doe@example.com", "jane.doe@example.com",
    "email@example.com", "youremail@example.com", "",
}
_PLACEHOLDER_PHONES = {"123-456-7890", "(123) 456-7890", "555-555-5555", ""}


def _authoritative_contact(llm_contact: object, user: object) -> dict:
    """Merge LLM-extracted contact with real authenticated-user data.

    The LLM sometimes emits placeholder values (e.g. "John Doe", "john.doe@example.com")
    when the user's original resume didn't contain their contact info.  We always
    prefer the real user record for name/email/phone/linkedin/github.
    """
    c: dict = llm_contact if isinstance(llm_contact, dict) else {}
    result = dict(c)

    if user is None:
        return result

    # name — prefer user record unless LLM value looks legit
    llm_name = (c.get("name") or "").strip()
    if llm_name.lower() in _PLACEHOLDER_NAMES:
        result["name"] = getattr(user, "name", "") or llm_name

    # email — always prefer authenticated user email
    llm_email = (c.get("email") or "").strip()
    if llm_email.lower() in _PLACEHOLDER_EMAILS:
        result["email"] = getattr(user, "email", "") or llm_email

    # phone — user record wins if LLM produced a placeholder
    llm_phone = (c.get("phone") or "").strip()
    if llm_phone in _PLACEHOLDER_PHONES and getattr(user, "phone", None):
        result["phone"] = user.phone  # type: ignore[union-attr]

    # linkedin / github — user record fills gaps only (don't override real LLM values)
    if not result.get("linkedin") and getattr(user, "linkedin", None):
        result["linkedin"] = user.linkedin  # type: ignore[union-attr]
    if not result.get("github") and getattr(user, "github", None):
        result["github"] = user.github  # type: ignore[union-attr]

    return result


def _resume_to_html(session: Session) -> str:
    template = _jinja_env.get_template("resume.html")
    output = session.phase3_output
    user = session.user_info
    contact = _authoritative_contact(output.contact, user)
    return template.render(
        contact=contact,
        summary=output.summary,
        skills=output.skills,
        experience=output.experience,
        projects=output.projects,
        education=output.education,
        certifications=output.certifications,
        user=user,
    )


async def render_pdf(session: Session) -> bytes:
    """Render the tailored resume to PDF via WeasyPrint (pure Python, no browser needed)."""
    from weasyprint import HTML, CSS
    html = _resume_to_html(session)
    css = CSS(string="""
        @page { size: Letter; margin: 0.6in 0.65in; }
        body { font-family: Georgia, serif; font-size: 10.5pt; color: #111; line-height: 1.45; }
        h1 { font-size: 18pt; margin: 0 0 2pt; }
        h2 { font-size: 11pt; border-bottom: 1px solid #555; padding-bottom: 2pt; margin: 12pt 0 4pt; }
        ul { margin: 2pt 0; padding-left: 14pt; }
        li { margin-bottom: 2pt; }
        p  { margin: 2pt 0; }
    """)
    return HTML(string=html).write_pdf(stylesheets=[css])


def render_docx(session: Session) -> bytes:
    """Render the tailored resume to DOCX via python-docx."""
    output = session.phase3_output
    user = session.user_info
    doc = Document()

    # Title / Contact
    contact = _authoritative_contact(output.contact, user)
    name = contact.get("name", "")
    email = contact.get("email", "")
    phone = contact.get("phone", "")
    linkedin = contact.get("linkedin", "")
    github = contact.get("github", "")

    doc.add_heading(name, level=0)
    contact_line_parts = [p for p in [email, phone, linkedin, github] if p]
    doc.add_paragraph("  |  ".join(contact_line_parts))

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
            year_str = f" ({edu.year})" if edu.year else ""
            doc.add_paragraph(f"{edu.degree} — {edu.institution}{year_str}")
            for bullet in edu.bullets:
                doc.add_paragraph(bullet, style="List Bullet")

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

    contact = _authoritative_contact(output.contact, user)
    name = contact.get("name", "")
    email = contact.get("email", "")
    phone = contact.get("phone", "")
    linkedin = contact.get("linkedin", "")
    github = contact.get("github", "")

    contact_parts = [p for p in [email, phone, linkedin, github] if p]
    lines += [name.upper(), " | ".join(contact_parts), ""]

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
            year_str = f" ({edu.year})" if edu.year else ""
            lines.append(f"{edu.degree} — {edu.institution}{year_str}")
            for bullet in edu.bullets:
                lines.append(f"  • {bullet}")
        lines.append("")

    if output.certifications:
        lines += ["CERTIFICATIONS", "--------------", ", ".join(output.certifications), ""]

    return "\n".join(lines)


def _cover_letter_paragraphs(output: CoverLetterOutput) -> list[str]:
    text = output.body_plain.strip() or output.body_markdown.strip()
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _cover_letter_to_html(session: Session) -> str:
    template = _jinja_env.get_template("cover_letter.html")
    output = session.cover_letter_output
    if output is None:
        raise ValueError("No cover letter to export")
    user = session.user_info
    target_role = user.target_role if user else ""
    return template.render(
        paragraphs=_cover_letter_paragraphs(output),
        user=user,
        target_role=target_role,
    )


async def render_cover_letter_pdf(session: Session) -> bytes:
    """Render the cover letter to PDF via WeasyPrint."""
    from weasyprint import CSS, HTML

    html = _cover_letter_to_html(session)
    css = CSS(string="""
        @page { size: Letter; margin: 0.75in; }
        body { font-family: Georgia, serif; font-size: 11pt; color: #111; line-height: 1.55; }
        p { margin-bottom: 12pt; text-align: justify; }
    """)
    return HTML(string=html).write_pdf(stylesheets=[css])


def render_cover_letter_docx(session: Session) -> bytes:
    """Render the cover letter to DOCX via python-docx."""
    output = session.cover_letter_output
    if output is None:
        raise ValueError("No cover letter to export")
    user = session.user_info
    doc = Document()

    if user and user.name:
        title = doc.add_heading(user.name, level=0)
        title.runs[0].font.size = Pt(14)
    contact_bits = []
    if user:
        if user.email:
            contact_bits.append(user.email)
        if user.phone:
            contact_bits.append(user.phone)
    if contact_bits:
        doc.add_paragraph("  |  ".join(contact_bits))

    if user and user.target_role:
        p = doc.add_paragraph()
        p.add_run(f"Re: {user.target_role}").italic = True

    doc.add_paragraph("")

    for para in _cover_letter_paragraphs(output):
        doc.add_paragraph(para)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def render_cover_letter_txt(session: Session) -> str:
    """Plain-text cover letter for copy-paste."""
    output = session.cover_letter_output
    if output is None:
        raise ValueError("No cover letter to export")
    user = session.user_info
    lines: list[str] = []

    if user and user.name:
        lines.append(user.name)
    if user and user.email:
        lines.append(user.email)
    if user and user.phone:
        lines.append(user.phone)
    if user and user.target_role:
        lines.append(f"Re: {user.target_role}")
    if lines:
        lines.append("")

    lines.extend(_cover_letter_paragraphs(output))
    return "\n\n".join(lines)
