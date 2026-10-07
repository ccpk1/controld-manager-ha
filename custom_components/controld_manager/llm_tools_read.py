"""LLM read tools for Control D Manager.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names below are
never imported on older Home Assistant.

Each read tool delegates to an existing service and wraps the response in the
documented envelope. The tool injects its own ``config_entry_id`` so the caller
never selects an account.

Tool schemas are built on ``probatio``, not ``voluptuous``. Home Assistant
declares ``llm.Tool.parameters`` as ``probatio.Schema``, and probatio replaced
voluptuous as the validation engine in Core 2026.10. HA's own tool integrations
import probatio directly.
"""

from __future__ import annotations

from typing import Any, Final, cast, override

import probatio
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
    SERVICE_FIELD_ENDPOINT_NAME,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_PAGE,
    SERVICE_FIELD_PAGE_SIZE,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_FIELD_PROFILE_NAME,
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
from .llm_tools_common import READ_INJECTION, as_list, format_tool_name, time_zone_note
from .utils.time_window import ACTIVITY_LOG_WINDOWS, DEFAULT_ACTIVITY_LOG_WINDOW

# Every read tool queries the Control D cloud API rather than local state, so
# it reaches outside Home Assistant even though it changes nothing.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)


class _ControlDReadTool(llm.Tool):
    """Base class for a Control D read tool backed by a service."""

    integration = DOMAIN
    annotations = _READ_ANNOTATIONS

    # Prepended at construction rather than written into each description, so a
    # new read tool cannot be added without the family block.
    _injection: Final = READ_INJECTION

    _service: str
    _response_type: str

    # Most read services take the Control D profile PK straight through, but
    # `get_catalog` targets profiles through the Home Assistant device registry,
    # so its tool has to translate the PK first.
    _profile_id_is_device_id: bool = False

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id
        if self.description:
            self.description = f"{self._injection}\n\n{self.description}"

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
        "Account-level counts and block statistics, plus one row per profile.\n"
        "\n"
        "Call this first: it is the only result carrying `system_model`.\n"
        "\n"
        "- `region` — analytics region token.\n"
        "- `endpoint_count` — rows in `/devices`. `client_count` — devices seen "
        "under them. `protected_device_count` — the two added; what DNS "
        "protection covers. Exact here, a single pass.\n"
        "- `profiles[]` — `profile_id`, `profile_name`, "
        "`protected_device_count`, `paused`, and per-profile "
        "blocked/bypassed/redirected counts. These rows do **not** sum to the "
        "account figure: an endpoint on two profiles counts under each. Quote "
        "the account value.\n"
        "- `analytics` — totals and ratio for the account's own window, which "
        "may not be a round hour. Block counts exist only where analytics "
        "logging is on.\n"
        "\n"
        "Per-query detail is `get_activity_log`."
    )
    parameters = probatio.Schema({})
    _service = SERVICE_GET_ACCOUNT_OVERVIEW
    _response_type = "account_overview"


