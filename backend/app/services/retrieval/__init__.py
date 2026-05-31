"""Master-resume retrieval surface (IMPLEMENTATION_PLAN §6a).

- ``config`` exposes compile-time constants for caps / thresholds /
  budget / embedding model.  Admin overrides via ``LLMConfig`` happen at
  runtime inside :mod:`app.services.retrieval.retrieval_service`.
- ``retrieval_service`` implements the deterministic ANN selection,
  empty-result fallback, and prompt-budget enforcement.
"""

from app.services.retrieval import config  # noqa: F401
