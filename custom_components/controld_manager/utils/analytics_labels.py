"""Pure helpers that resolve Control D analytics slugs to human labels.

Ranked analytics responses return internal slugs (``x-hagezi-light``,
``ai_malware``). Some resolve against the profile catalogs; a few documented
variants do not appear in any catalog and are mapped here. Resolution never
invents a label: an unknown slug is returned as its own label and flagged as
unresolved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Documented ranked values that appear in no profile catalog. Kept deliberately
# small; the catalogs remain the primary source. `ads` itself resolves from the
# profile filter catalog ("Ads & Trackers"), so only these variants are added.
ANALYTICS_SLUG_ALIASES: Mapping[str, str] = {
    "ads_small": "Ads & Trackers - Relaxed",
    "ads_medium": "Ads & Trackers - Balanced",
}


def build_analytics_label_map(
    *,
    filters: Iterable[Mapping[str, Any]] = (),
    external_filters: Iterable[Mapping[str, Any]] = (),
    ip_filters: Iterable[Mapping[str, Any]] = (),
    options: Iterable[Mapping[str, Any]] = (),
    services: Iterable[Mapping[str, Any]] = (),
) -> dict[str, str]:
    """Build a ranked-value to label map from catalog rows.

    Sources are applied in priority order and never overwrite an existing entry,
    so a slug present in more than one catalog keeps the first (filter) label.
    """
    label_map: dict[str, str] = dict(ANALYTICS_SLUG_ALIASES)
    for rows in (filters, external_filters, ip_filters, options, services):
        for row in rows:
            slug = _optional_string(row.get("PK"))
            label = _row_label(row)
            if slug is not None and label is not None and slug not in label_map:
                label_map[slug] = label
    return label_map


def resolve_ranked_rows(
    rows: Iterable[Mapping[str, Any]],
    label_map: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Return ranked rows carrying both the raw value and its resolved label."""
    resolved_rows: list[dict[str, Any]] = []
    for row in rows:
        raw_value = _optional_string(row.get("value"))
        if raw_value is None:
            continue
        resolved_rows.append(
            {
                "value": raw_value,
                "label": label_map.get(raw_value, raw_value),
                "label_resolved": raw_value in label_map,
                "count": row.get("count"),
            }
        )
    return resolved_rows


def _row_label(row: Mapping[str, Any]) -> str | None:
    """Return the best human label from one catalog row."""
    return _optional_string(row.get("name")) or _optional_string(row.get("title"))


def _optional_string(value: Any) -> str | None:
    """Return a non-empty string value or None."""
    return value if isinstance(value, str) and value else None