class GetInventoryTool(_ControlDReadTool):
    """Report the account topology: profiles, endpoints, and clients."""

    name = format_tool_name("get_inventory")
    title = "Get inventory"
    description = (
        "Account structure: every profile, every endpoint, and with "
        "`detail: full` every client under them. The source for `profile_id`, "
        "`endpoint_id`, and `client_id` before any write.\n"
        "\n"
        "- `enforced_profiles` — every profile the endpoint enforces, in order, "
        "slot named. Both apply: the engine merges them before matching, so the "
        "secondary blocks just as the primary does. Check every entry when "
        "explaining a block.\n"
        "- `detail` — `summary` (default) returns profiles and endpoints; "
        "`full` adds clients. Narrow with `profile_id` or `endpoint_id` rather "
        "than pulling every client.\n"
        "- Client rows — `last_active` is when Control D last saw the device, so "
        "recent means live. For a promoted client it reports the endpoint's "
        "activity, because the traffic is attributed there once promoted. "
        "`mac_address` is the second signal: blank or all-zeros is expected "
        "where the router relays without a MAC, so it does **not** mean the row "
        "is stale. The two are independent — prefer a row that is both recent "
        "and has a usable MAC.\n"
        "- `analytics_logging` — the endpoint's logging level: `'None'`, "
        "`'Some'`, or `'Full'`. `set_endpoint_logging` reads this to name the "
        "level it replaces.\n"
        "- `advanced` — the dashboard's Advanced Settings. Read-only: no tool "
        "here changes them, so report the value, never offer to set it.\n"
        "- `analytics_logging` — `None`, `Some`, or `Full`, the level "
        "`set_endpoint_logging` sets. It sits outside `advanced` because it is "
        "the one endpoint setting a tool here can change."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_DETAIL,
                default="summary",
                description=(
                    "Optional. 'summary' (default) returns profiles and "
                    "endpoints. 'full' also returns the client rows under the "
                    "selected endpoints."
                ),
            ): probatio.In(("summary", "full")),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One Control D profile id, or a list of them "
                    "(from get_account_overview), to narrow the result to those "
                    "profiles. Omit to include every profile."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME,
                description=(
                    "Optional. One Control D profile name, or a list of them, "
                    "as an alternative to `profile_id`. Names are not unique, "
                    "so an unknown or ambiguous name is an error rather than a "
                    "silently widened scope. `profile_id` wins when both are "
                    "given."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Optional. One endpoint device_id, or a list of them, to "
                    "narrow the result. Omit to include every endpoint."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_NAME,
                description=(
                    "Optional. One endpoint display name, or a list of them, "
                    "from get_inventory, as an alternative to `endpoint_id`. "
                    "This is the field to use when you know the device by name. "
                    "Names are not unique, so an unknown or ambiguous name is "
                    "an error rather than a silently widened scope. "
                    "`endpoint_id` wins when both are given."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_CLIENT_LIMIT,
                default=100,
                description=(
                    "Optional. Defaults to 100, maximum 500. Caps the client "
                    "rows returned only when detail is 'full'. `clients_truncated` "
                    "reports whether the cap was reached, so a capped list is "
                    "never mistaken for a complete one."
                ),
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=500)),
        }
    )
    _service = SERVICE_GET_INVENTORY
    _response_type = "inventory"


