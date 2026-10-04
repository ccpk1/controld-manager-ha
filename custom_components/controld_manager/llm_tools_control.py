"""LLM control tools for Control D Manager.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names below are
never imported on older Home Assistant.

Each control tool delegates to an existing service and returns the action-result
envelope. Control D writes have no admin gate, so the configured tier is the only
thing deciding which of these are reachable at all.
"""

from __future__ import annotations

from typing import Any, Final, cast, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_RULE,
    SERVICE_DISABLE_PROFILE,
    SERVICE_ENABLE_PROFILE,
    SERVICE_FIELD_CANCEL_EXPIRATION,
    SERVICE_FIELD_COMMENT,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_EXPIRATION_DURATION,
    SERVICE_FIELD_EXPIRE_AT,
    SERVICE_FIELD_FILTER_ID,
    SERVICE_FIELD_FILTER_NAME,
    SERVICE_FIELD_HOSTNAME,
    SERVICE_FIELD_MINUTES,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_OPTION_ID,
    SERVICE_FIELD_OPTION_NAME,
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
    SERVICE_SET_DEFAULT_RULE_STATE,
    SERVICE_SET_FILTER_STATE,
    SERVICE_SET_OPTION_STATE,
    SERVICE_SET_RULE_STATE,
    SERVICE_SET_SERVICE_STATE,
)
from .llm_tools_common import format_tool_name
from .models import (
    default_rule_mode_labels,
    rule_action_options,
    service_mode_labels,
)
from .utils.action_result import (
    ACTION_STATUS_APPLIED,
    ACTION_STATUS_FAILED,
    build_action_result,
)

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


