"""Constants for the Control D Manager integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "controld_manager"

DEFAULT_UPDATE_INTERVAL_ACCOUNT = timedelta(minutes=15)
DEFAULT_UPDATE_INTERVAL_ANALYTICS = timedelta(minutes=5)
DEFAULT_UPDATE_INTERVAL_SETTINGS = timedelta(minutes=2)

TRANS_KEY_NOT_IMPLEMENTED = "not_implemented"