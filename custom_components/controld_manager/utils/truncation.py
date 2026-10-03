"""Pure helpers that signal truncated read results.

A capped result must never be presented as complete. Ranked and paged surfaces
signal truncation differently because only the paged surface has any notion of
position, and neither exposes a total.
"""

from __future__ import annotations

from typing import Any


def build_limit_meta(applied_limit: int, returned_count: int) -> dict[str, Any]:
    """Return truncation metadata for a capped ranked read.

    A ranked response that returns at least the requested limit is treated as
    truncated, because the endpoint exposes no total to compare against.
    """
    return {
        "applied_limit": applied_limit,
        "truncated": returned_count >= applied_limit,
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
