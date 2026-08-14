"""Public promo code redemption — POST /api/promo/redeem"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.limiter import limiter
from app.models.admin_grant import AdminGrantType
from app.models.user import User
from app.services.auth.dependencies import get_current_user
from app.services.admin.grants import InvalidGrantPayloadError
from app.services.billing.promo import (
    PromoCodeExhaustedError,
    PromoCodeExpiredError,
    PromoCodeInactiveError,
    PromoCodeInvalidError,
    PromoRedeemResult,
    redeem_promo_code,
)

router = APIRouter(prefix="/api/promo", tags=["promo"])


class PromoRedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class PromoRedeemResponse(BaseModel):
    ok: bool = True
    idempotent: bool
    promo_code_id: uuid.UUID
    grant_type: AdminGrantType
    payload: dict[str, Any]
    redemption_id: uuid.UUID
    credit_transaction_id: uuid.UUID | None = None
    admin_user_grant_id: uuid.UUID | None = None


def _serialize_result(result: PromoRedeemResult) -> PromoRedeemResponse:
    return PromoRedeemResponse(
        idempotent=result.idempotent,
        promo_code_id=result.promo_code_id,
        grant_type=result.grant_type,
        payload=result.payload,
        redemption_id=result.redemption_id,
        credit_transaction_id=result.credit_transaction_id,
        admin_user_grant_id=result.admin_user_grant_id,
    )


@router.post("/redeem", response_model=PromoRedeemResponse)
@limiter.limit("10/minute")
async def promo_redeem(
    request: Request,
    body: PromoRedeemRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PromoRedeemResponse:
    try:
        result = await redeem_promo_code(
            db,
            user_id=user.id,
            code=body.code,
        )
    except PromoCodeInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code},
        ) from exc
    except PromoCodeInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": exc.code},
        ) from exc
    except PromoCodeExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": exc.code},
        ) from exc
    except PromoCodeExhaustedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
    except InvalidGrantPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "promo_misconfigured", "message": str(exc)},
        ) from exc

    await db.commit()
    return _serialize_result(result)


__all__ = ["router"]
