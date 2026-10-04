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
    ACTIVITY_ACTIONS,
    ACTIVITY_TRIGGERS,
    CATALOG_TYPES,
    DNS_RECORD_TYPES,
    DOMAIN,
    SERVICE_FIELD_CATALOG_TYPE,
    SERVICE_FIELD_CLIENT_ID,
    SERVICE_FIELD_CLIENT_LIMIT,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_DESTINATION_COUNTRY,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_DOMAIN,
    SERVICE_FIELD_ENDPOINT_ID,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_PAGE,
    SERVICE_FIELD_PAGE_SIZE,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_FIELD_PROTOCOL,
    SERVICE_FIELD_QUERY_ACTION,
    SERVICE_FIELD_RECORD_TYPE,
    SERVICE_FIELD_SEARCH,
    SERVICE_FIELD_SORT_ORDER,
    SERVICE_FIELD_SOURCE_ASN,
    SERVICE_FIELD_SOURCE_COUNTRY,
    SERVICE_FIELD_SOURCE_ISP,
    SERVICE_FIELD_STATUS_CODE,
    SERVICE_FIELD_TRIGGER,
    SERVICE_FIELD_TRIGGER_VALUE,
    SERVICE_FIELD_WINDOW,
    SERVICE_GET_ACCOUNT_OVERVIEW,
    SERVICE_GET_ACTIVITY_LOG,
    SERVICE_GET_CATALOG,
    SERVICE_GET_INVENTORY,
    SERVICE_TEST_DOMAIN,
)
from .llm_tools_common import as_list, format_tool_name
from .utils.time_window import ACTIVITY_LOG_WINDOWS, DEFAULT_ACTIVITY_LOG_WINDOW

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

    # Most read services take the Control D profile PK straight through, but
    # `get_catalog` targets profiles through the Home Assistant device registry,
    # so its tool has to translate the PK first.
    _profile_id_is_device_id: bool = False

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

    def _translate_profile_ids(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Map Control D profile PKs onto the device ids this service targets.

        Only applied where the service declares a Home Assistant device selector.
        The model is handed a profile PK by the read tools, so the translation
        keeps one identifier in play rather than exposing an unpublished second
        one.
        """
        raw_profile_ids = args.get(SERVICE_FIELD_PROFILE_ID)
        if not self._profile_id_is_device_id or raw_profile_ids is None:
            return args
        entry = hass.config_entries.async_get_entry(self._entry_id)
        runtime = getattr(entry, "runtime_data", None)
        device_manager = getattr(getattr(runtime, "managers", None), "device", None)
        if device_manager is None:
            return args
        return {
            **args,
            SERVICE_FIELD_PROFILE_ID: [
                device_manager.profile_device_ids.get(profile_pk, profile_pk)
                for profile_pk in as_list(raw_profile_ids)
            ],
        }

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the backing service and return the wrapped payload."""
        service_data = self._translate_profile_ids(hass, self._args(tool_input))
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
        "`get_activity_log` for that.\n"
        "\n"
        "`status` is Control D's 0/1 account flag: 1 when the account is "
        "enabled, 0 when it is disabled. Quote the account `endpoint_count`, "
        "not a sum of the profile rows. An endpoint attached to more than one "
        "profile is counted under each of them, so those rows deliberately "
        "total more than the account figure."
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


class GetActivityLogTool(_ControlDReadTool):
    """Report per-record DNS queries for a recent window."""

    name = format_tool_name("get_activity_log")
    title = "Get activity log"
    description = (
        "Report individual DNS queries and what Control D did with each one. "
        "Every record carries the domain, the action taken (blocked, bypassed, "
        "redirected, or failed), the endpoint and client, the protocol and "
        "record type, the source and destination geography, and — most "
        "importantly — the `trigger` and `triggerValue` that caused the action "
        "(a filter, a service, one of your own custom rules, the default rule, "
        "a global rule, or rebind protection).\n"
        "\n"
        'This is the tool for "why was this blocked?" and "what has this '
        'device been doing?" Use it when you need the specific cause on a '
        "specific query. For aggregate counts (how much was blocked in total) "
        "use `get_account_overview`, and to ask about one domain on one endpoint "
        "in a single call use `test_domain`.\n"
        "\n"
        "Defaults to the last hour across the whole account. Narrow the window "
        "and the scope rather than paging through everything: the activity log "
        "is a recent-detail surface and a page can be large. Filter by "
        "`profile_id`, `endpoint_id`, or `client_id` (which requires an "
        "endpoint), by `query_action` to see only blocks or only passes, or by "
        "`search` to match a domain substring.\n"
        "\n"
        "Retention is limited (roughly 33 days, and a user can shorten it or "
        "turn logging off), so an empty result may mean no matching traffic, a "
        "window that has expired, or logging being disabled — say which you "
        "cannot distinguish rather than reporting that nothing happened. A full "
        "page sets `has_more`; there is no total, so never imply one. `status_code` "
        "is the DNS response code, and `rcode` is not an accepted parameter."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WINDOW,
                default=DEFAULT_ACTIVITY_LOG_WINDOW,
                description=(
                    "Optional. How far back to look. One of "
                    f"{', '.join(ACTIVITY_LOG_WINDOWS)}; defaults to "
                    f"{DEFAULT_ACTIVITY_LOG_WINDOW}. Keep it short unless you "
                    "really need a wider view."
                ),
            ): vol.In(ACTIVITY_LOG_WINDOWS),
            vol.Optional(
                SERVICE_FIELD_SEARCH,
                description=(
                    "Optional. A substring to match against the queried domain, "
                    "for example 'netflix'. This is a substring match, not an "
                    "exact domain."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_QUERY_ACTION,
                description=(
                    "Optional. Filter by what was done: 'blocked', 'bypassed', "
                    "'redirected', or 'failed'. Omit to return all actions."
                ),
            ): vol.In(ACTIVITY_ACTIONS),
            vol.Optional(
                SERVICE_FIELD_TRIGGER,
                description=(
                    "Optional. Filter by what caused the action. Use 'filter' "
                    "for a blocklist, 'service' for a service, 'custom' for one "
                    "of your own rules, 'default' for the default rule. Pair "
                    "with trigger_value to name the specific cause."
                ),
            ): vol.In(ACTIVITY_TRIGGERS),
            vol.Optional(
                SERVICE_FIELD_TRIGGER_VALUE,
                description=(
                    "Optional. The specific cause, used with `trigger` — for "
                    "example 'x-hagezi-light' for a filter or 'instagram' for a "
                    "service. Pass the raw value exactly as reported; do not "
                    "invent a label."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One Control D profile id (from "
                    "get_account_overview) to scope the result to that profile."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Optional. One or more endpoint device_ids (from "
                    "get_inventory) to scope the result. Provide a list to cover "
                    "several endpoints at once."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_CLIENT_ID,
                description=(
                    "Optional. One client id (from get_inventory with "
                    "detail 'full') to scope the result to a single client. "
                    "Requires endpoint_id as well."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_PROTOCOL,
                description=(
                    "Optional. DNS transport to filter by, such as 'doh', "
                    "'dot', 'doq', 'doh3', or 'legacy' for plain DNS."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_SOURCE_COUNTRY,
                description=(
                    "Optional. One or more source country codes to filter by, "
                    "such as 'US'."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_DESTINATION_COUNTRY,
                description=(
                    "Optional. A destination country code to filter by. This is "
                    "only available on the activity log, not on aggregate counts."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_SOURCE_ISP,
                description="Optional. A source ISP name to filter by.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_SOURCE_ASN,
                description="Optional. A source ASN to filter by.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_STATUS_CODE,
                description=(
                    "Optional. The DNS response code to filter by, as a number "
                    "(for example 0 for a normal answer or 3 for NXDOMAIN)."
                ),
            ): vol.Coerce(int),
            vol.Optional(
                SERVICE_FIELD_RECORD_TYPE,
                description=(
                    "Optional. The DNS record type to filter by, such as 'A', "
                    "'AAAA', or 'HTTPS'."
                ),
            ): vol.In(DNS_RECORD_TYPES),
            vol.Optional(
                SERVICE_FIELD_PAGE,
                default=0,
                description=(
                    "Optional. Zero-based page number. Defaults to 0, the newest "
                    "records first."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(
                SERVICE_FIELD_PAGE_SIZE,
                default=50,
                description=(
                    "Optional. Records per page, 1 to 500. Defaults to 50. A "
                    "larger page costs more context; narrow the filters instead "
                    "if you need less."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
            vol.Optional(
                SERVICE_FIELD_SORT_ORDER,
                default="desc",
                description=(
                    "Optional. 'desc' (default) returns newest first; 'asc' "
                    "returns oldest first."
                ),
            ): vol.In(("desc", "asc")),
        }
    )
    _service = SERVICE_GET_ACTIVITY_LOG
    _response_type = "activity_log"


class TestDomainTool(_ControlDReadTool):
    """Report the policy verdict for one domain on one endpoint."""

    name = format_tool_name("test_domain")
    title = "Test domain"
    description = (
        "Ask Control D what would happen if one endpoint resolved one domain, "
        "without waiting for real traffic. This is the cheapest way to answer "
        '"is this blocked?" and "what would block it?" — one call, one '
        "domain, one endpoint.\n"
        "\n"
        "The result reports whether the domain is blocked and, when it is, the "
        "profile that decided it, the matched rule or list, and the cause "
        "(`source` is 'filter', 'service', 'custom', or 'default' after "
        "translation, with the raw value in `source_label`). A blocked answer "
        "comes back as `is_blocked: true` with a REFUSED response code; that is "
        "a normal result, not an error. If no policy matched, the domain is "
        "simply not blocked and the cause fields are empty.\n"
        "\n"
        "Use `get_inventory` to find the endpoint device_id, and "
        "`get_activity_log` when you want the real traffic history rather than a "
        "hypothetical answer. The lookup is diagnostic and does not appear in "
        "the activity log."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id to test, from "
                    "get_inventory. The verdict depends on which endpoint asks, "
                    "because each endpoint enforces its own profile."
                ),
            ): str,
            vol.Required(
                SERVICE_FIELD_DOMAIN,
                description=(
                    "Required. The domain to test, for example 'google.com'. "
                    "Use a bare domain, not a URL."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_RECORD_TYPE,
                default="A",
                description=(
                    "Optional. The DNS record type to test. Defaults to 'A'; use "
                    "'AAAA' for IPv6 or 'HTTPS' for HTTPS records."
                ),
            ): vol.In(DNS_RECORD_TYPES),
        }
    )
    _service = SERVICE_TEST_DOMAIN
    _response_type = "domain_test"


class GetCatalogTool(_ControlDReadTool):
    """Report the Control D configuration catalog for one profile scope."""

    name = format_tool_name("get_catalog")
    title = "Get catalog"
    description = (
        "Report Control D configuration and its current state for one profile "
        "scope. Use it to resolve the exact identifiers the control tools need "
        "before changing anything, and to answer what a profile is configured "
        "to do.\n"
        "\n"
        "Choose one `catalog_type` per call:\n"
        "- `filters` — blocklists, each with whether it is enabled, whether it "
        "supports modes, and its current mode.\n"
        "- `services` — services, each with its category and current mode.\n"
        "- `rules` — rule folders and the custom rules inside them, with action, "
        "enabled state, and comment.\n"
        "- `profile_options` — options such as AI Malware, Safe Search, and "
        "Restricted YouTube, with their current value.\n"
        "- `default_rule` — each profile's catch-all action.\n"
        "\n"
        "Scope it with `profile_id`; without one it returns every managed "
        "profile, which is usually more than you need. The service catalog alone "
        "has over a thousand entries, so set `limit` and treat `truncated` as a "
        "signal to narrow the scope rather than assuming you have everything."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_CATALOG_TYPE,
                description=(
                    "Required. One of 'filters', 'services', 'rules', "
                    "'profile_options', or 'default_rule'."
                ),
            ): vol.In(CATALOG_TYPES),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One or more profile ids (from "
                    "get_account_overview) to scope the catalog. Strongly "
                    "recommended; without it the result covers every profile."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_LIMIT,
                default=50,
                description=(
                    "Optional. Maximum items to return, 1 to 500. Defaults to "
                    "50. `truncated` reports whether the cap was reached, so a "
                    "capped catalog is never mistaken for a complete one."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        }
    )
    _service = SERVICE_GET_CATALOG
    _response_type = "catalog"
    _profile_id_is_device_id = True


def build_read_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [
        GetInventoryTool(entry_id=entry_id),
        GetActivityLogTool(entry_id=entry_id),
        TestDomainTool(entry_id=entry_id),
        GetCatalogTool(entry_id=entry_id),
    ]


def build_account_overview_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the account overview tool bound to one config entry."""
    return [GetAccountOverviewTool(entry_id=entry_id)]
