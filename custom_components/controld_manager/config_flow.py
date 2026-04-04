"""Config and options flows for Control D Manager."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, ClassVar, Self

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ControlDApiAuthError,
    ControlDAPIClient,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import (
    CONF_ADVANCED_PROFILE_OPTIONS,
    CONF_ALLOWED_SERVICE_CATEGORIES,
    CONF_API_TOKEN,
    CONF_AUTO_ENABLE_SERVICE_SWITCHES,
    CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES,
    CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES,
    CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    CONF_ENDPOINT_SENSORS_ENABLED,
    CONF_ENTRY_NAME,
    CONF_EXPOSED_CUSTOM_RULES,
    CONF_MANAGED_IN_HOME_ASSISTANT,
    CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES,
    DEFAULT_TITLE,
    DOMAIN,
    MAX_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    MAX_REFRESH_INTERVAL,
    MIN_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    MIN_REFRESH_INTERVAL,
    TRANS_KEY_CANNOT_CONNECT,
    TRANS_KEY_INVALID_AUTH,
    TRANS_KEY_UNKNOWN,
)
from .models import (
    ControlDManagerRuntime,
    ControlDOptions,
    ControlDRefreshIntervals,
    ControlDUser,
    build_rule_group_target,
    build_rule_identity,
    build_rule_item_target,
    rule_action_label_from_action_do,
)


async def _async_validate_input(
    flow: ControlDManagerConfigFlow, user_input: dict[str, Any]
) -> ControlDUser:
    """Validate config-flow user input against the Control D API."""
    session = async_get_clientsession(flow.hass)
    client = ControlDAPIClient(user_input[CONF_API_TOKEN], session)
    return await client.async_get_instance_identity()


STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_TOKEN): str})


class ControlDManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Control D Manager."""

    VERSION = 1
    MINOR_VERSION = 1

    def is_matching(self, other_flow: Self) -> bool:
        """Return whether another flow matches this one."""
        del other_flow
        return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ControlDManagerOptionsFlow:
        """Return the options flow handler."""
        return ControlDManagerOptionsFlow(config_entry)

    def _get_entry_title(self) -> str:
        """Return the default title for a newly created config entry."""
        entry_count = len(self._async_current_entries())
        if entry_count == 0:
            return DEFAULT_TITLE
        return f"{DEFAULT_TITLE} {entry_count + 1}"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate once and create one entry per Control D instance."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors={}
            )

        errors: dict[str, str] = {}

        try:
            user = await _async_validate_input(self, user_input)
        except ControlDApiAuthError:
            errors["base"] = TRANS_KEY_INVALID_AUTH
        except ControlDApiConnectionError:
            errors["base"] = TRANS_KEY_CANNOT_CONNECT
        except ControlDApiResponseError, ValueError:
            errors["base"] = TRANS_KEY_UNKNOWN
        else:
            await self.async_set_unique_id(user.instance_id)
            self._abort_if_unique_id_configured()
            title = self._get_entry_title()
            return self.async_create_entry(
                title=title,
                data={**user_input, CONF_ENTRY_NAME: title},
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class ControlDManagerOptionsFlow(OptionsFlow):
    """Handle the menu-driven options flow."""

    _RULE_STATE_PREFIX: ClassVar[dict[int, str]] = {
        0: "⛔ ",
        1: "✅ ",
        2: "↪️ ",
    }
    _FOLDER_STATE_PREFIX: ClassVar[dict[int | None, str]] = {
        0: "📁 ",
        1: "📁 ",
        2: "📁 ",
        None: "📁 ",
    }

    @classmethod
    def _rule_prefix(cls, action_do: int) -> str:
        """Return the web-style prefix for one rule action."""
        return cls._RULE_STATE_PREFIX.get(action_do, cls._RULE_STATE_PREFIX[1])

    @classmethod
    def _folder_prefix(cls, action_do: int | None) -> str:
        """Return the web-style prefix for one folder action."""
        return cls._FOLDER_STATE_PREFIX.get(action_do, cls._FOLDER_STATE_PREFIX[None])

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry
        self._options = ControlDOptions.from_mapping(dict(config_entry.options))
        self._selected_profile_pk: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the top-level options menu."""
        del user_input
        return self.async_show_menu(
            step_id="init",
            menu_options=["select_profile", "integration_settings"],
        )

    async def async_step_select_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one Control D profile to edit."""
        errors: dict[str, str] = {}
        profile_choices: dict[str, str] = {}

        try:
            profile_choices = await self._async_get_profile_choices()
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
            ValueError,
        ) as err:
            errors["base"] = self._options_error_key(err)

        if user_input is not None:
            self._selected_profile_pk = user_input["profile_pk"]
            return await self.async_step_edit_profile()

        return self.async_show_form(
            step_id="select_profile",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "profile_pk", default=self._selected_profile_pk
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=profile_pk, label=label)
                                for profile_pk, label in profile_choices.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_edit_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one profile policy end to end."""
        if self._selected_profile_pk is None:
            return await self.async_step_select_profile()

        errors: dict[str, str] = {}
        profiles: dict[str, str] = {}
        service_categories: dict[str, str] = {}
        rule_targets: dict[str, str] = {}

        try:
            profiles = await self._async_get_profile_choices()
            service_categories = await self._async_get_service_category_choices()
            rule_targets = await self._async_get_rule_target_choices(
                self._selected_profile_pk
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
            ValueError,
        ) as err:
            errors["base"] = self._options_error_key(err)

        profile_policy = self._options.profile_policy(self._selected_profile_pk)
        if user_input is not None:
            profile_policies = dict(self._options.profile_policies)
            profile_policies[self._selected_profile_pk] = replace(
                profile_policy,
                managed_in_home_assistant=bool(
                    user_input[CONF_MANAGED_IN_HOME_ASSISTANT]
                ),
                advanced_profile_options=bool(
                    user_input[CONF_ADVANCED_PROFILE_OPTIONS]
                ),
                endpoint_sensors_enabled=bool(
                    user_input[CONF_ENDPOINT_SENSORS_ENABLED]
                ),
                endpoint_inactivity_threshold_minutes=int(
                    user_input[CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES]
                ),
                allowed_service_categories=frozenset(
                    user_input[CONF_ALLOWED_SERVICE_CATEGORIES]
                ),
                auto_enable_service_switches=bool(
                    user_input[CONF_AUTO_ENABLE_SERVICE_SWITCHES]
                ),
                exposed_custom_rules=frozenset(user_input[CONF_EXPOSED_CUSTOM_RULES]),
            )
            self._options = replace(self._options, profile_policies=profile_policies)
            await self._async_apply_updated_options()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_profile",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MANAGED_IN_HOME_ASSISTANT,
                        default=profile_policy.managed_in_home_assistant,
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_ADVANCED_PROFILE_OPTIONS,
                        default=profile_policy.advanced_profile_options,
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_ENDPOINT_SENSORS_ENABLED,
                        default=profile_policy.endpoint_sensors_enabled,
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
                        default=profile_policy.endpoint_inactivity_threshold_minutes,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
                            max=MAX_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
                            mode=selector.NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                    vol.Required(
                        CONF_ALLOWED_SERVICE_CATEGORIES,
                        default=sorted(profile_policy.allowed_service_categories),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=category_pk,
                                    label=label,
                                )
                                for category_pk, label in service_categories.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_AUTO_ENABLE_SERVICE_SWITCHES,
                        default=profile_policy.auto_enable_service_switches,
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_EXPOSED_CUSTOM_RULES,
                        default=sorted(profile_policy.exposed_custom_rules),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=target, label=label)
                                for target, label in rule_targets.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "profile_name": profiles.get(
                    self._selected_profile_pk, self._selected_profile_pk
                )
            },
        )

    async def async_step_integration_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._options = replace(
                self._options,
                configuration_sync_interval=timedelta(
                    minutes=user_input[CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES]
                ),
                profile_analytics_interval=timedelta(
                    minutes=user_input[CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES]
                ),
                endpoint_analytics_interval=timedelta(
                    minutes=user_input[CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES]
                ),
            )
            await self._async_apply_updated_options()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="integration_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES,
                        default=int(
                            self._options.configuration_sync_interval.total_seconds()
                            // 60
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=int(MIN_REFRESH_INTERVAL.total_seconds() // 60),
                            max=int(MAX_REFRESH_INTERVAL.total_seconds() // 60),
                            mode=selector.NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                    vol.Required(
                        CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES,
                        default=int(
                            self._options.profile_analytics_interval.total_seconds()
                            // 60
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=int(MIN_REFRESH_INTERVAL.total_seconds() // 60),
                            max=int(MAX_REFRESH_INTERVAL.total_seconds() // 60),
                            mode=selector.NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                    vol.Required(
                        CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES,
                        default=int(
                            self._options.endpoint_analytics_interval.total_seconds()
                            // 60
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=int(MIN_REFRESH_INTERVAL.total_seconds() // 60),
                            max=int(MAX_REFRESH_INTERVAL.total_seconds() // 60),
                            mode=selector.NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                }
            ),
        )

    async def _async_get_client(self) -> ControlDAPIClient:
        """Return an authenticated client for the current config entry."""
        session = async_get_clientsession(self.hass)
        return ControlDAPIClient(self._entry.data[CONF_API_TOKEN], session)

    async def _async_get_profile_choices(self) -> dict[str, str]:
        """Return the current discovered profile choices."""
        client = await self._async_get_client()
        profiles = await client.async_get_profiles()
        return {
            str(profile["PK"]): str(profile["name"])
            for profile in profiles
            if isinstance(profile.get("PK"), str)
            and isinstance(profile.get("name"), str)
        }

    async def _async_get_service_category_choices(self) -> dict[str, str]:
        """Return the current service-category choices."""
        client = await self._async_get_client()
        categories = await client.async_get_service_categories()
        return {
            str(category["PK"]): (
                f"{category['name']} ({int(category.get('count', 0) or 0)} services)"
            )
            for category in categories
            if isinstance(category.get("PK"), str)
            and isinstance(category.get("name"), str)
        }

    async def _async_get_rule_target_choices(self, profile_pk: str) -> dict[str, str]:
        """Return the current selectable folder and rule targets for one profile."""
        client = await self._async_get_client()
        groups, rules = (
            await client.async_get_profile_groups(profile_pk),
            await client.async_get_profile_rules(profile_pk),
        )
        choices: dict[str, str] = {}
        group_names = {
            str(group["PK"]): str(group["group"])
            for group in groups
            if "PK" in group and isinstance(group.get("group"), str)
        }
        for group in groups:
            if not isinstance(group.get("PK"), (str, int)) or not isinstance(
                group.get("group"), str
            ):
                continue
            folder_pk = str(group["PK"])
            group_action_do: int | None = None
            group_action = ""
            if isinstance(group.get("action"), dict) and "do" in group["action"]:
                group_action_do = int(group["action"]["do"])
                group_action = rule_action_label_from_action_do(group_action_do)
            action_suffix = f" ({group_action})" if group_action else ""
            choices[build_rule_group_target(folder_pk)] = (
                f"{self._folder_prefix(group_action_do)}{group['group']}{action_suffix}"
            )
        for rule in rules:
            if not isinstance(rule.get("PK"), str):
                continue
            group_value = rule.get("group")
            group_pk: str | None = None
            if isinstance(group_value, int) and group_value != 0:
                group_pk = str(group_value)
            elif isinstance(group_value, str) and group_value and group_value != "0":
                group_pk = group_value
            identity = build_rule_identity(group_pk, rule["PK"])
            target = build_rule_item_target(identity)
            action_label = rule_action_label_from_action_do(
                int(
                    rule.get("action", {}).get("do", 1)
                    if isinstance(rule.get("action"), dict)
                    else 1
                )
            )
            action_do = int(
                rule.get("action", {}).get("do", 1)
                if isinstance(rule.get("action"), dict)
                else 1
            )
            if group_pk is not None and group_pk in group_names:
                choices[target] = (
                    f"📁 {group_names[group_pk]} / "
                    f"↳ {self._rule_prefix(action_do)}{rule['PK']} ({action_label})"
                )
            else:
                choices[target] = (
                    f"{self._rule_prefix(action_do)}{rule['PK']} ({action_label})"
                )
        return dict(sorted(choices.items(), key=lambda item: item[1].lower()))

    async def _async_apply_updated_options(self) -> None:
        """Persist options and apply them to the live runtime immediately."""
        self.hass.config_entries.async_update_entry(
            self._entry, options=self._options.as_mapping()
        )
        runtime = getattr(self._entry, "runtime_data", None)
        if not isinstance(runtime, ControlDManagerRuntime):
            return
        runtime.options = self._options
        runtime.refresh_intervals = ControlDRefreshIntervals(
            configuration_sync=self._options.configuration_sync_interval,
            profile_analytics=self._options.profile_analytics_interval,
            endpoint_analytics=self._options.endpoint_analytics_interval,
        )
        runtime.active_coordinator.update_interval = (
            runtime.refresh_intervals.configuration_sync
        )
        await runtime.active_coordinator.async_refresh()

    @staticmethod
    def _options_error_key(err: Exception) -> str:
        """Return the translated error key for options-flow API failures."""
        if isinstance(err, ControlDApiAuthError):
            return TRANS_KEY_INVALID_AUTH
        if isinstance(err, ControlDApiConnectionError):
            return TRANS_KEY_CANNOT_CONNECT
        return TRANS_KEY_UNKNOWN
