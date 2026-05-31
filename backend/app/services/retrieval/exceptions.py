"""Structured errors raised by the master-resume retrieval surface.

These are HTTP-shape carriers — the FastAPI handlers in
``app/routers/phases.py`` (Step 10 integration) translate them into the
status codes specified in ``docs/IMPLEMENTATION_PLAN.md`` §6a:

- :class:`MasterResumeRequiredError` → 409 ``master_resume_required``
- :class:`PromptBudgetExceededError` → 422 ``prompt_budget_exceeded``
"""

from __future__ import annotations


class MasterResumeRequiredError(Exception):
    """Raised when the user has no live ``MasterResumeChunk`` rows.

    HTTP 409 with ``{"code": "master_resume_required"}``.  The frontend
    routes the user to ``/profile`` so they can upload before retrying.
    """

    code = "master_resume_required"

    def __init__(self, message: str = "User has not uploaded a master resume."):
        super().__init__(message)


class PromptBudgetExceededError(Exception):
    """Raised when, after retrieval trimming, the prompt is still too big.

    HTTP 422 with ``{"code": "prompt_budget_exceeded", ...}``.  Carries
    the actual token count and the model's effective budget so the UI
    can render a useful message.
    """

    code = "prompt_budget_exceeded"

    def __init__(
        self,
        *,
        total_tokens: int,
        budget: int,
        model: str,
        message: str | None = None,
    ) -> None:
        self.total_tokens = total_tokens
        self.budget = budget
        self.model = model
        super().__init__(
            message
            or (
                f"prompt of {total_tokens} tokens exceeds the {budget}-token "
                f"budget for model {model!r} (after retrieval trimming)"
            )
        )


__all__ = [
    "MasterResumeRequiredError",
    "PromptBudgetExceededError",
]
