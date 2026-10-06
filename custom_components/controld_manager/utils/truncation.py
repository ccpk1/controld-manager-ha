"""Pure helpers that signal truncated read results.

A capped result must never be presented as complete. Ranked and paged surfaces
signal truncation differently because only the paged surface has any notion of
position, and neither exposes a total.
"""

from __future__ import annotations

from typing import Any


def build_limit_meta(applied_limit: int, total_count: int) -> dict[str, Any]:
    """Return truncation metadata for a capped read that knows its total.

    Truncation is exact here because the caller counts the items before applying
    the limit: a full result is only truncated when something was actually
    dropped. This is deliberately not the "a full page may mean more" rule, which
    applies to a surface that exposes no total to compare against. Reporting a
    complete result as truncated would tell a model it is missing data it has.
    """
    return {
        "applied_limit": applied_limit,
        "truncated": total_count > applied_limit,
    }


def build_page_meta(page: int, page_size: int, returned_count: int) -> dict[str, Any]:
    """Return paging metadata for a paged read that exposes no total.

    A full page means more records may exist; it does not confirm how many.
    """
    return {
        "page": page,
        "page_size": page_size,
        "has_more": returned_count >= page_size,
    }
