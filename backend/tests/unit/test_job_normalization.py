"""Unit tests for job dedup key and salary normalization."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.jobs.normalization import (
    compute_dedup_key,
    compute_dedup_key_v2,
    normalize_apply_url,
    normalize_location,
    normalize_salary,
)


class TestComputeDedupKey:
    def test_deterministic_for_same_inputs(self) -> None:
        posted = datetime(2026, 5, 15, 14, 30, tzinfo=timezone.utc)
        a = compute_dedup_key("Acme Corp", "Software Engineer", "Toronto", posted)
        b = compute_dedup_key("Acme Corp", "Software Engineer", "Toronto", posted)
        assert a == b

    def test_case_insensitive_company_and_title(self) -> None:
        posted = date(2026, 5, 15)
        lower = compute_dedup_key("acme corp", "software engineer", "Toronto", posted)
        mixed = compute_dedup_key("ACME CORP", "Software Engineer", "Toronto", posted)
        assert lower == mixed

    def test_differs_when_city_changes(self) -> None:
        posted = date(2026, 5, 15)
        toronto = compute_dedup_key("Acme", "Engineer", "Toronto", posted)
        montreal = compute_dedup_key("Acme", "Engineer", "Montreal", posted)
        assert toronto != montreal

    def test_accepts_date_without_time(self) -> None:
        d = date(2026, 1, 2)
        key = compute_dedup_key("Co", "Role", "City", d)
        assert key.endswith("2026-01-02")


class TestNormalizeSalary:
    def test_usd_passthrough(self) -> None:
        assert normalize_salary(100_000, "USD") == 100_000

    def test_cad_conversion(self) -> None:
        assert normalize_salary(100_000, "CAD") == 73_000

    def test_unknown_currency_returns_none(self) -> None:
        assert normalize_salary(50_000, "JPY") is None

    def test_none_amount_returns_none(self) -> None:
        assert normalize_salary(None, "USD") is None

    def test_none_currency_returns_none(self) -> None:
        assert normalize_salary(50_000, None) is None


class TestNormalizeLocation:
    @pytest.mark.parametrize(
        ("location", "city", "country"),
        [
            ("Toronto, Canada", "Toronto", "Canada"),
            ("Austin, TX, United States", "Austin", "United States"),
            ("Remote", "Remote", None),
            ("", None, None),
        ],
    )
    def test_heuristic_split(
        self, location: str, city: str | None, country: str | None
    ) -> None:
        assert normalize_location(location) == (city, country)

    def test_none_input_returns_none_tuple(self) -> None:
        assert normalize_location(None) == (None, None)


class TestNormalizeApplyUrl:
    def test_strips_tracking_params(self) -> None:
        raw = "https://Boards.Greenhouse.io/acme/jobs/123?utm_source=linkedin&ref=foo"
        assert normalize_apply_url(raw) == "https://boards.greenhouse.io/acme/jobs/123"

    def test_trailing_slash_removed(self) -> None:
        assert (
            normalize_apply_url("https://jobs.lever.co/acme/abc-def/")
            == "https://jobs.lever.co/acme/abc-def"
        )

    def test_empty_returns_none(self) -> None:
        assert normalize_apply_url("") is None
        assert normalize_apply_url(None) is None


class TestComputeDedupKeyV2:
    def test_prefers_normalized_apply_url(self) -> None:
        key = compute_dedup_key_v2(
            apply_url="https://Example.com/jobs/1?utm_campaign=x",
            ats_type="greenhouse",
            external_job_id="1",
            company="Acme",
            title="Engineer",
        )
        assert key == "url:https://example.com/jobs/1"

    def test_falls_back_to_ats_pair(self) -> None:
        key = compute_dedup_key_v2(
            apply_url="",
            ats_type="Greenhouse",
            external_job_id=" 42 ",
            company="Acme",
            title="Engineer",
        )
        assert key == "ats:greenhouse:42"

    def test_falls_back_to_legacy_key(self) -> None:
        posted = date(2026, 5, 15)
        legacy = compute_dedup_key("Acme", "Engineer", "Toronto", posted)
        key = compute_dedup_key_v2(
            company="Acme",
            title="Engineer",
            city="Toronto",
            posted_date=posted,
        )
        assert key == legacy
