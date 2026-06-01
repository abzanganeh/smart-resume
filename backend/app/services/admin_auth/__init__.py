"""Admin authentication services (Step 35 / IMPLEMENTATION_PLAN section 8.4).

Sub-modules:

- ``audit``     : ``write_admin_audit`` helper that writes one
  ``AdminAuditLog`` row inside the caller's transaction.
- ``bootstrap`` : startup hook that creates the first super-admin under
  ``pg_advisory_lock`` (section 8.4.3).
- ``passwords`` : bcrypt re-export (kept thin so admin paths never
  accidentally bypass the user-side strength rules).
- ``sessions``  : Redis-backed admin session store with IP + UA binding.
- ``tokens``    : JWT issuance / verification for the three admin token
  types (``admin_2fa_setup``, ``admin_challenge``, ``admin_session``).
- ``totp``      : TOTP enrollment / verification helpers (mandatory).
- ``invites``   : invite token mint / accept logic.
"""

from __future__ import annotations