class _ControlDControlTool(llm.Tool):
    """Base class for a Control D control tool backed by a service."""

    integration = DOMAIN
    annotations = _CONTROL_ANNOTATIONS

    _service: str

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    def _args(self, tool_input: llm.ToolInput) -> dict[str, Any]:
        """Return tool args validated against the declared schema."""
        return cast(dict[str, Any], self.parameters(tool_input.tool_args))

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the resolved target to report, from the caller's own input."""
        return {key: value for key, value in args.items() if value is not None}

    def _before(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Return the state observed before the action, when it can be read."""
        return None

    def _after(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Return the state the action requests."""
        return None

    def _undo(self, args: dict[str, Any]) -> str | None:
        """Return the exact call that reverses the action, or None."""
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
        target = self._target(args)
        service_data = {**args, SERVICE_FIELD_CONFIG_ENTRY_ID: self._entry_id}
        try:
            await hass.services.async_call(
                DOMAIN,
                self._service,
                service_data,
                blocking=True,
                context=llm_context.context,
            )
        except HomeAssistantError:
            return llm.ToolResult(
                data=build_action_result(
                    status=ACTION_STATUS_FAILED,
                    target=target,
                    changed=False,
                    before=self._before(args),
                ),
                error=True,
            )

        return llm.ToolResult(
            data=build_action_result(
                status=ACTION_STATUS_APPLIED,
                target=target,
                changed=True,
                before=self._before(args),
                after=self._after(args),
                undo=self._undo(args),
            )
        )


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
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_FILTER_ID,
                description=(
                    "Optional. A filter id or list of ids (from get_catalog). "
                    "Provide this or filter_name."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_FILTER_NAME,
                description=(
                    "Optional. A filter name or list of names (from get_catalog). "
                    "Provide this or filter_id."
                ),
            ): vol.Any(str, [str]),
            vol.Required(
                SERVICE_FIELD_ENABLED,
                description="Required. True to enable the filter, false to disable it.",
            ): bool,
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_FILTER_STATE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested enabled state."""
        return {"enabled": args[SERVICE_FIELD_ENABLED]}

    def _undo(self, args: dict[str, Any]) -> str:
        """Return the call that flips the filter back."""
        filters = args.get(SERVICE_FIELD_FILTER_ID) or args.get(
            SERVICE_FIELD_FILTER_NAME
        )
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return (
            f"{format_tool_name('set_filter_state')}(filter_id={filters!r}, "
            f"profile_id={profile!r}, enabled={not args[SERVICE_FIELD_ENABLED]})"
        )


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
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_SERVICE_ID,
                description=(
                    "Optional. A service id or list of ids (from get_catalog). "
                    "Provide this or service_name."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_SERVICE_NAME,
                description=(
                    "Optional. A service name or list of names (from "
                    "get_catalog). Provide this or service_id."
                ),
            ): vol.Any(str, [str]),
            vol.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. How to handle the service: 'blocked', 'bypassed', "
                    "or a redirect mode."
                ),
            ): vol.In(service_mode_labels()),
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): vol.In(("location", "ip")),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_SERVICE_STATE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested mode."""
        return {"mode": args[SERVICE_FIELD_MODE]}

    def _undo(self, args: dict[str, Any]) -> str | None:
        """Services have no single inverse mode, so no undo is claimed."""
        return None


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
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_OPTION_ID,
                description=(
                    "Optional. An option id or list of ids (from get_catalog). "
                    "Provide this or option_name."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_OPTION_NAME,
                description=(
                    "Optional. An option name or list of names (from "
                    "get_catalog). Provide this or option_id."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_ENABLED,
                description=(
                    "Optional. For a toggle option: true to enable it, false to "
                    "disable it."
                ),
            ): bool,
            vol.Optional(
                SERVICE_FIELD_VALUE,
                description=(
                    "Optional. For a dropdown option: the value to set, using "
                    "the choices reported by get_catalog."
                ),
            ): vol.Any(str, int),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_OPTION_STATE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return whichever of the enabled/value pair was requested."""
        after: dict[str, Any] = {}
        if SERVICE_FIELD_ENABLED in args:
            after["enabled"] = args[SERVICE_FIELD_ENABLED]
        if SERVICE_FIELD_VALUE in args:
            after["value"] = args[SERVICE_FIELD_VALUE]
        return after

    def _undo(self, args: dict[str, Any]) -> str | None:
        """The previous value is not read here, so no undo is claimed."""
        return None


class SetRuleStateTool(_ControlDControlTool):
    """Enable, disable, or modify one custom rule."""

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
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_IDENTITY,
                description=(
                    "Required. The rule identity or list of identities (from "
                    "get_catalog, catalog_type 'rules')."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_ENABLED,
                description="Optional. True to enable the rule, false to disable it.",
            ): bool,
            vol.Optional(
                SERVICE_FIELD_MODE,
                description=(
                    "Optional. Change what the rule does: 'blocked', 'bypassed', "
                    "or a redirect mode."
                ),
            ): vol.In(rule_action_options()),
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): vol.In(("location", "ip")),
            vol.Optional(SERVICE_FIELD_COMMENT, description=_COMMENT_DESCRIPTION): str,
            vol.Optional(
                SERVICE_FIELD_EXPIRATION_DURATION,
                description=_EXPIRATION_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_EXPIRE_AT,
                description=(
                    "Optional. An absolute expiry as an ISO 8601 timestamp. Use "
                    "instead of expiration_duration when the moment is known."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_CANCEL_EXPIRATION,
                description=(
                    "Optional. True to clear an existing expiry, making the "
                    "change permanent."
                ),
            ): bool,
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_RULE_STATE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested rule state."""
        after: dict[str, Any] = {}
        for key in (
            SERVICE_FIELD_ENABLED,
            SERVICE_FIELD_MODE,
            SERVICE_FIELD_COMMENT,
            SERVICE_FIELD_EXPIRE_AT,
            SERVICE_FIELD_EXPIRATION_DURATION,
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
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. The catch-all action: 'blocking', 'bypassing', or "
                    "'redirecting'."
                ),
            ): vol.In(default_rule_mode_labels()),
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): vol.In(("location", "ip")),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_SET_DEFAULT_RULE_STATE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested default mode."""
        return {"mode": args[SERVICE_FIELD_MODE]}


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
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): vol.Any(str, [str]),
        }
    )
    _service = SERVICE_ENABLE_PROFILE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested paused state."""
        return {"paused": False}

    def _undo(self, args: dict[str, Any]) -> str:
        """Return the call that pauses the profile again."""
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return f"{format_tool_name('disable_profile')}(profile_id={profile!r})"


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
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_MINUTES,
                description=(
                    "Optional. How long to disable the profile for, in minutes. "
                    "Defaults to a short window. Prefer a short value; the "
                    "profile re-enables itself when it elapses."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        }
    )
    _service = SERVICE_DISABLE_PROFILE

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested paused state and duration."""
        return {"paused": True, "minutes": args.get(SERVICE_FIELD_MINUTES)}

    def _undo(self, args: dict[str, Any]) -> str:
        """Return the call that re-enables the profile."""
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return f"{format_tool_name('enable_profile')}(profile_id={profile!r})"


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
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_HOSTNAME,
                description=(
                    "Required. The domain or list of domains to create the rule "
                    "for, as bare domains such as 'example.com'."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_MODE,
                description=(
                    "Optional. What the rule does: 'blocked' (the default), "
                    "'bypassed' to make an exception, or a redirect mode."
                ),
            ): vol.In(rule_action_options()),
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET,
                description=_REDIRECT_TARGET_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_REDIRECT_TARGET_TYPE,
                description=_REDIRECT_TARGET_TYPE_DESCRIPTION,
            ): vol.In(("location", "ip")),
            vol.Optional(
                SERVICE_FIELD_RULE_GROUP_ID,
                description=(
                    "Optional. The folder to create the rule in, by id (from "
                    "get_catalog, catalog_type 'rules'). Omit to use the root."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_RULE_GROUP_NAME,
                description=(
                    "Optional. The folder to create the rule in, by name. "
                    "Provide this or rule_group_id."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_ENABLED,
                description=(
                    "Optional. Defaults to true. Set false to create the rule "
                    "switched off."
                ),
            ): bool,
            vol.Optional(SERVICE_FIELD_COMMENT, description=_COMMENT_DESCRIPTION): str,
            vol.Optional(
                SERVICE_FIELD_EXPIRATION_DURATION,
                description=_EXPIRATION_DESCRIPTION,
            ): str,
            vol.Optional(
                SERVICE_FIELD_EXPIRE_AT,
                description=("Optional. An absolute expiry as an ISO 8601 timestamp."),
            ): str,
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_CREATE_RULE
    annotations = _NON_IDEMPOTENT_ANNOTATIONS

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the created rule target."""
        return {"hostname": args[SERVICE_FIELD_HOSTNAME]}

    def _after(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the requested rule state."""
        return {
            "mode": args.get(SERVICE_FIELD_MODE),
            "enabled": args.get(SERVICE_FIELD_ENABLED, True),
        }

    def _undo(self, args: dict[str, Any]) -> str:
        """Return the delete call that removes the created rule."""
        hostname = args[SERVICE_FIELD_HOSTNAME]
        profile = args.get(SERVICE_FIELD_PROFILE_ID) or args.get(
            SERVICE_FIELD_PROFILE_NAME
        )
        return (
            f"{format_tool_name('delete_rule')}(rule_identity={hostname!r}, "
            f"profile_id={profile!r})"
        )


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
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_IDENTITY,
                description=(
                    "Required. The rule identity or list of identities to delete "
                    "(from get_catalog, catalog_type 'rules'). This is "
                    "permanent."
                ),
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_ID, description=_PROFILE_ID_DESCRIPTION
            ): vol.Any(str, [str]),
            vol.Optional(
                SERVICE_FIELD_PROFILE_NAME, description=_PROFILE_NAME_DESCRIPTION
            ): str,
        }
    )
    _service = SERVICE_DELETE_RULE
    annotations = _DESTRUCTIVE_ANNOTATIONS

    def _target(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the deleted rule target."""
        return {"rule_identity": args[SERVICE_FIELD_RULE_IDENTITY]}

    def _undo(self, args: dict[str, Any]) -> None:
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
        SetOptionStateTool(entry_id=entry_id),
        SetRuleStateTool(entry_id=entry_id),
        SetDefaultRuleStateTool(entry_id=entry_id),
        EnableProfileTool(entry_id=entry_id),
        DisableProfileTool(entry_id=entry_id),
        CreateRuleTool(entry_id=entry_id),
    ]
    if include_destructive:
        tools.append(DeleteRuleTool(entry_id=entry_id))
    return tools
