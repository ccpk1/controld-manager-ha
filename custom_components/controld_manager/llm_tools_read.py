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
    SERVICE_FIELD_CLIENT_LIMIT,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_ENDPOINT_ID,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_GET_ACCOUNT_OVERVIEW,
    SERVICE_GET_INVENTORY,
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


class GetInventoryTool(_ControlDReadTool):
    """Report the account topology: profiles, endpoints, and clients."""

    name = format_tool_name("get_inventory")
    title = "Get inventory"
    description = (
        "Report the account's structure: every profile, every endpoint, and "
        "(with full detail) every client seen under an endpoint. Use it to "
        "resolve the identifiers and names that the other tools need before "
        "acting, and to answer questions about how the account is organized.\n"
        "\n"
        "The words are not interchangeable. A *profile* is a policy container. "
        "An *endpoint* is a top-level protected row (a router segment, a ctrld "
        "instance, or an individually protected device). A *client* is something "
        "seen under an endpoint. An endpoint reports into its own profile, but "
        "may be attached to more than one; `attached_profiles` lists them all.\n"
        "\n"
        "A client follows its parent endpoint's profile. A client that has been "
        "made into its own standalone device becomes an endpoint as well: it "
        "appears in `endpoints` with its own profile, and in `clients` with "
        "`is_standalone_endpoint: true` and its `own_endpoint_id` set. A client "
        "with `is_standalone_endpoint: false` only follows its parent.\n"
        "\n"
        "Defaults to `detail: summary`, which returns profiles and endpoints but "
        "no client rows. Use `detail: full` to add clients, and narrow with "
        "`profile_id` or `endpoint_id` rather than pulling every client in the "
        "account. Client rows are capped by `client_limit`, and "
        "`clients_truncated` says whether the cap was hit; narrow the filter "
        "instead of treating a capped list as complete.\n"
        "\n"
        "All counts come from the same runtime state the integration's own "
        "entities use, so they always agree with the sensors."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                default="summary",
                description=(
                    "Optional. 'summary' (default) returns profiles and "
                    "endpoints. 'full' also returns the client rows under the "
                    "selected endpoints."
                ),
            ): vol.In(("summary", "full")),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One Control D profile id, or a list of them "
                    "(from get_account_overview), to narrow the result to those "
                    "profiles. Omit to include every profile."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Optional. One endpoint device_id, or a list of them, to "
                    "narrow the result. Omit to include every endpoint."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_CLIENT_LIMIT,
                default=100,
                description=(
                    "Optional. Defaults to 100, maximum 500. Caps the client "
                    "rows returned only when detail is 'full'. `clients_truncated` "
                    "reports whether the cap was reached, so a capped list is "
                    "never mistaken for a complete one."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        }
    )
    _service = SERVICE_GET_INVENTORY
    _response_type = "inventory"


def build_read_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [GetInventoryTool(entry_id=entry_id)]


def build_account_overview_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the account overview tool bound to one config entry."""
    return [GetAccountOverviewTool(entry_id=entry_id)]
