"""Pure builder for the control-tool action result.

Control D write responses are not uniform: a filter write returns a map of every
filter, a service write returns a list, and a rule delete returns an empty body.
Wrapping the upstream response would therefore expose a different shape per tool,
so the action result is synthesized instead. The write response is used only as
confirmation that the call succeeded; the target and the reported states come
from what the tool resolved and requested.
"""

from __future__ import annotations

from typing import Any

ACTION_STATUS_APPLIED = "applied"
ACTION_STATUS_ALREADY_IN_STATE = "already_in_state"
ACTION_STATUS_FAILED = "failed"


def build_action_result(
    *,
    status: str,
    target: dict[str, Any],
    changed: bool,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    undo: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build one action-result payload.

    ``after`` states what the action requested, not a re-read of the box. ``undo``
    is the call that reverses the action, or ``None`` when nothing reverses it;
    callers must not describe an action with ``undo: None`` as reversible.
    """
    return {
        "status": status,
        "changed": changed,
        "target": target,
        "before": before,
        "after": after,
        "undo": undo,
        "warnings": warnings or [],
    }
