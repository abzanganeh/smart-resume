from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import is_production_grade

# Rate limits apply in ci/staging/production only — local dev should not 429 loops.
limiter = Limiter(key_func=get_remote_address, enabled=is_production_grade())
