"""LLM read tools for Control D Manager.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names below are
never imported on older Home Assistant.

Each read tool delegates to an existing service and wraps the response in the
documented envelope. The tool injects its own ``config_entry_id`` so the caller
never selects an account.
"""

from __future__ import annotations

from typing import Any, Final, cast, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_GET_ACCOUNT_OVERVIEW,
)
from .llm_tools_common import format_tool_name

# Every read tool is a bounded, read-only query against the user's own account.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
)


class _ControlDReadTool(llm.Tool):
    """Base class for a Control D read tool backed by a service."""

    integration = DOMAIN
    annotations = _READ_ANNOTATIONS

    _service: str
    _response_type: str

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    def _args(self, tool_input: llm.ToolInput) -> dict[str, Any]:
        """Return tool args validated against the declared schema.

        The LLM provider validates args, but an MCP client can call directly, so
        validate here to turn a missing or unknown argument into a clean error
        instead of a bare KeyError.
        """
        return cast(dict[str, Any], self.parameters(tool_input.tool_args))

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the backing service and return the wrapped payload."""
        service_data = self._args(tool_input)
        service_data[SERVICE_FIELD_CONFIG_ENTRY_ID] = self._entry_id
        result = await hass.services.async_call(
            DOMAIN,
            self._service,
            service_data,
            blocking=True,
            return_response=True,
            context=llm_context.context,
        )
        return llm.ToolResult(
            data={
                "result": result,
                "meta": {"response_type": self._response_type},
            },
        )


class GetAccountOverviewTool(_ControlDReadTool):
    """Report account-level counts and block statistics."""

    name = format_tool_name("get_account_overview")
    title = "Get account overview"
    description = (
        "Report the high-level state of the Control D account: the analytics "
        "region, how many profiles, endpoints, and router clients exist, and how "
        "many DNS queries were blocked, bypassed, or redirected in the current "
        "analytics window. It also lists one row per profile with that profile's "
        "endpoint count, paused state, and blocked, bypassed, and redirected "
        "counts.\n"
        "\n"
        "This is the orientation call. Start here to size the account and see "
        "which profile is doing what before asking a narrower question, and call "
        "it once per session unless something has changed.\n"
        "\n"
        "All counts come from the same runtime state the integration's own "
        "entities use, so they always agree with the sensors. Block counts only "
        "exist for endpoints that have analytics logging enabled, and the "
        "reported window is whatever the account returns, which may not be an "
        "exact round hour. This tool reads no per-query detail; use "
        "`get_activity_log` for that."
    )
    parameters = vol.Schema({})
    _service = SERVICE_GET_ACCOUNT_OVERVIEW
    _response_type = "account_overview"


def build_account_overview_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the account overview tool bound to one config entry."""
    return [GetAccountOverviewTool(entry_id=entry_id)]
