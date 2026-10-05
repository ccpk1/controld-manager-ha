"""LLM control tools for Control D Manager.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names below are
never imported on older Home Assistant.

Each control tool delegates to an existing service and returns the action-result
envelope. Every write service requires an admin user, so a non-admin caller is
rejected by the service layer rather than by the tool; the configured tier
additionally decides which of these tools are registered at all.

Tool schemas are built on ``probatio``, not ``voluptuous``. Home Assistant
declares ``llm.Tool.parameters`` as ``probatio.Schema``, and probatio replaced
voluptuous as the validation engine in Core 2026.10. Importing voluptuous would
still work at runtime, because HA aliases it to probatio in ``sys.modules``, but
it would describe the wrong type. HA's own tool integrations import probatio
directly. Service schemas elsewhere in this integration stay on voluptuous.
"""

from __future__ import annotations

import logging
from typing import Any, Final, cast, override

import probatio
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_CLEAR_CLIENT_ALIAS,
    SERVICE_CREATE_ENDPOINT,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_CLIENT,
    SERVICE_DELETE_ENDPOINT,
    SERVICE_DELETE_RULE,
    SERVICE_DELETE_SERVICE,
    SERVICE_DISABLE_PROFILE,
    SERVICE_ENABLE_PROFILE,
    SERVICE_FIELD_ALIAS,
    SERVICE_FIELD_CANCEL_EXPIRATION,
    SERVICE_FIELD_CLEAR_PROFILE2,
    SERVICE_FIELD_CLIENT_ID,
    SERVICE_FIELD_COMMENT,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_DELETE_HISTORY,
    SERVICE_FIELD_DESCRIPTION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_ENDPOINT_HOSTNAME,
    SERVICE_FIELD_ENDPOINT_ID,
    SERVICE_FIELD_ENDPOINT_MAC,
    SERVICE_FIELD_ENDPOINT_NAME,
    SERVICE_FIELD_EXPIRATION_DURATION,
    SERVICE_FIELD_EXPIRE_AT,
    SERVICE_FIELD_FILTER_ID,
    SERVICE_FIELD_FILTER_NAME,
    SERVICE_FIELD_HOSTNAME,
    SERVICE_FIELD_ICON,
    SERVICE_FIELD_MINUTES,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_OPTION_ID,
    SERVICE_FIELD_OPTION_NAME,
    SERVICE_FIELD_PARENT_ENDPOINT_NAME,
    SERVICE_FIELD_PROFILE2_ID,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_FIELD_PROFILE_NAME,
    SERVICE_FIELD_REDIRECT_TARGET,
    SERVICE_FIELD_REDIRECT_TARGET_TYPE,
    SERVICE_FIELD_RULE_GROUP_ID,
    SERVICE_FIELD_RULE_GROUP_NAME,
    SERVICE_FIELD_RULE_IDENTITY,
    SERVICE_FIELD_SERVICE_ID,
    SERVICE_FIELD_SERVICE_NAME,
    SERVICE_FIELD_VALUE,
    SERVICE_RENAME_ENDPOINT,
    SERVICE_SET_CLIENT_ALIAS,
    SERVICE_SET_DEFAULT_RULE_STATE,
    SERVICE_SET_ENDPOINT_ANALYTICS_LOGGING,
    SERVICE_SET_ENDPOINT_DESCRIPTION,
    SERVICE_SET_ENDPOINT_PROFILE,
    SERVICE_SET_FILTER_STATE,
    SERVICE_SET_OPTION_STATE,
    SERVICE_SET_RULE_STATE,
    SERVICE_SET_SERVICE_STATE,
)
from .llm_tools_common import as_list, format_tool_name
from .models import (
    DEFAULT_RULE_MODE_LABELS,
    SERVICE_MODE_LABELS,
    ControlDRule,
    default_rule_mode_labels,
    endpoint_analytics_logging_mode_labels,
    normalize_default_rule_mode,
    normalize_service_mode,
    rule_action_options,
    service_mode_labels,
)
from .utils.action_result import (
    ACTION_STATUS_ALREADY_IN_STATE,
    ACTION_STATUS_APPLIED,
    ACTION_STATUS_FAILED,
    build_action_result,
)

LOGGER = logging.getLogger(__name__)

_CONTROL_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=True,
    open_world=False,
)

_DESTRUCTIVE_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=True,
    idempotent=True,
    open_world=False,
)

# A repeat of a non-idempotent action has an effect, so it must not claim
# idempotency. `create_rule` is the only such tool: creating the same rule twice
# creates two rules.
_NON_IDEMPOTENT_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=False,
    open_world=False,
)

_PROFILE_ID_DESCRIPTION: Final = (
    "Optional. A Control D profile id (from get_account_overview). Provide this "
    "or profile_name; ids take precedence when both are given. Omit both to act "
    "on every managed profile, which is rarely what you want."
)

_PROFILE_NAME_DESCRIPTION: Final = (
    "Optional. A Control D profile name (from get_account_overview). Provide "
    "this or profile_id."
)

_REDIRECT_TARGET_DESCRIPTION: Final = (
    "Optional. Only for a redirect mode. The redirect destination: a region "
    "code such as 'JFK' for a location redirect, or an IP address for an IP "
    "redirect. Required when the mode is a redirect."
)

_REDIRECT_TARGET_TYPE_DESCRIPTION: Final = (
    "Optional. Only for a redirect mode. 'location' (a region code) or 'ip' (an "
    "IP address). Required alongside redirect_target."
)

_EXPIRATION_DESCRIPTION: Final = (
    "Optional. Set an expiry so the change reverts on its own. Use this rather "
    "than a permanent change when the intent is temporary, for example '2h' or "
    "'1d'."
)

_COMMENT_DESCRIPTION: Final = "Optional. A comment to record on the rule."


def _resolve_profile_pks(registry: Any, args: dict[str, Any]) -> tuple[str, ...]:
    """Return the profile ids a tool call addresses.

    Ids win over names. With neither, the call covers every profile, which is
    also how the services behave.
    """
    profile_ids = as_list(args.get(SERVICE_FIELD_PROFILE_ID))
    if profile_ids:
        return tuple(pk for pk in profile_ids if pk in registry.profiles)
    profile_names = as_list(args.get(SERVICE_FIELD_PROFILE_NAME))
    if profile_names:
        wanted = {name.casefold() for name in profile_names}
        return tuple(
            pk
            for pk, profile in registry.profiles.items()
            if profile.name.casefold() in wanted
        )
    return tuple(registry.profiles)


def _match_client_targets(
    registry: Any | None, args: dict[str, Any]
) -> tuple[Any, ...]:
    """Return the client alias targets a call addresses.

    A `client_id` is tried first because it is the identifier the alias API keys
    on and the only selector that is guaranteed to match a single client. A MAC
    is accepted as a convenience but commonly matches several clients under one
    endpoint that share a MAC and IP but differ by `client_id`.
    """
    if registry is None:
        return ()
    client_ids = set(as_list(args.get(SERVICE_FIELD_CLIENT_ID)))
    if client_ids:
        return tuple(
            target
            for target in registry.client_alias_targets.values()
            if target.client_id in client_ids
        )
    macs = {mac.casefold() for mac in as_list(args.get(SERVICE_FIELD_ENDPOINT_MAC))}
    if macs:
        return tuple(
            target
            for target in registry.client_alias_targets.values()
            if (target.client_mac_address or "").casefold() in macs
        )
    hostnames = {
        host.casefold() for host in as_list(args.get(SERVICE_FIELD_ENDPOINT_HOSTNAME))
    }
    if hostnames:
        return tuple(
            target
            for target in registry.client_alias_targets.values()
            if (target.client_hostname or "").casefold() in hostnames
        )
    return ()


def _client_target(args: dict[str, Any]) -> dict[str, Any]:
    """Return a reportable client target built from the caller's own input."""
    if client_ids := args.get(SERVICE_FIELD_CLIENT_ID):
        return {"kind": "client", "client_id": client_ids}
    if macs := args.get(SERVICE_FIELD_ENDPOINT_MAC):
        return {"kind": "client", "mac": macs}
    return {"kind": "client", "hostname": args.get(SERVICE_FIELD_ENDPOINT_HOSTNAME)}


def _client_selector_args(target: Any) -> str:
    """Return the selector arguments that address one resolved client target.

    The client id is emitted rather than the MAC, because a MAC may match more
    than one client and would make the call ambiguous.
    """
    if getattr(target, "client_id", None):
        return f"client_id={target.client_id!r}"
    return f"endpoint_mac={target.client_mac_address!r}"


def _client_selector_args_from_args(args: dict[str, Any]) -> str | None:
    """Return a selector reproducing the caller's own target, if there is one.

    Used when the registry holds no matching client, so the undo can still name
    the same target the caller addressed instead of guessing at one.
    """
    if client_ids := as_list(args.get(SERVICE_FIELD_CLIENT_ID)):
        return f"client_id={client_ids[0]!r}"
    if macs := as_list(args.get(SERVICE_FIELD_ENDPOINT_MAC)):
        return f"endpoint_mac={macs[0]!r}"
    if hostnames := as_list(args.get(SERVICE_FIELD_ENDPOINT_HOSTNAME)):
        return f"endpoint_hostname={hostnames[0]!r}"
    return None


