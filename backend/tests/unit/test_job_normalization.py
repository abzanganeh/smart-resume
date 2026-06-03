"""Unit tests for job dedup key and salary normalization."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.jobs.normalization import (
    compute_dedup_key,
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
