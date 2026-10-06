"""Pure helpers for relative analytics time windows.

Callers ask for a recent window by label (``1h``, ``7d``) rather than absolute
timestamps, which avoids timezone mistakes and keeps a request small. The label
is validated against a fixed set so a caller cannot ask for an unbounded range.
"""

from __future__ import annotations

from datetime import timedelta

# Short, explicit choices. Ordered from narrowest to widest.
WINDOW_15_MINUTES = "15m"
WINDOW_1_HOUR = "1h"
WINDOW_6_HOURS = "6h"
WINDOW_24_HOURS = "24h"
WINDOW_7_DAYS = "7d"
WINDOW_30_DAYS = "30d"

ACTIVITY_LOG_WINDOWS: tuple[str, ...] = (
    WINDOW_15_MINUTES,
    WINDOW_1_HOUR,
    WINDOW_6_HOURS,
    WINDOW_24_HOURS,
    WINDOW_7_DAYS,
    WINDOW_30_DAYS,
)

DEFAULT_ACTIVITY_LOG_WINDOW = WINDOW_1_HOUR

_WINDOW_DELTAS: dict[str, timedelta] = {
    WINDOW_15_MINUTES: timedelta(minutes=15),
    WINDOW_1_HOUR: timedelta(hours=1),
    WINDOW_6_HOURS: timedelta(hours=6),
    WINDOW_24_HOURS: timedelta(hours=24),
    WINDOW_7_DAYS: timedelta(days=7),
    WINDOW_30_DAYS: timedelta(days=30),
}


def window_to_timedelta(label: str) -> timedelta:
    """Return the duration for a supported window label.

    Raises ``ValueError`` for an unknown label so a bad request fails loudly
    instead of silently querying an unintended period.
    """
    try:
        return _WINDOW_DELTAS[label]
    except KeyError as err:
        raise ValueError(f"Unsupported window {label!r}") from err
