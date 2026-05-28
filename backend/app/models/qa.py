from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class QAItem(BaseModel):
    item: str
    status: Literal["pass", "warn", "fail"]
    note: str = ""


class QAOutput(BaseModel):
    checklist: list[QAItem] = []
    overall_status: Literal["pass", "warn", "fail"] = "warn"
    user_action_required: list[str] = []
