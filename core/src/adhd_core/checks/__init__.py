"""Role checks. Each role maps to one function: (bundle, slot) -> list of checks."""

from __future__ import annotations

from typing import Any, Callable

from ..bundle import Bundle
from ..result import Check
from .story import check_story
from .storyboard import check_storyboard

RoleCheck = Callable[[Bundle, dict[str, Any]], list[Check]]

ROLE_CHECKS: dict[str, RoleCheck] = {
    "story": check_story,
    "title": check_story,
    "storyboard": check_storyboard,
}
