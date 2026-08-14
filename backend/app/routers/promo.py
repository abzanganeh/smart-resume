"""Public promo code redemption — POST /api/promo/redeem"""

from __future__ import annotations

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
    PromoRedeemError,
    redeem_promo_code,
)

router = APIRouter(prefix="/api/promo", tags=["promo"])


class PromoRedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class PromoRedeemResponse(BaseModel):
    ok: bool = True
    grant_type: AdminGrantType
    payload: dict[str, Any]
    idempotent: bool
    credit_transaction_id: str | None = None
    admin_user_grant_id: str | None = None


@router.post("/redeem", response_model=PromoRedeemResponse)
@limiter.limit("10/minute")
async def promo_redeem(
    request: Request,
    body: PromoRedeemRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PromoRedeemResponse:
    try:
        result = await redeem_promo_code(db, user_id=user.id, code=body.code)
    except PromoCodeInvalidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "promo_code_invalid"},
        )
    except PromoCodeInactiveError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "promo_code_inactive"},
        )
    except PromoCodeExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "promo_code_expired"},
        )
    except PromoCodeExhaustedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "promo_code_exhausted"},
        )
    except InvalidGrantPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "invalid_grant_payload", "message": str(exc)},
        ) from exc
    except PromoRedeemError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code},
        ) from exc

    await db.commit()
    return PromoRedeemResponse(
        grant_type=result.grant_type,
        payload=result.payload,
        idempotent=result.idempotent,
        credit_transaction_id=(
            str(result.credit_transaction_id)
            if result.credit_transaction_id is not None
            else None
        ),
        admin_user_grant_id=(
            str(result.admin_user_grant_id)
            if result.admin_user_grant_id is not None
            else None
        ),
    )