class GetActivityLogTool(_ControlDReadTool):
    """Report per-record DNS queries for a recent window."""

    name = format_tool_name("get_activity_log")
    title = "Get activity log"
    description = (
        "Individual DNS queries and what Control D did with each: the tool for "
        '"why was this blocked?".\n'
        "\n"
        "- `trigger` + `triggerValue` — the cause. `filter` (a blocklist), "
        "`service`, `custom` (a rule of yours), `default` (the catch-all), "
        "`grule`, `rebind`. `triggerValue` is absent when there is no list to "
        "name — for `default` that absence is the answer, not missing data.\n"
        "- `action_label` — the verdict. The raw `action` codes are not "
        "contiguous and one is negative: -1 failed, 0 blocked, 1 bypassed, "
        "3 redirected.\n"
        "- `profileId` — which profile decided, which matters when an endpoint "
        "enforces more than one. `endpointName` is resolved from current "
        "inventory and empty for a device no longer held; `endpointId` is "
        "always present.\n"
        "- `status_code` — DNS response code. `rcode` is not accepted.\n"
        "\n"
        "To diagnose a block: widen the window, set `query_action` to "
        "`blocked`, then resolve `trigger`/`triggerValue` with `get_catalog`. "
        "Change it with the matching tool. Defaults to the last hour "
        "account-wide. Narrow with `window`, `profile_id`, `endpoint_id`, "
        "`client_id` (needs an endpoint), `query_action`, or `search`. **One "
        "page is not the window** — check `has_more`. There is no total, so "
        "never imply one."
    )

    def __init__(self, *, entry_id: str, time_zone: str | None = None) -> None:
        """Bind the tool and name the user's timezone when it is known.

        Appended here rather than written into the class text, because the
        timezone is a user setting and this is the one tool that reports times.
        """
        super().__init__(entry_id=entry_id)
        note = time_zone_note(time_zone)
        if note:
            self.description = f"{self.description}\n\n{note}"

    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_WINDOW,
                default=DEFAULT_ACTIVITY_LOG_WINDOW,
                description=(
                    "Optional. How far back to look. One of "
                    f"{', '.join(ACTIVITY_LOG_WINDOWS)}; defaults to "
                    f"{DEFAULT_ACTIVITY_LOG_WINDOW}. Keep it short unless you "
                    "really need a wider view."
                ),
            ): probatio.In(ACTIVITY_LOG_WINDOWS),
            probatio.Optional(
                SERVICE_FIELD_SEARCH,
                description=(
                    "Optional. A substring to match against the queried domain, "
                    "for example 'netflix'. This is a substring match, not an "
                    "exact domain."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_QUERY_ACTION,
                description=(
                    "Optional. Filter by what was done: 'blocked', 'bypassed', "
                    "'redirected', or 'failed'. Omit to return all actions."
                ),
            ): probatio.In(ACTIVITY_ACTIONS),
            probatio.Optional(
                SERVICE_FIELD_TRIGGER,
                description=(
                    "Optional. Filter by what caused the action. Use 'filter' "
                    "for a blocklist, 'service' for a service, 'custom' for one "
                    "one of your own rules, 'default' for the default rule, "
                    "'grule' for a global rule, or 'rebind' for rebind "
                    "protection. Pair with trigger_value to name the specific "
                    "cause."
                ),
            ): probatio.In(ACTIVITY_TRIGGERS),
            probatio.Optional(
                SERVICE_FIELD_TRIGGER_VALUE,
                description=(
                    "Optional. The specific cause, used with `trigger` — for "
                    "example 'x-hagezi-light' for a filter or 'instagram' for a "
                    "service. Pass the raw value exactly as reported; do not "
                    "invent a label."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One Control D profile id (from "
                    "get_account_overview) to scope the result to that profile."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME,
                description=(
                    "Optional. One profile name, as an alternative to "
                    "`profile_id`. A name that matches more than one profile is "
                    "an error, because this read covers at most one profile."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Optional. One or more endpoint device_ids (from "
                    "get_inventory) to scope the result. Provide a list to cover "
                    "several endpoints at once."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_NAME,
                description=(
                    "Optional. One or more endpoint display names (from "
                    "get_inventory), as an alternative to `endpoint_id`. Use "
                    "this when you know the device by name. An unknown or "
                    "ambiguous name is an error rather than a silently widened "
                    "scope."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_CLIENT_ID,
                description=(
                    "Optional. One client id (from get_inventory with "
                    "detail 'full') to scope the result to a single client. "
                    "Requires endpoint_id as well."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_PROTOCOL,
                description=(
                    "Optional. DNS transport to filter by, such as 'doh', "
                    "'dot', 'doq', 'doh3', or 'legacy' for plain DNS."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_SOURCE_COUNTRY,
                description=(
                    "Optional. One or more source country codes to filter by, "
                    "such as 'US'."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_DESTINATION_COUNTRY,
                description=(
                    "Optional. A destination country code to filter by. This is "
                    "only available on the activity log, not on aggregate counts."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_SOURCE_ISP,
                description="Optional. A source ISP name to filter by.",
            ): str,
            probatio.Optional(
                SERVICE_FIELD_SOURCE_ASN,
                description="Optional. A source ASN to filter by.",
            ): str,
            probatio.Optional(
                SERVICE_FIELD_STATUS_CODE,
                description=(
                    "Optional. The DNS response code to filter by, as a number "
                    "(for example 0 for a normal answer or 3 for NXDOMAIN)."
                ),
            ): probatio.Coerce(int),
            probatio.Optional(
                SERVICE_FIELD_RECORD_TYPE,
                description=(
                    "Optional. The DNS record type to filter by. One of "
                    "'A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'PTR', 'SRV', "
                    "or 'HTTPS'; defaults to 'A'."
                ),
            ): probatio.In(DNS_RECORD_TYPES),
            probatio.Optional(
                SERVICE_FIELD_PAGE,
                default=0,
                description=(
                    "Optional. Zero-based page number. Defaults to 0, the newest "
                    "records first."
                ),
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=0)),
            probatio.Optional(
                SERVICE_FIELD_PAGE_SIZE,
                default=50,
                description=(
                    "Optional. Records per page, 1 to 500. Defaults to 50. A "
                    "larger page costs more context; narrow the filters instead "
                    "if you need less."
                ),
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=500)),
            probatio.Optional(
                SERVICE_FIELD_SORT_ORDER,
                default="desc",
                description=(
                    "Optional. 'desc' (default) returns newest first; 'asc' "
                    "returns oldest first."
                ),
            ): probatio.In(("desc", "asc")),
        }
    )
    _service = SERVICE_GET_ACTIVITY_LOG
    _response_type = "activity_log"


class TestDomainTool(_ControlDReadTool):
    """Report the policy verdict for one domain on one endpoint."""

    name = format_tool_name("test_domain")
    title = "Test domain"
    description = (
        "What Control D would do if one endpoint resolved one domain, without "
        'waiting for traffic. The cheapest "is this blocked?".\n'
        "\n"
        "- `is_blocked` — the verdict. A block returns REFUSED; that is a "
        "normal result, not an error.\n"
        "- `source` / `source_label` — the cause after translation, and the raw "
        "value naming the list or rule.\n"
        "- **Redirecting is not blocking.** A redirect reports "
        "`is_blocked: false` with a resolved address. Read `action` to tell "
        "block, bypass, and redirect apart.\n"
        "\n"
        "Needs an `endpoint_id` — the verdict is per-endpoint, because each "
        "enforces its own profile. Diagnostic only: the lookup never appears in "
        "the activity log. Use `get_activity_log` for real traffic."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Optional. The endpoint device_id to test, from "
                    "get_inventory. The verdict depends on which endpoint asks, "
                    "because each endpoint enforces its own profile. Provide "
                    "this or `endpoint_name`."
                ),
            ): str,
            probatio.Required(
                SERVICE_FIELD_DOMAIN,
                description=(
                    "Required. The domain to test, for example 'google.com'. "
                    "Use a bare domain, not a URL."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_NAME,
                description=(
                    "Optional. The endpoint display name to test, from "
                    "get_inventory, as an alternative to `endpoint_id`. Exactly "
                    "one endpoint must be named in total."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_RECORD_TYPE,
                default="A",
                description=(
                    "Optional. The DNS record type to test. One of 'A', "
                    "'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'PTR', 'SRV', or "
                    "'HTTPS'; defaults to 'A'."
                ),
            ): probatio.In(DNS_RECORD_TYPES),
        }
    )
    _service = SERVICE_TEST_DOMAIN
    _response_type = "domain_test"


class GetCatalogTool(_ControlDReadTool):
    """Report the Control D configuration catalog for one profile scope."""

    name = format_tool_name("get_catalog")
    title = "Get catalog"
    description = (
        "A profile's configuration and current state: the source for filter, "
        "service, option, and rule ids before changing anything.\n"
        "\n"
        "One `catalog_type` per call: `filters`, `services`, `rules`, "
        "`profile_options`, `default_rule`, or `redirect_locations`. The last "
        "is account-wide and ignores `profile_id` — it supplies the 3-letter "
        "code a redirect's `redirect_target` takes.\n"
        "\n"
        "Scope with `profile_id`; without it every managed profile is "
        "returned.\n"
        "\n"
        "The service catalog runs past a thousand entries and `limit` caps at "
        "500 with no paging, so it cannot be listed exhaustively. Use `search` "
        "to find a named row — `search='apple'` finds the Apple service in one "
        "row where listing never would. It matches the row's own name and ids, "
        "not its profile columns; `item_count` reports the true match count."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_CATALOG_TYPE,
                description=(
                    "Required. One of 'filters', 'services', 'rules', "
                    "'profile_options', 'default_rule', or 'redirect_locations'."
                ),
            ): probatio.In(CATALOG_TYPES),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. One or more profile ids (from "
                    "get_account_overview) to scope the catalog. Strongly "
                    "recommended; without it the result covers every profile."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME,
                description=(
                    "Optional. One profile name, or a list of them, as an "
                    "alternative to `profile_id`. `profile_id` wins when both "
                    "are given."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_SEARCH,
                description=(
                    "Optional. A substring matched case-insensitively against "
                    "each row's own name and ids, for example 'apple' or "
                    "'hagezi'. Use this to find one named entry in a catalog "
                    "too large to list; it is the reliable way to locate a "
                    "service, filter, or option by name."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_LIMIT,
                default=50,
                description=(
                    "Optional. Maximum items to return, 1 to 500. Defaults to "
                    "50. `truncated` reports whether the cap was reached, so a "
                    "capped catalog is never mistaken for a complete one."
                ),
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=500)),
        }
    )
    _service = SERVICE_GET_CATALOG
    _response_type = "catalog"
    _profile_id_is_device_id = True


def build_read_tools(*, entry_id: str, time_zone: str | None = None) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [
        GetInventoryTool(entry_id=entry_id),
        GetActivityLogTool(entry_id=entry_id, time_zone=time_zone),
        TestDomainTool(entry_id=entry_id),
        GetCatalogTool(entry_id=entry_id),
    ]


def build_account_overview_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the account overview tool bound to one config entry."""
    return [GetAccountOverviewTool(entry_id=entry_id)]
