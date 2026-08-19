"""PromoCode model contract tests."""

from __future__ import annotations

import uuid

from sqlalchemy import inspect

from app.models.promo_code import PromoCode


def test_promo_code_has_restricted_user_id_column() -> None:
    columns = {col.key for col in inspect(PromoCode).columns}
    assert "restricted_user_id" in columns


def test_promo_code_restricted_user_id_is_optional_uuid() -> None:
    promo = PromoCode(
        id=uuid.uuid4(),
        code="TESTCODE",
        grant_type="extra_credits",
        payload={"amount": 5, "credit_kind": "free"},
        restricted_user_id=None,
    )
    assert promo.restricted_user_id is None

    user_id = uuid.uuid4()
    promo.restricted_user_id = user_id
    assert promo.restricted_user_id == user_id
