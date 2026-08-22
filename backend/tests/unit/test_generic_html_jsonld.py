"""JSON-LD JobPosting parsing for generic HTML career pages (M19 slice 4)."""

from __future__ import annotations

from app.services.career_watch.generic_html import (
    parse_generic_html,
    parse_jsonld_job_postings,
)


def test_parse_jsonld_single_job_posting() -> None:
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Backend Engineer",
        "description": "<p>Build APIs</p>",
        "datePosted": "2026-02-01",
        "url": "https://careers.example.com/jobs/backend-engineer",
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "San Francisco",
            "addressRegion": "CA",
            "addressCountry": "US"
          }
        }
      }
      </script>
    </head></html>
    """
    jobs = parse_jsonld_job_postings(html, base_url="https://careers.example.com")
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert "Build APIs" in jobs[0].description_text
    assert jobs[0].location == "San Francisco, CA, US"
    assert jobs[0].apply_url == "https://careers.example.com/jobs/backend-engineer"
    assert jobs[0].posted_at is not None


def test_parse_jsonld_graph_with_multiple_postings() -> None:
    html = """
    <script type='application/ld+json'>
    {
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "Organization", "name": "Acme"},
        {"@type": "JobPosting", "title": "Designer", "url": "/jobs/designer"},
        {"@type": "JobPosting", "title": "PM", "url": "/jobs/pm"}
      ]
    }
    </script>
    """
    jobs = parse_jsonld_job_postings(html, base_url="https://careers.example.com")
    assert len(jobs) == 2
    titles = {job.title for job in jobs}
    assert titles == {"Designer", "PM"}


def test_parse_generic_html_prefers_jsonld_over_anchors() -> None:
    html = """
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Structured Role", "url": "/jobs/structured"}
    </script>
    <a href="/jobs/noisy-link">Noisy Job Link</a>
    """
    jobs = parse_generic_html(html, base_url="https://careers.example.com")
    assert len(jobs) == 1
    assert jobs[0].title == "Structured Role"


def test_parse_generic_html_falls_back_to_anchors_without_jsonld() -> None:
    html = """
    <a href="/jobs/backend-engineer">Backend Engineer Job</a>
    <a href="/about">About us</a>
    """
    jobs = parse_generic_html(html, base_url="https://careers.example.com")
    assert len(jobs) == 1
    assert "Backend Engineer" in jobs[0].title
