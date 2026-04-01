"""Config flow placeholder for Control D Manager."""

from __future__ import annotations

from typing import Any, Self

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class ControlDManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Control D Manager."""

    VERSION = 1
    MINOR_VERSION = 1

    def is_matching(self, other_flow: Self) -> bool:
        """Return whether another flow matches this one."""
        del other_flow
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain that the runtime implementation is not ready yet."""
        del user_input
        return self.async_abort(reason="not_implemented")