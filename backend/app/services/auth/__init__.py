"""Authentication service package.

Modules:

- ``encryption``  AES-256-GCM helpers used by BYOK keys + TOTP secrets.
- ``password``    bcrypt + zxcvbn for password storage and gating.
- ``tokens``      JWT issuance, refresh-token rotation, reuse detection.
- ``session``     Redis bindings for refresh tokens (device + revocation).
- ``oauth``       Google / GitHub code-for-profile exchanges.
- ``totp``        TOTP enrollment, verification, recovery codes.
- ``email``       Resend transactional emails (verify + reset).
- ``audit``       AuthAuditLog writes + lockout detection.
- ``maintenance`` Background helpers (unverified-account cleanup).
- ``dependencies`` FastAPI ``get_current_user`` + variants.
- ``exceptions``  Typed auth errors.
"""
