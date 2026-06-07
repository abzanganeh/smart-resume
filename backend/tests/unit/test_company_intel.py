"""Unit tests for company intelligence extraction and caching helpers."""

from __future__ import annotations

import pytest

from app.models.company_profile import CompanyIntelOutput
from app.services.company_intel.cache import normalise_key
from app.services.company_intel.extractor import _build_intel, _parse_json_from_response

pytestmark = pytest.mark.unit


def test_normalise_key_slugifies_company_name() -> None:
    assert normalise_key("Google LLC") == "google-llc"
    assert normalise_key("Amazon Web Services (AWS)") == "amazon-web-services-aws"
    assert normalise_key("  Stripe  ") == "stripe"


def test_normalise_key_empty_falls_back_to_unknown() -> None:
    assert normalise_key("   ") == "unknown"


def test_parse_json_from_response_accepts_wrapped_json() -> None:
    raw = 'Here is the result:\n{"mission": "Build X", "values": ["Speed"], "culture_notes": "Move fast"}\n'
    parsed = _parse_json_from_response(raw)
    assert parsed is not None
    assert parsed["mission"] == "Build X"


def test_parse_json_from_response_rejects_invalid_payload() -> None:
    assert _parse_json_from_response("not json") is None


def test_build_intel_trims_values_and_ignores_non_list() -> None:
    intel = _build_intel(
        "Acme",
        {
            "mission": "  Ship great products  ",
            "values": "Customer Obsession",
            "culture_notes": "Ownership matters",
        },
    )
    assert intel.mission == "Ship great products"
    assert intel.values == []
    assert intel.culture_notes == "Ownership matters"
    assert intel.source == "jd_text"


def test_company_intel_output_render_and_empty() -> None:
    empty = CompanyIntelOutput(company_name="Acme")
    assert empty.is_empty()
    assert empty.render_for_prompt() == "Company: Acme"

    filled = CompanyIntelOutput(
        company_name="Acme",
        mission="Build useful software",
        values=["Ownership", "Speed"],
        culture_notes="Bias for action",
        source="cache",
    )
    assert not filled.is_empty()
    rendered = filled.render_for_prompt()
    assert "Mission: Build useful software" in rendered
    assert "Values: Ownership, Speed" in rendered
    assert "Culture: Bias for action" in rendered
