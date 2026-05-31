"""Billing service package.

Modules:

- ``price_resolver``  Two-layer ``code → stripe_price_id`` resolution
  (PlanConfig DB row → ``STRIPE_PRICE_<CODE>`` env fallback) per
  IMPLEMENTATION_PLAN §7.2.
- ``subscription``    Stripe checkout / portal / pause / resume / change-plan
  wrappers.  All persistence happens via webhook handlers; service-layer
  calls never optimistically mutate ``Subscription`` state.
- ``credits``         Append-only credit ledger helpers.  ``get_balance``
  uses ``FOR SHARE``; ``consume_credit`` uses ``SELECT … FOR UPDATE`` so
  concurrent consumes serialize and never double-spend (§7.5).
- ``quota``           Suspended → subscription → credits routing tree
  enforced before every paid action (§18.3).
- ``webhook_handler`` Implements the seven Stripe events from
  IMPLEMENTATION_PLAN §7.3 in idempotent transactions.
- ``grace_tick``      Scheduled job that transitions stale ``grace`` rows
  to ``expired`` after the 72-hour window (§7.6).
- ``exceptions``      Typed billing errors.  Routers translate these into
  HTTP shapes (402 / 409 / 503 / 500).
"""