def _resolve_row_pks(
    rows_by_profile: dict[str, dict[str, Any]],
    profile_pks: tuple[str, ...],
    *,
    id_field: str,
    name_field: str,
    args: dict[str, Any],
    name_attr: str,
) -> tuple[tuple[str, str], ...]:
    """Return the (profile_pk, row_pk) pairs a call addresses.

    Rows are matched by id when given, otherwise by their display name.
    """
    row_ids = as_list(args.get(id_field))
    row_names = as_list(args.get(name_field))
    wanted_names = {name.casefold() for name in row_names}
    pairs: list[tuple[str, str]] = []
    for profile_pk in profile_pks:
        for row_pk, row in rows_by_profile.get(profile_pk, {}).items():
            if (row_ids and row_pk in row_ids) or (
                wanted_names and getattr(row, name_attr, "").casefold() in wanted_names
            ):
                pairs.append((profile_pk, row_pk))
    return tuple(pairs)


class _ControlDControlTool(llm.Tool):
    """Base class for a Control D control tool backed by a service.

    Pylint reads this class in isolation, so it cannot see two things that are
    true by construction. The hooks below are a template method: each declares
    the full signature every subclass overrides, and most subclasses use only
    part of it. And the dispatch reads `before` and `undo` from those hooks,
    whose base implementations return ``None`` while subclasses return state.
    """

    # pylint: disable=unused-argument,assignment-from-none

    integration = DOMAIN
    annotations = _CONTROL_ANNOTATIONS

    _service: str

    # Whether a pre-write state can be read at all. `create_rule` cannot: it is
    # additive, so there is no previous state to compare against.
    _has_precheck: bool = True

    _UNREADABLE_STATE_WARNING: Final = (
        "The previous state could not be read, so `changed` reports that the "
        "action was sent, not that the value differs. `undo` is not available "
        "for the same reason."
    )

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    def _args(self, tool_input: llm.ToolInput) -> dict[str, Any]:
        """Return tool args validated against the declared schema."""
        return cast(dict[str, Any], self.parameters(tool_input.tool_args))

    def _registry(self, hass: HomeAssistant) -> Any | None:
        """Return the read-only runtime registry for this tool's entry.

        Writes still go through services; this read-only view exists so a tool
        can compare the requested state against the current one and report
        ``already_in_state`` honestly instead of claiming a change that did not
        happen.
        """
        entry = hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return None
        runtime = getattr(entry, "runtime_data", None)
        return getattr(runtime, "registry", None)

    def _translate_profile_ids(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Map Control D profile PKs onto the device ids these services target.

        The profile services declare ``profile_id`` with a Home Assistant device
        selector, but every read surface hands the caller a Control D profile PK.
        The PK is translated here so the model is given one identifier to work
        with instead of having to learn a second, unpublished one.

        Only the service call is translated: the pre-write reads above resolve
        against the registry, which is keyed by the PK.
        """
        raw_profile_ids = args.get(SERVICE_FIELD_PROFILE_ID)
        if raw_profile_ids is None:
            return args
        entry = hass.config_entries.async_get_entry(self._entry_id)
        runtime = getattr(entry, "runtime_data", None)
        device_manager = getattr(getattr(runtime, "managers", None), "device", None)
        if device_manager is None:
            return args
        mapping = device_manager.profile_device_ids
        # The caller's shape is preserved. A profile-scoped service accepts a
        # list, but `create_endpoint` takes exactly one profile as a string, so
        # wrapping a scalar in a list would fail its schema.
        translated: Any = (
            [mapping.get(profile_pk, profile_pk) for profile_pk in raw_profile_ids]
            if isinstance(raw_profile_ids, list)
            else mapping.get(raw_profile_ids, raw_profile_ids)
        )
        return {**args, SERVICE_FIELD_PROFILE_ID: translated}

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the resolved target to report, from the caller's own input."""
        return {key: value for key, value in args.items() if value is not None}

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the state observed before the action, when it can be read."""
        return None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether the target is already in the requested state."""
        return False

    def _after(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Return the state the action requests."""
        return None

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return the calls that reverse the action, or None when none can.

        Read the pre-write state here rather than from ``args``: reversing a
        change means restoring the previous value, which only the runtime
        registry knows. Each addressed target needs its own call, so this
        returns a list.
        """
        return None

    async def _async_preload(self, hass: HomeAssistant, args: dict[str, Any]) -> None:
        """Load anything the pre-write hooks need that the registry cannot supply.

        The hooks above are synchronous because most targets are fully described
        by the runtime registry. A target the registry does not hold has to be
        fetched, and fetching is asynchronous, so a tool overrides this to
        populate state the hooks can then read synchronously.

        Called once per ``async_call``, before ``_before``.
        """
        return None

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the backing service and return the action result."""
        args = self._args(tool_input)
        try:
            await self._async_preload(hass, args)
            return await self._async_dispatch(hass, args, llm_context)
        finally:
            # Preloaded state is per-call, so it never outlives the call that
            # needed it.
            self._clear_preload()

    def _clear_preload(self) -> None:
        """Drop any state loaded by ``_async_preload``."""
        return None

    async def _async_dispatch(
        self,
        hass: HomeAssistant,
        args: dict[str, Any],
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Run the pre-check, the write, and the action-result assembly."""
        target = self._target(args)
        before = self._before(hass, args)

        if self._is_already_in_state(hass, args):
            # Nothing changed, so there is nothing to reverse.
            return llm.ToolResult(
                data=build_action_result(
                    status=ACTION_STATUS_ALREADY_IN_STATE,
                    target=target,
                    changed=False,
                    before=before,
                    after=before,
                )
            )

        # Resolved before the write, while the registry still holds the
        # pre-write state the undo has to restore.
        undo = self._undo(hass, args)

        service_data = {
            **self._translate_profile_ids(hass, args),
            SERVICE_FIELD_CONFIG_ENTRY_ID: self._entry_id,
        }
        try:
            await hass.services.async_call(
                DOMAIN,
                self._service,
                service_data,
                blocking=True,
                context=llm_context.context,
            )
        except HomeAssistantError as err:
            return llm.ToolResult(
                data=build_action_result(
                    status=ACTION_STATUS_FAILED,
                    target=target,
                    changed=False,
                    before=before,
                    # The reason is the only thing that distinguishes a missing
                    # target from a rejected value, so it must not be dropped.
                    error=str(err) or type(err).__name__,
                ),
                error=True,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            # An unexpected error must still leave the model with a coherent
            # action result. Letting it escape handed back a bare repr such as
            # `'group:1|example.com'` (a KeyError), which reads like data. The
            # error is logged so the underlying defect is still discoverable.
            # The broad catch is the point: the tool layer is the boundary, so
            # anything a service raises has to become an action result here.
            LOGGER.exception(
                "Control D tool %s failed unexpectedly for %s", self._service, target
            )
            return llm.ToolResult(
                data=build_action_result(
                    status=ACTION_STATUS_FAILED,
                    target=target,
                    changed=False,
                    before=before,
                    error=f"{type(err).__name__}: {err}",
                ),
                error=True,
            )

        return llm.ToolResult(
            data=build_action_result(
                status=ACTION_STATUS_APPLIED,
                target=target,
                changed=True,
                before=before,
                after=self._after(args),
                undo=undo,
                warnings=self._warnings(before, undo),
            )
        )

    def _warnings(
        self, before: dict[str, Any] | None, undo: list[str] | None
    ) -> list[str]:
        """Return warnings about what this action could and could not report.

        A tool that could not read the pre-write state cannot honestly claim the
        value changed, nor name the call that reverses it. Reporting the action
        as applied is still correct, so the caveat is carried as a warning rather
        than as a failure.
        """
        if self._has_precheck and before is None and undo is None:
            return [self._UNREADABLE_STATE_WARNING]
        return []


class SetFilterStateTool(_ControlDControlTool):
    """Enable or disable a blocklist filter on a profile."""

    name = format_tool_name("set_filter_state")
    title = "Set filter state"
    description = (
        "Turn a blocklist filter on or off on one or more profiles. Use it to "
        "stop a category from being blocked, or to start blocking one that is "
        "currently off.\n"
        "\n"
        "Resolve the filter first with get_catalog (catalog_type 'filters'), "
        "which returns each filter's id, name, and current enabled state. Pass "
        "either the id or the name; ids take precedence.\n"
        "\n"
        "Filters come in two kinds. Native filters are Control D's own "
        "categories; third-party filters are community blocklists such as "
        "Hagezi. Both work here.\n"
        "\n"
        "This is reversible — call it again with the opposite value, or use the "
        "`undo` field it returns. Changing a filter affects every device attached "
        "to that profile, so name the profile explicitly rather than relying on "
        "the default."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_FILTER_ID,
                description=(
                    "Optional. A filter id or list of ids (from get_catalog). "
                    "Provide this or filter_name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_FILTER_NAME,
                description=(
                    "Optional. A filter name or list of names (from get_catalog). "
                    "Provide this or filter_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_ENABLED,
                description="Required. True to enable the filter, false to disable it.",
            ): bool,
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_FILTER_STATE

    def _pairs(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        """Return the (profile, filter) rows this call addresses."""
        registry = self._registry(hass)
        if registry is None:
            return ()
        return _resolve_row_pks(
            registry.filters_by_profile,
            _resolve_profile_pks(registry, args),
            id_field=SERVICE_FIELD_FILTER_ID,
            name_field=SERVICE_FIELD_FILTER_NAME,
            args=args,
            name_attr="name",
        )

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current enabled state of the addressed filters."""
        registry = self._registry(hass)
        if registry is None:
            return None
        states = [
            registry.filters_by_profile[profile_pk][filter_pk].enabled
            for profile_pk, filter_pk in self._pairs(hass, args)
        ]
        return {"enabled": states} if states else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed filter is already as requested."""
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return False
        wanted = bool(args[SERVICE_FIELD_ENABLED])
        return all(
            registry.filters_by_profile[profile_pk][filter_pk].enabled == wanted
            for profile_pk, filter_pk in pairs
        )

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested enabled state."""
        return {"enabled": args[SERVICE_FIELD_ENABLED]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per filter, restoring its previous state."""
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return None
        return [
            f"{format_tool_name('set_filter_state')}(filter_id={filter_pk!r}, "
            f"profile_id={profile_pk!r}, "
            f"enabled={registry.filters_by_profile[profile_pk][filter_pk].enabled})"
            for profile_pk, filter_pk in pairs
        ]


class SetServiceStateTool(_ControlDControlTool):
    """Set the action mode for a service on a profile."""

    name = format_tool_name("set_service_state")
    title = "Set service state"
    description = (
        "Set how one or more services are handled on a profile: blocked, "
        "bypassed, or redirected. Use it to allow something that is currently "
        "blocked, block something that is allowed, or point a service somewhere "
        "else.\n"
        "\n"
        "Resolve the service first with get_catalog (catalog_type 'services'). "
        "Pass either the id or the name; ids take precedence. A service not "
        "currently listed on the profile can still be set, which adds it.\n"
        "\n"
        "A redirect mode needs a destination: 'location' with a region code such "
        "as 'JFK', or 'ip' with an address. Leaving a service in a redirect mode "
        "without a target is rejected.\n"
        "\n"
        "This is reversible — set the mode back, or use the `undo` field. Every "
        "device on that profile is affected."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_SERVICE_ID,
                description=(
                    "Optional. A service id or list of ids (from get_catalog). "
                    "Provide this or service_name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_SERVICE_NAME,
                description=(
                    "Optional. A service name or list of names (from "
                    "get_catalog). Provide this or service_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. How to handle the service: 'Off', 'Blocked', "
                    "'Bypassed', or 'Redirected'. The values are "
                    "case-sensitive."
                ),
            ): probatio.In(service_mode_labels()),
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): probatio.In(("location", "ip")),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_SERVICE_STATE

    def _pairs(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        """Return the (profile, service) rows this call addresses."""
        registry = self._registry(hass)
        if registry is None:
            return ()
        return _resolve_row_pks(
            registry.services_by_profile,
            _resolve_profile_pks(registry, args),
            id_field=SERVICE_FIELD_SERVICE_ID,
            name_field=SERVICE_FIELD_SERVICE_NAME,
            args=args,
            name_attr="name",
        )

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current service modes as display labels.

        Labels rather than the internal mode keys, so ``before`` and ``after``
        speak the same vocabulary and a caller comparing them is not misled by
        "blocked" versus "Blocked".
        """
        registry = self._registry(hass)
        if registry is None:
            return None
        modes = [
            SERVICE_MODE_LABELS.get(
                registry.services_by_profile[profile_pk][service_pk].current_mode
            )
            for profile_pk, service_pk in self._pairs(hass, args)
        ]
        modes = [mode for mode in modes if mode is not None]
        return {"mode": modes} if modes else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed service is already in the requested mode.

        The schema accepts display labels, while ``current_mode`` is an internal
        key, so the requested value is normalized before comparing.
        """
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return False
        wanted = normalize_service_mode(args[SERVICE_FIELD_MODE])
        return all(
            registry.services_by_profile[profile_pk][service_pk].current_mode == wanted
            for profile_pk, service_pk in pairs
        )

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested mode."""
        return {"mode": args[SERVICE_FIELD_MODE]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per service, restoring its previous mode."""
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return None
        calls: list[str] = []
        for profile_pk, service_pk in pairs:
            # The schema takes display labels, so the key read from the registry
            # is translated back before being emitted in a call.
            label = SERVICE_MODE_LABELS.get(
                registry.services_by_profile[profile_pk][service_pk].current_mode
            )
            if label is None:
                continue
            calls.append(
                f"{format_tool_name('set_service_state')}("
                f"service_id={service_pk!r}, profile_id={profile_pk!r}, "
                f"mode={label!r})"
            )
        return calls or None


class DeleteServiceTool(_ControlDControlTool):
    """Remove a configured service from a profile."""

    name = format_tool_name("delete_service")
    title = "Delete service"
    description = (
        "Remove one or more configured services from a profile entirely, so the "
        "profile no longer carries a row for them.\n"
        "\n"
        "This is **not** the same as setting a service to `'Off'`. `Off` leaves "
        "the service on the profile switched off, and it can be switched back on "
        "at any time. Deleting removes the row, and re-adding it means "
        "configuring the service again.\n"
        "\n"
        "Prefer `set_service_state` with `'Off'` when you only want to stop a "
        "service applying — that is almost always the intent, and it preserves "
        "the configuration. Delete only when the service should not remain "
        "configured on the profile at all.\n"
        "\n"
        "This is reversible: the `undo` field names the call that configures the "
        "service again with the mode it had. It is not a destructive tool, "
        "because the service can be re-added."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_SERVICE_ID,
                description=(
                    "Optional. A service id or list of ids (from get_catalog, "
                    "catalog_type 'services'). Provide this or service_name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_SERVICE_NAME,
                description=(
                    "Optional. A service name or list of names (from "
                    "get_catalog). Provide this or service_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_DELETE_SERVICE

    def _pairs(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        """Return the (profile, service) rows this call addresses."""
        registry = self._registry(hass)
        if registry is None:
            return ()
        return _resolve_row_pks(
            registry.services_by_profile,
            _resolve_profile_pks(registry, args),
            id_field=SERVICE_FIELD_SERVICE_ID,
            name_field=SERVICE_FIELD_SERVICE_NAME,
            args=args,
            name_attr="name",
        )

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the modes the addressed services currently hold."""
        registry = self._registry(hass)
        if registry is None:
            return None
        modes = [
            SERVICE_MODE_LABELS.get(
                registry.services_by_profile[profile_pk][service_pk].current_mode
            )
            for profile_pk, service_pk in self._pairs(hass, args)
        ]
        modes = [mode for mode in modes if mode is not None]
        return {"mode": modes} if modes else None

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the removed state."""
        del args
        return {"configured": False}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per service, configuring it again as it was.

        Deletion is reversible by configuring the service again, so this is not a
        destructive tool even though the row is removed.
        """
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return None
        calls: list[str] = []
        for profile_pk, service_pk in pairs:
            label = SERVICE_MODE_LABELS.get(
                registry.services_by_profile[profile_pk][service_pk].current_mode
            )
            calls.append(
                f"{format_tool_name('set_service_state')}("
                f"service_id={service_pk!r}, profile_id={profile_pk!r}, "
                f"mode={label or 'Blocked'!r})"
            )
        return calls or None


class SetOptionStateTool(_ControlDControlTool):
    """Enable, disable, or set the value of a profile option."""

    name = format_tool_name("set_option_state")
    title = "Set option state"
    description = (
        "Change a Control D profile option. Options are the profile-level "
        "protections such as AI Malware, Safe Search, Restricted YouTube, DNSSEC, "
        "and rebind protection.\n"
        "\n"
        "Resolve the option first with get_catalog (catalog_type "
        "'profile_options'), which returns each option's id, type, and current "
        "value. Toggle options use `enabled`; dropdown options use `value`.\n"
        "\n"
        "This is reversible — set the previous value back, or use the `undo` "
        "field. Options apply to every device on the profile."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_OPTION_ID,
                description=(
                    "Optional. An option id or list of ids (from get_catalog). "
                    "Provide this or option_name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_OPTION_NAME,
                description=(
                    "Optional. An option name or list of names (from "
                    "get_catalog). Provide this or option_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENABLED,
                description=(
                    "Optional. For a toggle option: true to enable it, false to "
                    "disable it."
                ),
            ): bool,
            probatio.Optional(
                SERVICE_FIELD_VALUE,
                description=(
                    "Optional. For a dropdown option: the value to set, using "
                    "the choices reported by get_catalog."
                ),
            ): probatio.Any(str, int),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_OPTION_STATE

    def _pairs(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        """Return the (profile, option) rows this call addresses."""
        registry = self._registry(hass)
        if registry is None:
            return ()
        return _resolve_row_pks(
            registry.options_by_profile,
            _resolve_profile_pks(registry, args),
            id_field=SERVICE_FIELD_OPTION_ID,
            name_field=SERVICE_FIELD_OPTION_NAME,
            args=args,
            name_attr="title",
        )

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current option states, shaped by option kind.

        Reported per kind rather than as a single select-style label:
        ``current_select_option`` returns "Off" for any option whose value has no
        matching choice, which is every enabled toggle, so an enabled toggle
        would otherwise be reported as off.
        """
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return None
        enabled: list[bool] = []
        values: list[str] = []
        for profile_pk, option_pk in pairs:
            option = registry.options_by_profile[profile_pk][option_pk]
            if option.entity_kind == "toggle":
                enabled.append(option.is_enabled)
            elif option.entity_kind == "select":
                values.append(option.current_select_option)
        if enabled and values:
            return {"enabled": enabled, "value": values}
        if enabled:
            return {"enabled": enabled}
        return {"value": values} if values else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed option is already as requested."""
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return False
        wants_enabled = args.get(SERVICE_FIELD_ENABLED)
        wants_value = args.get(SERVICE_FIELD_VALUE)
        for profile_pk, option_pk in pairs:
            option = registry.options_by_profile[profile_pk][option_pk]
            if wants_enabled is not None and bool(wants_enabled) != option.is_enabled:
                return False
            if wants_value is not None and str(wants_value) != str(
                option.current_value_key
            ):
                return False
        return True

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return whichever of the enabled/value pair was requested."""
        after: dict[str, Any] = {}
        if SERVICE_FIELD_ENABLED in args:
            after["enabled"] = args[SERVICE_FIELD_ENABLED]
        if SERVICE_FIELD_VALUE in args:
            after["value"] = args[SERVICE_FIELD_VALUE]
        return after

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per option, restoring its previous value."""
        registry = self._registry(hass)
        pairs = self._pairs(hass, args)
        if registry is None or not pairs:
            return None
        calls: list[str] = []
        for profile_pk, option_pk in pairs:
            option = registry.options_by_profile[profile_pk][option_pk]
            if option.entity_kind == "toggle":
                undo_args = f"enabled={option.is_enabled}"
            elif option.entity_kind == "select" and option.current_value_key:
                undo_args = f"value={option.current_value_key!r}"
            else:
                continue
            calls.append(
                f"{format_tool_name('set_option_state')}("
                f"option_id={option_pk!r}, profile_id={profile_pk!r}, {undo_args})"
            )
        return calls or None


class SetRuleStateTool(_ControlDControlTool):
    """Enable, disable, or modify one custom rule."""

    # Rows fetched for a rule the registry does not expose, held for one call.
    _preloaded_rules: dict[str, dict[str, ControlDRule]] | None = None

    name = format_tool_name("set_rule_state")
    title = "Set rule state"
    description = (
        "Enable, disable, or modify one of your own custom rules. Use it to "
        "temporarily stop a rule from applying, or to change what it does.\n"
        "\n"
        "Resolve the rule first with get_catalog (catalog_type 'rules'), which "
        "returns each rule's `rule_identity` along with its domain, action, and "
        "current state. Pass that identity — not the raw domain.\n"
        "\n"
        "This is reversible, and a disabled rule is usually better than a "
        "deleted one: the rule keeps its place and can be switched back on. Use "
        "`expiration_duration` or `expire_at` for a change that should revert on "
        "its own, and `cancel_expiration` to clear an existing expiry. The "
        "`undo` field returns the call that reverses the change."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_RULE_IDENTITY,
                description=(
                    "Required. The rule identity or list of identities (from "
                    "get_catalog, catalog_type 'rules')."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENABLED,
                description="Optional. True to enable the rule, false to disable it.",
            ): bool,
            probatio.Optional(
                SERVICE_FIELD_MODE,
                description=(
                    "Optional. Change what the rule does: 'block', 'bypass', "
                    "or 'redirect'. The values are case-sensitive and are not "
                    "the same words the filter and service tools use."
                ),
            ): probatio.In(rule_action_options()),
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): probatio.In(("location", "ip")),
            probatio.Optional(
                SERVICE_FIELD_COMMENT, description=_COMMENT_DESCRIPTION
            ): str,
            probatio.Optional(
                SERVICE_FIELD_EXPIRATION_DURATION,
                description=_EXPIRATION_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_EXPIRE_AT,
                description=(
                    "Optional. An absolute expiry as an ISO 8601 timestamp. Use "
                    "instead of expiration_duration when the moment is known."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_CANCEL_EXPIRATION,
                description=(
                    "Optional. True to clear an existing expiry, making the "
                    "change permanent."
                ),
            ): bool,
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_RULE_STATE

    def _matching_rules(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[Any, ...]:
        """Return the rule rows this call addresses, by identity.

        Prefers rows preloaded from the API: the registry only holds rules a
        profile exposes, so without them the pre-check, the no-op check, and the
        undo would all be blind for an unexposed rule.
        """
        registry = self._registry(hass)
        if registry is None:
            return ()
        identities = set(as_list(args[SERVICE_FIELD_RULE_IDENTITY]))
        rows_by_profile = self._preloaded_rules or {}
        found: list[Any] = []
        for profile_pk in _resolve_profile_pks(registry, args):
            source = rows_by_profile.get(profile_pk) or registry.rules_by_profile.get(
                profile_pk, {}
            )
            found.extend(
                rule for rule in source.values() if rule.identity in identities
            )
        return tuple(found)

    async def _async_preload(self, hass: HomeAssistant, args: dict[str, Any]) -> None:
        """Fetch rules the registry does not hold.

        Only runs when the registry cannot answer, so the common case of an
        exposed rule costs no extra request.
        """
        registry = self._registry(hass)
        if registry is None:
            return
        identities = set(as_list(args[SERVICE_FIELD_RULE_IDENTITY]))
        if not identities:
            return
        profiles = _resolve_profile_pks(registry, args)
        if all(
            any(
                rule.identity in identities
                for rule in registry.rules_by_profile.get(profile_pk, {}).values()
            )
            for profile_pk in profiles
        ):
            return
        entry = hass.config_entries.async_get_entry(self._entry_id)
        manager = getattr(
            getattr(getattr(entry, "runtime_data", None), "managers", None),
            "integration",
            None,
        )
        if manager is None:
            return
        loaded = await manager.async_load_live_rules(frozenset(profiles))
        self._preloaded_rules = {
            profile_pk: rows[1] for profile_pk, rows in loaded.items()
        }

    def _clear_preload(self) -> None:
        """Drop the preloaded rows once the call is done."""
        self._preloaded_rules = None

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current rule states, including any redirect destination."""
        rules = self._matching_rules(hass, args)
        if not rules:
            return None
        targets = [rule.redirect_target for rule in rules]
        before: dict[str, Any] = {
            "enabled": [rule.enabled for rule in rules],
            "action": [rule.action_key for rule in rules],
        }
        # A redirect whose destination is not reported is only half-described.
        if any(target is not None for target in targets):
            before["redirect_target"] = targets
        return before

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether the addressed rules already match the request."""
        rules = self._matching_rules(hass, args)
        if not rules:
            return False
        wants_enabled = args.get(SERVICE_FIELD_ENABLED)
        wants_mode = args.get(SERVICE_FIELD_MODE)
        wants_target = args.get(SERVICE_FIELD_REDIRECT_TARGET)
        for rule in rules:
            if wants_enabled is not None and bool(wants_enabled) != rule.enabled:
                return False
            if wants_mode is not None and rule.action_key != wants_mode:
                return False
            if wants_target is not None and rule.redirect_target != wants_target:
                return False
        return True

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per rule, restoring its previous state and destination."""
        rules = self._matching_rules(hass, args)
        if not rules:
            return None
        calls: list[str] = []
        for rule in rules:
            parts = [
                f"rule_identity={rule.identity!r}",
                f"enabled={rule.enabled}",
            ]
            if rule.redirect_target is not None:
                # The destination must be restated, otherwise the rule is left
                # redirecting with no target, which Control D rejects.
                parts.append("mode='redirect'")
                parts.append(f"redirect_target={rule.redirect_target!r}")
                if rule.redirect_write_type is not None:
                    parts.append(f"redirect_target_type={rule.redirect_write_type!r}")
            else:
                parts.append(f"mode={rule.action_key!r}")
            if rule.ttl is not None:
                parts.append(f"expire_at={rule.ttl}")
            calls.append(f"{format_tool_name('set_rule_state')}({', '.join(parts)})")
        return calls or None

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested rule state."""
        after: dict[str, Any] = {}
        for key in (
            SERVICE_FIELD_ENABLED,
            SERVICE_FIELD_MODE,
            SERVICE_FIELD_COMMENT,
            SERVICE_FIELD_EXPIRE_AT,
            SERVICE_FIELD_EXPIRATION_DURATION,
            SERVICE_FIELD_REDIRECT_TARGET,
            SERVICE_FIELD_REDIRECT_TARGET_TYPE,
        ):
            if key in args:
                after[key] = args[key]
        return after


class SetDefaultRuleStateTool(_ControlDControlTool):
    """Set what a profile does when nothing else matches."""

    name = format_tool_name("set_default_rule_state")
    title = "Set default rule state"
    description = (
        "Set the catch-all action for a profile — what happens to a domain that "
        "no custom rule, service, or filter matches. This is a profile-wide "
        "policy change with the widest possible reach.\n"
        "\n"
        "Read the current value with get_catalog (catalog_type 'default_rule'). "
        "Setting it to bypass makes the profile permissive, which effectively "
        "turns off blocking for anything not explicitly ruled on; setting it to "
        "blocking makes it strict. Treat a change as significant and confirm the "
        "intent before making it.\n"
        "\n"
        "This is reversible — set the previous mode back, or use the `undo` field."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. The catch-all action: 'Blocking', 'Bypassing', "
                    "or 'Redirecting'. The values are case-sensitive."
                ),
            ): probatio.In(default_rule_mode_labels()),
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): probatio.In(("location", "ip")),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_DEFAULT_RULE_STATE

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current default modes as display labels.

        Labels rather than internal keys, so ``before`` and ``after`` match; see
        the equivalent note on the service tool.
        """
        registry = self._registry(hass)
        if registry is None:
            return None
        modes = [
            DEFAULT_RULE_MODE_LABELS.get(
                registry.default_rules_by_profile[pk].current_mode
            )
            for pk in _resolve_profile_pks(registry, args)
            if pk in registry.default_rules_by_profile
        ]
        modes = [mode for mode in modes if mode is not None]
        return {"mode": modes} if modes else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed profile already uses the requested mode.

        The schema accepts display labels, while ``current_mode`` is an internal
        key, so the requested value is normalized before comparing.
        """
        registry = self._registry(hass)
        if registry is None:
            return False
        wanted = normalize_default_rule_mode(args[SERVICE_FIELD_MODE])
        modes = [
            registry.default_rules_by_profile[pk].current_mode
            for pk in _resolve_profile_pks(registry, args)
            if pk in registry.default_rules_by_profile
        ]
        return bool(modes) and all(mode == wanted for mode in modes)

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested default mode."""
        return {"mode": args[SERVICE_FIELD_MODE]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per profile, restoring its previous mode."""
        registry = self._registry(hass)
        if registry is None:
            return None
        calls: list[str] = []
        for profile_pk in _resolve_profile_pks(registry, args):
            rule_row = registry.default_rules_by_profile.get(profile_pk)
            if rule_row is None:
                continue
            label = DEFAULT_RULE_MODE_LABELS.get(rule_row.current_mode)
            if label is None:
                continue
            calls.append(
                f"{format_tool_name('set_default_rule_state')}("
                f"mode={label!r}, profile_id={profile_pk!r})"
            )
        return calls or None


class EnableProfileTool(_ControlDControlTool):
    """Re-enable one or more previously disabled profiles."""

    name = format_tool_name("enable_profile")
    title = "Enable profile"
    description = (
        "Re-enable one or more Control D profiles that were previously disabled, "
        "immediately. This is the counterpart to `disable_profile`.\n"
        "\n"
        "Disabling is Control D's own pause: while a profile is disabled, its "
        "filters, services, and rules stop applying, so enabling it restores the "
        "full policy. Find the profile id with get_account_overview, which also "
        "reports which profiles are paused.\n"
        "\n"
        "This is reversible with `disable_profile`; the `undo` field names the "
        "call. Enabling a profile affects every device that profile covers."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): probatio.Any(str, [str]),
        }
    )
    _service = SERVICE_ENABLE_PROFILE

    def _profile_pks(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[str, ...]:
        registry = self._registry(hass)
        return () if registry is None else _resolve_profile_pks(registry, args)

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current paused state of the addressed profiles."""
        registry = self._registry(hass)
        if registry is None:
            return None
        return {
            "paused": [
                registry.profiles[pk].paused_until is not None
                for pk in self._profile_pks(hass, args)
                if pk in registry.profiles
            ]
        }

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Enabling is a no-op when nothing is paused."""
        registry = self._registry(hass)
        pks = self._profile_pks(hass, args)
        if registry is None or not pks:
            return False
        return all(
            registry.profiles[pk].paused_until is None
            for pk in pks
            if pk in registry.profiles
        )

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested paused state."""
        return {"paused": False}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str]:
        """Return the call that pauses the profile again."""
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return [f"{format_tool_name('disable_profile')}(profile_id={profile!r})"]


class DisableProfileTool(_ControlDControlTool):
    """Temporarily disable one or more profiles."""

    name = format_tool_name("disable_profile")
    title = "Disable profile"
    description = (
        "Temporarily disable one or more Control D profiles. While a profile is "
        "disabled, its filters, services, and rules stop applying, so this is how "
        "you pause protection without unwinding any configuration. A timed "
        "disable is the safer choice: it restores itself.\n"
        "\n"
        "This is Control D's own pause feature, and it is reversible — "
        "`enable_profile` turns it back on, or the disable expires. The `undo` "
        "field names that call.\n"
        "\n"
        "The blast radius is wide: every device covered by the profile loses its "
        "protection for the duration. Confirm with the user before disabling, and "
        "prefer a short `minutes` value over a long one."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_MINUTES,
                description=(
                    "Optional. How long to disable the profile for, in minutes. "
                    "Defaults to a short window. Prefer a short value; the "
                    "profile re-enables itself when it elapses."
                ),
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=1440)),
        }
    )
    _service = SERVICE_DISABLE_PROFILE

    def _profile_pks(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[str, ...]:
        registry = self._registry(hass)
        return () if registry is None else _resolve_profile_pks(registry, args)

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current paused state of the addressed profiles."""
        registry = self._registry(hass)
        if registry is None:
            return None
        return {
            "paused": [
                registry.profiles[pk].paused_until is not None
                for pk in self._profile_pks(hass, args)
                if pk in registry.profiles
            ]
        }

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Disabling is a no-op when every addressed profile is already paused."""
        registry = self._registry(hass)
        pks = self._profile_pks(hass, args)
        if registry is None or not pks:
            return False
        return all(
            registry.profiles[pk].paused_until is not None
            for pk in pks
            if pk in registry.profiles
        )

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested paused state and duration."""
        return {"paused": True, "minutes": args.get(SERVICE_FIELD_MINUTES)}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str]:
        """Return the call that re-enables the profile."""
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return [f"{format_tool_name('enable_profile')}(profile_id={profile!r})"]


class CreateRuleTool(_ControlDControlTool):
    """Create one or more custom rules."""

    name = format_tool_name("create_rule")
    title = "Create rule"
    description = (
        "Create a custom rule for one or more domains on one or more profiles. "
        "Use it to block, bypass, or redirect specific domains.\n"
        "\n"
        "Pass the domain in `hostname` as a bare domain, for example "
        "'example.com'. By default the rule blocks it; set `mode` to 'bypassed' "
        "to make an exception instead, which is the usual way to stop a domain "
        "being blocked by a filter. Optionally place it in a folder with "
        "`rule_group_id` (from get_catalog, catalog_type 'rules').\n"
        "\n"
        "This is NOT idempotent: creating the same rule twice creates two rules. "
        "The service rejects a domain that already has a rule on the profile, but "
        "do not retry a failed call blindly.\n"
        "\n"
        "To undo it, delete the rule — the `undo` field names that call. If the "
        "configured tier does not include destructive actions, the undo is not "
        "available through these tools and you should say so rather than "
        "implying the change is easily reversible."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_HOSTNAME,
                description=(
                    "Required. The domain or list of domains to create the rule "
                    "for, as bare domains such as 'example.com'."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_MODE,
                description=(
                    "Optional. What the rule does: 'block' (the default), "
                    "'bypass' to make an exception, or 'redirect'. The values "
                    "are case-sensitive and are not the same words the filter "
                    "and service tools use."
                ),
            ): probatio.In(rule_action_options()),
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): probatio.In(("location", "ip")),
            probatio.Optional(
                SERVICE_FIELD_RULE_GROUP_ID,
                description=(
                    "Optional. The folder to create the rule in, by id (from "
                    "get_catalog, catalog_type 'rules'). Omit to use the root."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_RULE_GROUP_NAME,
                description=(
                    "Optional. The folder to create the rule in, by name. "
                    "Provide this or rule_group_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENABLED,
                description=(
                    "Optional. Defaults to true. Set false to create the rule "
                    "switched off."
                ),
            ): bool,
            probatio.Optional(
                SERVICE_FIELD_COMMENT, description=_COMMENT_DESCRIPTION
            ): str,
            probatio.Optional(
                SERVICE_FIELD_EXPIRATION_DURATION,
                description=_EXPIRATION_DESCRIPTION,
            ): str,
            probatio.Optional(
                SERVICE_FIELD_EXPIRE_AT,
                description=("Optional. An absolute expiry as an ISO 8601 timestamp."),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_CREATE_RULE
    annotations = _NON_IDEMPOTENT_ANNOTATIONS
    _has_precheck = False

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the created rule target."""
        return {"hostname": args[SERVICE_FIELD_HOSTNAME]}

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested rule state."""
        return {
            "mode": args.get(SERVICE_FIELD_MODE),
            "enabled": args.get(SERVICE_FIELD_ENABLED, True),
        }

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str]:
        """Return the delete call that removes the created rule."""
        hostname = args[SERVICE_FIELD_HOSTNAME]
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return [
            f"{format_tool_name('delete_rule')}(rule_identity={hostname!r}, "
            f"profile_id={profile!r})"
        ]


class DeleteRuleTool(_ControlDControlTool):
    """Permanently delete one or more custom rules."""

    name = format_tool_name("delete_rule")
    title = "Delete rule"
    description = (
        "PERMANENTLY DELETE one or more custom rules from a profile. This cannot "
        "be undone: re-creating a rule does not restore it, and any comment or "
        "folder placement is lost.\n"
        "\n"
        "Strongly prefer `set_rule_state` with `enabled: false`. A disabled rule "
        "stops applying and can be switched back on, which is almost always the "
        "outcome you want. Only delete when the rule should not exist at all.\n"
        "\n"
        "Resolve the rule first with get_catalog (catalog_type 'rules') and pass "
        "the `rule_identity` it reports. Deleting affects every device on the "
        "profile, and the rule is gone immediately."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_RULE_IDENTITY,
                description=(
                    "Required. The rule identity or list of identities to delete "
                    "(from get_catalog, catalog_type 'rules'). This is "
                    "permanent."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_DELETE_RULE
    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Deletion has no prior state to compare and no undo by design, so the
    # "state could not be read" note would give the wrong reason for both.
    _has_precheck = False

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the deleted rule target."""
        return {"rule_identity": args[SERVICE_FIELD_RULE_IDENTITY]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> None:
        """Deletion is irreversible, so no undo is claimed."""
        return None


class RenameEndpointTool(_ControlDControlTool):
    """Change the display name of one or more endpoints."""

    name = format_tool_name("rename_endpoint")
    title = "Rename endpoint"
    description = (
        "Change the display name of one or more Control D endpoints. This is "
        "cosmetic: it changes what the endpoint is called, not what it does.\n"
        "\n"
        "An *endpoint* is a top-level protected row — a router segment, a ctrld "
        "instance, or an individually protected device. Find it with "
        "get_inventory and pass its `device_id` as `endpoint_id`, which is "
        "unique. An id is the safer selector, because endpoint names are not "
        "guaranteed to be unique.\n"
        "\n"
        "This is reversible — rename it back. Renaming an endpoint does not "
        "change its clients; if you meant to label a single device under an "
        "endpoint, use `set_client_alias` instead."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id or list of device_ids "
                    "(from get_inventory). Ids are unique, so prefer this over a "
                    "name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_NEW_NAME,
                description=(
                    "Required. The new display name to apply to every selected "
                    "endpoint."
                ),
            ): str,
        }
    )
    _service = SERVICE_RENAME_ENDPOINT

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the renamed endpoints."""
        return {
            "kind": "endpoint",
            "id": args[SERVICE_FIELD_ENDPOINT_ID],
            "new_name": args[SERVICE_FIELD_NEW_NAME],
        }

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the current endpoint names."""
        registry = self._registry(hass)
        if registry is None:
            return None
        names = [
            registry.endpoints[device_id].name
            for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID])
            if device_id in registry.endpoints
        ]
        return {"name": names} if names else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed endpoint already carries the new name."""
        registry = self._registry(hass)
        if registry is None:
            return False
        new_name = args[SERVICE_FIELD_NEW_NAME]
        endpoints = [
            registry.endpoints[device_id]
            for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID])
            if device_id in registry.endpoints
        ]
        return bool(endpoints) and all(
            endpoint.name == new_name for endpoint in endpoints
        )

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested name."""
        return {"name": args[SERVICE_FIELD_NEW_NAME]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per endpoint, restoring its previous name."""
        registry = self._registry(hass)
        if registry is None:
            return None
        calls: list[str] = []
        for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID]):
            endpoint = registry.endpoints.get(device_id)
            if endpoint is None or not endpoint.name:
                continue
            calls.append(
                f"{format_tool_name('rename_endpoint')}("
                f"endpoint_id={device_id!r}, new_name={endpoint.name!r})"
            )
        return calls or None


class SetEndpointAnalyticsLoggingTool(_ControlDControlTool):
    """Set the analytics logging level for one or more endpoints."""

    name = format_tool_name("set_endpoint_analytics_logging")
    title = "Set endpoint analytics logging"
    description = (
        "Set how much DNS activity Control D records for one or more endpoints: "
        "None, Some, or Full.\n"
        "\n"
        "The levels differ in what they store. **Full** records the queries "
        "themselves and additional metadata. **Some** stores only counts of "
        "blocks, redirects, and bypasses — no queries. **None** turns logging "
        "off for that endpoint entirely.\n"
        "\n"
        "This is consequential for troubleshooting, because it decides whether "
        "the other tools can see anything for that endpoint. With logging off, "
        "`get_activity_log` returns nothing for it and its block counts are "
        "absent from `get_account_overview` — an absence that means 'not "
        "recorded', not 'nothing happened'. Turning logging up increases what "
        "Control D stores about that network's traffic, so treat it as a "
        "privacy-relevant change rather than a routine one.\n"
        "\n"
        "Find the endpoint with get_inventory and pass its `device_id` as "
        "`endpoint_id`. The first time logging is enabled for an endpoint the "
        "dashboard asks for a storage region; that choice is not made here. This "
        "is reversible — set it back."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id or list of device_ids "
                    "(from get_inventory) to change logging for."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. 'None' stops logging for the endpoint, 'Some' "
                    "records block/redirect/bypass counts only, and 'Full' also "
                    "records the queries themselves."
                ),
            ): probatio.In(endpoint_analytics_logging_mode_labels()),
        }
    )
    _service = SERVICE_SET_ENDPOINT_ANALYTICS_LOGGING

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the addressed endpoints."""
        return {"kind": "endpoint", "id": args[SERVICE_FIELD_ENDPOINT_ID]}

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested logging level."""
        return {"mode": args[SERVICE_FIELD_MODE]}


class SetEndpointProfileTool(_ControlDControlTool):
    """Attach a primary or secondary profile to one or more endpoints."""

    name = format_tool_name(SERVICE_SET_ENDPOINT_PROFILE)
    title = "Set endpoint profile"
    description = (
        "Attach the profile an endpoint enforces, and optionally a second one. "
        "The profile decides what that endpoint blocks, so this is how a device "
        "moves between policies. It changes configuration, not traffic "
        "history.\n"
        "\n"
        "An endpoint always enforces one profile, so the primary slot can be "
        "changed but never emptied. The secondary is optional and can be "
        "cleared with `clear_profile2: true`. Both slots take a `profile_id` "
        "from `get_account_overview`; a profile name is also accepted."
        "\n"
        "\n"
        "When two profiles are enforced, the rule engine merges them before "
        "matching rather than applying them in order, so a custom rule in the "
        "second can override a filter in the first. That is what makes a shared "
        "baseline plus a device-specific policy work.\n"
        "\n"
        "This is reversible: set the previous value back, or clear the "
        "secondary, and the `undo` field names the call."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id or list of device_ids "
                    "(from get_inventory). Ids are unique, so prefer this over a "
                    "name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Optional. The profile PK (from get_account_overview) to "
                    "enforce as the primary. A profile name is also accepted. "
                    "Omit to leave the primary unchanged."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PROFILE2_ID,
                description=(
                    "Optional. The profile PK to enforce as the secondary. "
                    "Omit to leave the secondary unchanged."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_CLEAR_PROFILE2,
                default=False,
                description=(
                    "Optional, defaults to false. Set true to detach the "
                    "secondary profile, leaving only the primary."
                ),
            ): cv.boolean,
        }
    )
    _service = SERVICE_SET_ENDPOINT_PROFILE

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the addressed endpoints and the profile change."""
        return {
            "kind": "endpoint",
            "id": args[SERVICE_FIELD_ENDPOINT_ID],
            "primary": args.get(SERVICE_FIELD_PROFILE_ID),
            "secondary": args.get(SERVICE_FIELD_PROFILE2_ID),
            "clear_secondary": args.get(SERVICE_FIELD_CLEAR_PROFILE2, False),
        }

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the profiles each addressed endpoint enforces now."""
        registry = self._registry(hass)
        if registry is None:
            return None
        endpoints = registry.endpoints
        requested = as_list(args[SERVICE_FIELD_ENDPOINT_ID])
        rows = [
            {
                "device_id": device_id,
                "profile_id": endpoint.owning_profile_pk,
                "profile2_id": endpoint.secondary_profile_pk,
            }
            for device_id in requested
            if (endpoint := endpoints.get(device_id)) is not None
        ]
        return {"endpoints": rows} if rows else None

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return the calls that put each endpoint's own profiles back."""
        registry = self._registry(hass)
        if registry is None:
            return None
        calls: list[str] = []
        for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID]):
            endpoint = registry.endpoints.get(device_id)
            if endpoint is None or endpoint.owning_profile_pk is None:
                continue
            if args.get(SERVICE_FIELD_PROFILE_ID) is not None:
                calls.append(
                    f"{format_tool_name(SERVICE_SET_ENDPOINT_PROFILE)}("
                    f"endpoint_id={device_id!r}, "
                    f"profile_id={endpoint.owning_profile_pk!r})"
                )
            args_as_list = as_list(args.get(SERVICE_FIELD_PROFILE2_ID))
            clearing = bool(args.get(SERVICE_FIELD_CLEAR_PROFILE2))
            if args_as_list or clearing:
                # The registry models both slots, so the reverse names the
                # secondary that was actually attached rather than assuming none.
                previous = endpoint.secondary_profile_pk
                calls.append(
                    f"{format_tool_name(SERVICE_SET_ENDPOINT_PROFILE)}("
                    f"endpoint_id={device_id!r}, profile2_id={previous!r})"
                    if previous
                    else f"{format_tool_name(SERVICE_SET_ENDPOINT_PROFILE)}("
                    f"endpoint_id={device_id!r}, clear_profile2=True)"
                )
        return calls or None

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested profile change."""
        return {
            "primary": args.get(SERVICE_FIELD_PROFILE_ID),
            "secondary": args.get(SERVICE_FIELD_PROFILE2_ID),
            "clear_secondary": args.get(SERVICE_FIELD_CLEAR_PROFILE2, False),
        }


class CreateEndpointTool(_ControlDControlTool):
    """Create one endpoint that enforces a selected profile."""

    name = format_tool_name(SERVICE_CREATE_ENDPOINT)
    title = "Create endpoint"
    description = (
        "Create one endpoint, which is a DNS resolver that enforces a profile. "
        "This is how a new device or router segment is added to Control D.\n"
        "\n"
        "A profile is **required**, because an endpoint always enforces exactly "
        "one and the platform has no endpoint without one. The name must be "
        "unique across the account; the API rejects a duplicate.\n"
        "\n"
        "The endpoint is created **Pending**: it reports `status: 0` and no "
        "activity until it first sends queries, which is the dashboard's own "
        "label for that state and is not a disabled endpoint. "
        "The new `device_id` is assigned by Control D and only exists after the "
        "call, so `undo` names the reverse by **name**, which is unique and "
        "therefore unambiguous.\n"
        "\n"
        "Optionally set `description`, an `icon` slug such as `desktop-linux`, "
        "and the initial analytics logging `mode`. Logging stays off unless "
        "asked for, so choose it deliberately: `Full` records the queries "
        "themselves."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_NAME,
                description=(
                    "Required. The display name for the new endpoint, unique "
                    "across the account."
                ),
            ): cv.string,
            probatio.Required(
                SERVICE_FIELD_PROFILE_ID,
                description=(
                    "Required. The profile PK (from get_account_overview) the "
                    "endpoint enforces. A profile name is also accepted."
                ),
            ): cv.string,
            probatio.Optional(
                SERVICE_FIELD_DESCRIPTION,
                description="Optional. A free-text note stored on the endpoint.",
            ): cv.string,
            probatio.Optional(
                SERVICE_FIELD_ICON,
                description=(
                    "Optional. An icon slug, for example 'desktop-linux' or 'router'."
                ),
            ): cv.string,
            probatio.Optional(
                SERVICE_FIELD_MODE,
                description=(
                    "Optional. The initial analytics logging level: 'None', "
                    "'Some' (counts only), or 'Full' (records the queries). "
                    "Stays off when omitted."
                ),
            ): probatio.In(endpoint_analytics_logging_mode_labels()),
        }
    )
    _service = SERVICE_CREATE_ENDPOINT
    # Creation is additive, so there is no prior state to compare and the
    # "state could not be read" note would give the wrong reason.
    _has_precheck = False

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the endpoint about to be created."""
        return {
            "kind": "endpoint",
            "name": args[SERVICE_FIELD_ENDPOINT_NAME],
            "profile_id": args[SERVICE_FIELD_PROFILE_ID],
        }

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return what was requested, since Control D assigns the id."""
        return {
            "name": args[SERVICE_FIELD_ENDPOINT_NAME],
            "profile_id": args[SERVICE_FIELD_PROFILE_ID],
            "description": args.get(SERVICE_FIELD_DESCRIPTION),
            "icon": args.get(SERVICE_FIELD_ICON),
            "mode": args.get(SERVICE_FIELD_MODE),
        }

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str]:
        """Return the delete that reverses this create.

        The new `device_id` does not exist until the call returns, so the reverse
        is named by the endpoint's own name, which the API keeps unique.
        """
        return [
            f"{format_tool_name(SERVICE_DELETE_ENDPOINT)}("
            f"endpoint_name={args[SERVICE_FIELD_ENDPOINT_NAME]!r})"
        ]


class DeleteEndpointTool(_ControlDControlTool):
    """Permanently delete one or more endpoints."""

    name = format_tool_name(SERVICE_DELETE_ENDPOINT)
    title = "Delete endpoint"
    description = (
        "PERMANENTLY DELETE one or more endpoints. There is no undo, and a new "
        "endpoint created afterwards is a new identity rather than a restored "
        "one.\n"
        "\n"
        "The blast radius is wide, so state it before running it. Deleting an "
        "endpoint removes the resolver itself, so whatever resolves through it "
        "stops being filtered and loses its resolver identity, and the records "
        "kept against it go too. Deleting a router endpoint is the extreme "
        "case: it enforces a profile for a whole network segment, so every "
        "device behind it loses that policy at once.\n"
        "\n"
        "Confirm the target by `endpoint_id` from `get_inventory`. A name works "
        "too, but endpoint names are not guaranteed unique, so an id is the safe "
        "selector. Consider what the caller actually wants: to stop filtering "
        "for now, `set_endpoint_profile` to a permissive profile leaves the "
        "endpoint intact and its history readable, which is usually preferable "
        "to destroying it."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id or list of device_ids "
                    "(from get_inventory). This is permanent."
                ),
            ): probatio.Any(str, [str]),
        }
    )
    _service = SERVICE_DELETE_ENDPOINT
    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Deletion has no prior state to compare and no undo by design, so the
    # "state could not be read" note would give the wrong reason for both.
    _has_precheck = False

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the deleted endpoints."""
        return {"kind": "endpoint", "id": args[SERVICE_FIELD_ENDPOINT_ID]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> None:
        """Deletion is irreversible, so no undo is claimed."""
        return None


class SetEndpointDescriptionTool(_ControlDControlTool):
    """Set the free-text note stored on one or more endpoints."""

    name = format_tool_name(SERVICE_SET_ENDPOINT_DESCRIPTION)
    title = "Set endpoint description"
    description = (
        "Set the free-text note an endpoint carries, or clear it with an empty "
        "string. This is the *description* shown on the endpoint, useful for "
        "recording what a device is or why it is configured a certain way; it "
        "changes no behaviour.\n"
        "\n"
        "Read the current value from `get_inventory`, which reports it under "
        "`advanced.description`. The value is stored as given and an empty "
        "string removes it, because the API drops the field rather than keeping "
        "a blank one.\n"
        "\n"
        "This is reversible: set the previous value back, which `undo` names. "
        "It does not touch the endpoint's name, its profiles, or its clients."
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                SERVICE_FIELD_ENDPOINT_ID,
                description=(
                    "Required. The endpoint device_id or list of device_ids "
                    "(from get_inventory). Ids are unique, so prefer this over a "
                    "name."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_DESCRIPTION,
                description=(
                    "Required. The note to store. An empty string clears the "
                    "description."
                ),
            ): cv.string,
        }
    )
    _service = SERVICE_SET_ENDPOINT_DESCRIPTION

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the addressed endpoints."""
        return {"kind": "endpoint", "id": args[SERVICE_FIELD_ENDPOINT_ID]}

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the descriptions currently stored, read before the write."""
        registry = self._registry(hass)
        if registry is None:
            return None
        rows = [
            {
                "device_id": device_id,
                "description": endpoint.description,
            }
            for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID])
            if (endpoint := registry.endpoints.get(device_id)) is not None
        ]
        return {"endpoints": rows} if rows else None

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed endpoint already carries this note."""
        registry = self._registry(hass)
        if registry is None:
            return False
        wanted = args[SERVICE_FIELD_DESCRIPTION] or None
        requested = as_list(args[SERVICE_FIELD_ENDPOINT_ID])
        endpoints = [registry.endpoints.get(device_id) for device_id in requested]
        if any(endpoint is None for endpoint in endpoints):
            return False
        return all(endpoint.description == wanted for endpoint in endpoints if endpoint)

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested description."""
        return {"description": args[SERVICE_FIELD_DESCRIPTION] or None}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per endpoint, restoring its own previous note."""
        registry = self._registry(hass)
        if registry is None:
            return None
        calls: list[str] = []
        for device_id in as_list(args[SERVICE_FIELD_ENDPOINT_ID]):
            endpoint = registry.endpoints.get(device_id)
            if endpoint is None:
                continue
            calls.append(
                f"{format_tool_name(SERVICE_SET_ENDPOINT_DESCRIPTION)}("
                f"endpoint_id={device_id!r}, "
                f"description={endpoint.description or ''!r})"
            )
        return calls or None


class SetClientAliasTool(_ControlDControlTool):
    """Set a display alias for one client under an endpoint."""

    name = format_tool_name("set_client_alias")
    title = "Set client alias"
    description = (
        "Give one client a friendly display alias. This is cosmetic and "
        "client-scoped: it labels one device seen under an endpoint.\n"
        "\n"
        "A *client* is something seen under an endpoint. This is NOT the same as "
        "renaming an endpoint — an endpoint is the protected row itself, a client "
        "is a device behind it. Use `rename_endpoint` for the endpoint and this "
        "tool for a single device. A device can be both: a client that has been "
        "assigned its own profile becomes an endpoint too, and its alias still "
        "belongs to the client side.\n"
        "\n"
        "Resolve the client with get_inventory using `detail: 'full'`. **Pass its "
        "`client_id`**, which is the identifier the alias API itself uses and the "
        "only one that is guaranteed to address a single client.\n"
        "\n"
        "A MAC is accepted as a convenience but is **not** reliable: a client "
        "commonly appears more than once under one endpoint with the same MAC and "
        "IP but a different `client_id`, and the call then fails as ambiguous. "
        "The same applies to a hostname. When a call reports ambiguity, re-read "
        "the clients and use `client_id`. Note that `endpoint_mac` names the "
        "*client's* MAC, not the endpoint's — endpoints have no MAC at all.\n"
        "\n"
        "Aliases are only available for endpoints that relay client data, which "
        "requires DNS-over-HTTPS.\n"
        "\n"
        "This is reversible: `clear_client_alias` removes it, and the `undo` "
        "field names that call."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_CLIENT_ID,
                description=(
                    "Optional. The client's `client_id` from get_inventory with "
                    "detail 'full'. Recommended: it addresses exactly one client "
                    "and takes precedence over any other selector."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_MAC,
                description=(
                    "Optional. The client's MAC address, from get_inventory with "
                    "detail 'full'. Convenient but not unique: the same MAC can "
                    "appear on several clients under one endpoint. Prefer "
                    "client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_HOSTNAME,
                description=(
                    "Optional. The client's hostname, from get_inventory with "
                    "detail 'full'. Not guaranteed unique. Prefer client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Required(
                SERVICE_FIELD_ALIAS,
                description=(
                    "Required. The friendly label to assign to the client, for "
                    "example 'Kadens iPad'."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_PARENT_ENDPOINT_NAME,
                description=(
                    "Optional. The parent endpoint's name, to disambiguate when "
                    "the same selector matches clients under more than one "
                    "endpoint."
                ),
            ): str,
        }
    )
    _service = SERVICE_SET_CLIENT_ALIAS

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the addressed client."""
        return _client_target(args)

    def _matching_targets(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[Any, ...]:
        """Return the alias targets this call addresses."""
        return _match_client_targets(self._registry(hass), args)

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the clients' current aliases."""
        targets = self._matching_targets(hass, args)
        if not targets:
            return None
        return {"alias": [target.client_alias for target in targets]}

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Return whether every addressed client already carries this alias."""
        targets = self._matching_targets(hass, args)
        if not targets:
            return False
        wanted = args[SERVICE_FIELD_ALIAS]
        return all(target.client_alias == wanted for target in targets)

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested alias."""
        return {"alias": args[SERVICE_FIELD_ALIAS]}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str]:
        """Return the calls that clear the aliases addressed."""
        calls = [
            f"{format_tool_name('clear_client_alias')}({_client_selector_args(target)})"
            for target in self._matching_targets(hass, args)
        ]
        if calls:
            return calls
        selector = _client_selector_args_from_args(args)
        if selector is None:
            return []
        return [f"{format_tool_name('clear_client_alias')}({selector})"]


class ClearClientAliasTool(_ControlDControlTool):
    """Remove a client's display alias."""

    name = format_tool_name("clear_client_alias")
    title = "Clear client alias"
    description = (
        "Remove the display alias from one client, so it is shown by its "
        "hostname or MAC again. Use it to undo a `set_client_alias`.\n"
        "\n"
        "This is client-scoped and cosmetic: it changes no policy and does not "
        "touch the endpoint the client sits under.\n"
        "\n"
        "Resolve the client with get_inventory using `detail: 'full'`. **Pass its "
        "`client_id`**, which is the identifier the alias API uses and the only "
        "one guaranteed to address a single client. A MAC is accepted as a "
        "convenience but is not reliable — a client commonly appears more than "
        "once under one endpoint with the same MAC and IP but a different "
        "`client_id`, which fails as ambiguous. Note that `endpoint_mac` names "
        "the *client's* MAC; endpoints have no MAC at all.\n"
        "\n"
        "Only the alias is removed; the client's traffic and rules are "
        "unaffected."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_CLIENT_ID,
                description=(
                    "Optional. The client's `client_id` from get_inventory with "
                    "detail 'full'. Recommended: it addresses exactly one client "
                    "and takes precedence over any other selector."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_MAC,
                description=(
                    "Optional. The client's MAC address, from get_inventory with "
                    "detail 'full'. Convenient but not unique. Prefer client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_HOSTNAME,
                description=(
                    "Optional. The client's hostname, from get_inventory with "
                    "detail 'full'. Not guaranteed unique. Prefer client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PARENT_ENDPOINT_NAME,
                description=(
                    "Optional. The parent endpoint's name, to disambiguate when "
                    "the same selector matches clients under more than one "
                    "endpoint."
                ),
            ): str,
        }
    )
    _service = SERVICE_CLEAR_CLIENT_ALIAS

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the addressed client."""
        return _client_target(args)

    def _matching_targets(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[Any, ...]:
        """Return the alias targets this call addresses."""
        return _match_client_targets(self._registry(hass), args)

    def _before(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the aliases about to be removed."""
        targets = self._matching_targets(hass, args)
        if not targets:
            return None
        return {"alias": [target.client_alias for target in targets]}

    def _is_already_in_state(self, hass: HomeAssistant, args: dict[str, Any]) -> bool:
        """Clearing is a no-op only when no addressed client has an alias left."""
        targets = self._matching_targets(hass, args)
        if not targets:
            return False
        return all(target.client_alias is None for target in targets)

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the cleared state."""
        return {"alias": None}

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> list[str] | None:
        """Return one call per client, restoring the alias that was removed."""
        calls = [
            f"{format_tool_name('set_client_alias')}("
            f"{_client_selector_args(target)}, alias={target.client_alias!r})"
            for target in self._matching_targets(hass, args)
            if target.client_alias is not None
        ]
        return calls or None


class DeleteClientTool(_ControlDControlTool):
    """Permanently delete client rows and, by default, their query history."""

    name = format_tool_name("delete_client")
    title = "Delete client"
    description = (
        "PERMANENTLY DELETE client rows from one or more endpoints, and by "
        "default their stored query history with them. There is no undo: the "
        "rows and the history cannot be restored.\n"
        "\n"
        "Read this before running it, because the effect is usually not what a "
        "caller expects. A client row exists because Control D *observed* that "
        "client's traffic — it is derived, not configured. Deleting it clears "
        "what is recorded and nothing more: an ordinary client reappears the "
        "next time it is online, so the removal is **not** durable. Only two "
        "things about a client outlive its traffic, an `alias` and a policy "
        "assignment, and this tool changes neither. Where deletion *is* "
        "durable is a client that will never recur, and the everyday case is a "
        "rotating private MAC: each rotation arrives under a new MAC and so "
        "creates its own row that can never be seen again.\n"
        "\n"
        "That makes this a history-hygiene tool, not a device-retirement tool. "
        "If asked to remove clients by age or by a blank MAC, say what it "
        "actually does: on an ordinary client the row comes back, and on a "
        "network that rotates private MACs a sweep clears what exists now while "
        "the next connection adds a fresh row — a recurring chore, not a fix.\n"
        "\n"
        "Select targets exactly as for `set_client_alias`, preferring "
        "`client_id`. A MAC may match several clients, and a hostname such as "
        "`watch` can match a long list produced by repeated rotations, so a "
        "convenience selector can delete far more than intended. Confirm the "
        "resolved list first with get_inventory using `detail: 'full'` and "
        "narrow by `profile_id` or `endpoint_id`.\n"
        "\n"
        "This is not `clear_client_alias`: that removes an alias and leaves the "
        "client in place.\n"
        "\n"
        "Set `delete_history: false` to remove only the rows and keep their "
        "history.\n"
        "\n"
        "The result reports the clients the call **targeted** under "
        "`before.client_count`, not how many the API actually removed, because the "
        "API's own count is not returned through this path. The two can differ if "
        "a selector matched a row that had already gone, so re-read `get_inventory` "
        "afterwards when the exact number matters."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional(
                SERVICE_FIELD_CLIENT_ID,
                description=(
                    "Optional. The client's `client_id` from get_inventory with "
                    "detail 'full'. Recommended: it addresses exactly one "
                    "client and takes precedence over any other selector."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_MAC,
                description=(
                    "Optional. The client's MAC address, from get_inventory with "
                    "detail 'full'. Not unique: the same MAC can appear on "
                    "several clients, and every match is deleted. Prefer "
                    "client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_ENDPOINT_HOSTNAME,
                description=(
                    "Optional. The client's hostname, from get_inventory with "
                    "detail 'full'. A rotating private MAC yields many rows "
                    "under one hostname, so this can match a long list. Prefer "
                    "client_id."
                ),
            ): probatio.Any(str, [str]),
            probatio.Optional(
                SERVICE_FIELD_PARENT_ENDPOINT_NAME,
                description=(
                    "Optional. The parent endpoint's name, to disambiguate when "
                    "the same selector matches clients under more than one "
                    "endpoint."
                ),
            ): str,
            probatio.Optional(
                SERVICE_FIELD_DELETE_HISTORY,
                default=True,
                description=(
                    "Optional, defaults to true. When true the clients' stored "
                    "DNS query history is purged as well. Set false to remove "
                    "only the rows."
                ),
            ): cv.boolean,
        }
    )
    _service = SERVICE_DELETE_CLIENT
    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Deletion has no prior state to compare and no undo by design, so the
    # "state could not be read" note would give the wrong reason for both.
    _has_precheck = False

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the clients this call addresses."""
        return _client_target(args)

    def _matching_targets(
        self, hass: HomeAssistant, args: dict[str, Any]
    ) -> tuple[Any, ...]:
        """Return the alias targets this call addresses."""
        return _match_client_targets(self._registry(hass), args)

    def _before(self, hass: HomeAssistant, args: dict[str, Any]) -> dict[str, Any]:
        """Return what is being destroyed, read before the write."""
        targets = self._matching_targets(hass, args)
        return {
            "client_count": len(targets),
            "clients": [
                {
                    "client_id": target.client_id,
                    "alias": target.client_alias,
                    "hostname": target.client_hostname,
                    "mac_address": target.client_mac_address,
                }
                for target in targets
            ],
            "delete_history": args.get(SERVICE_FIELD_DELETE_HISTORY, True),
        }

    def _undo(self, hass: HomeAssistant, args: dict[str, Any]) -> None:
        """Deletion is irreversible, so no undo is claimed."""
        return None


def build_control_tools(*, entry_id: str, include_destructive: bool) -> list[llm.Tool]:
    """Return the control tools bound to one config entry.

    Reversible controls are always included; the destructive delete is added only
    when the configured tier opts into it.
    """
    tools: list[llm.Tool] = [
        SetFilterStateTool(entry_id=entry_id),
        SetServiceStateTool(entry_id=entry_id),
        DeleteServiceTool(entry_id=entry_id),
        SetOptionStateTool(entry_id=entry_id),
        SetRuleStateTool(entry_id=entry_id),
        SetDefaultRuleStateTool(entry_id=entry_id),
        EnableProfileTool(entry_id=entry_id),
        DisableProfileTool(entry_id=entry_id),
        RenameEndpointTool(entry_id=entry_id),
        CreateEndpointTool(entry_id=entry_id),
        SetEndpointProfileTool(entry_id=entry_id),
        SetEndpointDescriptionTool(entry_id=entry_id),
        SetEndpointAnalyticsLoggingTool(entry_id=entry_id),
        SetClientAliasTool(entry_id=entry_id),
        ClearClientAliasTool(entry_id=entry_id),
        CreateRuleTool(entry_id=entry_id),
    ]
    if include_destructive:
        tools.append(DeleteClientTool(entry_id=entry_id))
        tools.append(DeleteEndpointTool(entry_id=entry_id))
        tools.append(DeleteRuleTool(entry_id=entry_id))
    return tools
