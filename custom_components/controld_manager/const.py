"""Constants for the Control D Manager integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "controld_manager"
DEFAULT_TITLE = "Control D"
MANUFACTURER = "Control D"
MODEL_INSTANCE = "Instance"
MODEL_PROFILE = "Profile"

CONF_API_TOKEN = "api_token"
CONF_ENTRY_NAME = "entry_name"
CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES = "configuration_sync_interval_minutes"
CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES = "profile_analytics_interval_minutes"
CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES = "endpoint_analytics_interval_minutes"
CONF_PROFILE_POLICIES = "profile_policies"
CONF_MANAGED_IN_HOME_ASSISTANT = "managed_in_home_assistant"
CONF_EXPOSE_EXTERNAL_FILTERS = "expose_external_filters"
CONF_ADVANCED_PROFILE_OPTIONS = "advanced_profile_options"
CONF_ENDPOINT_SENSORS_ENABLED = "endpoint_sensors_enabled"
CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES = "endpoint_inactivity_threshold_minutes"
CONF_ALLOWED_SERVICE_CATEGORIES = "allowed_service_categories"
CONF_AUTO_ENABLE_SERVICE_SWITCHES = "auto_enable_service_switches"
CONF_EXPOSED_CUSTOM_RULES = "exposed_custom_rules"

REFRESH_GROUP_CONFIGURATION_SYNC = "configuration_sync"
REFRESH_GROUP_PROFILE_ANALYTICS = "profile_analytics"
REFRESH_GROUP_ENDPOINT_ANALYTICS = "endpoint_analytics"

DEFAULT_CONFIGURATION_SYNC_INTERVAL = timedelta(minutes=15)
DEFAULT_PROFILE_ANALYTICS_INTERVAL = timedelta(minutes=5)
DEFAULT_ENDPOINT_ANALYTICS_INTERVAL = timedelta(minutes=5)

MIN_REFRESH_INTERVAL = timedelta(minutes=5)
MAX_REFRESH_INTERVAL = timedelta(minutes=60)
DEFAULT_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES = 15
MIN_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES = 5
MAX_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES = 60
DEFAULT_ENABLED_FILTERS = frozenset({"ads", "typo"})
CORE_PROFILE_OPTION_TOGGLES = frozenset({"safesearch", "safeyoutube"})
CORE_PROFILE_OPTION_SELECTS = frozenset({"ai_malware"})
ADVANCED_PROFILE_OPTION_TOGGLES = frozenset(
    {
        "block_rfc1918",
        "no_dnssec",
        "spoof_ipv6",
        "dns64",
        "cflat",
        "ttl_blck",
        "ttl_spff",
        "ttl_pass",
    }
)
ADVANCED_PROFILE_OPTION_SELECTS = frozenset({"b_resp"})
SUPPORTED_PROFILE_OPTION_TOGGLES = (
    CORE_PROFILE_OPTION_TOGGLES | ADVANCED_PROFILE_OPTION_TOGGLES
)
SUPPORTED_PROFILE_OPTION_SELECTS = (
    CORE_PROFILE_OPTION_SELECTS | ADVANCED_PROFILE_OPTION_SELECTS
)

PLATFORMS: tuple[Platform, ...] = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
)

SERVICE_DISABLE_PROFILE = "disable_profile"
SERVICE_ENABLE_PROFILE = "enable_profile"
SERVICE_GET_CATALOG = "get_catalog"
SERVICE_SET_FILTER_STATE = "set_filter_state"
SERVICE_SET_SERVICE_STATE = "set_service_state"
SERVICE_FIELD_CATALOG_TYPE = "catalog_type"
SERVICE_FIELD_CONFIG_ENTRY_ID = "config_entry_id"
SERVICE_FIELD_CONFIG_ENTRY_NAME = "config_entry_name"
SERVICE_FIELD_ENABLED = "enabled"
SERVICE_FIELD_FILTER_ID = "filter_id"
SERVICE_FIELD_FILTER_NAME = "filter_name"
SERVICE_FIELD_MODE = "mode"
SERVICE_FIELD_MINUTES = "minutes"
SERVICE_FIELD_PROFILE_ID = "profile_id"
SERVICE_FIELD_PROFILE_NAME = "profile_name"
SERVICE_FIELD_SERVICE_ID = "service_id"
SERVICE_FIELD_SERVICE_NAME = "service_name"
DEFAULT_DISABLE_MINUTES = 60

ATTR_PURPOSE = "purpose"
ATTR_ATTACHED_PROFILES = "attached_profiles"
ATTR_PARENT_DEVICE_ID = "parent_device_id"
ATTR_PAUSED_UNTIL = "paused_until"
ATTR_LAST_ACTIVE = "last_active"
ATTR_ACTIVITY_THRESHOLD_MINUTES = "activity_threshold_minutes"
ATTR_GROUP = "group"
ATTR_RULE_IDENTITY = "rule_identity"
ATTR_ACTION = "action"
ATTR_COMMENT = "comment"
ATTR_DISCOVERED_ENDPOINT_COUNT = "discovered_endpoint_count"
ATTR_ROUTER_CLIENT_COUNT = "router_client_count"
ATTR_LAST_REFRESH_ATTEMPT = "last_refresh_attempt"
ATTR_LAST_SUCCESSFUL_REFRESH = "last_successful_refresh"
ATTR_LAST_REFRESH_ERROR = "last_refresh_error"
ATTR_REFRESH_IN_PROGRESS = "refresh_in_progress"
ATTR_LAST_REFRESH_TRIGGER = "last_refresh_trigger"
ATTR_ACCOUNT_STATUS = "account_status"
ATTR_STATS_ENDPOINT = "stats_endpoint"
ATTR_CONSECUTIVE_FAILED_REFRESHES = "consecutive_failed_refreshes"

TRANS_KEY_NOT_IMPLEMENTED = "not_implemented"
TRANS_KEY_ALREADY_CONFIGURED = "already_configured"
TRANS_KEY_CANNOT_CONNECT = "cannot_connect"
TRANS_KEY_INVALID_AUTH = "invalid_auth"
TRANS_KEY_UNKNOWN = "unknown"
TRANS_KEY_CONFIG_ENTRY_NOT_FOUND = "config_entry_not_found"
TRANS_KEY_CONFIG_ENTRY_NAME_NOT_FOUND = "config_entry_name_not_found"
TRANS_KEY_CONFIG_ENTRY_NAME_AMBIGUOUS = "config_entry_name_ambiguous"
TRANS_KEY_CONFIG_ENTRY_NOT_LOADED = "config_entry_not_loaded"
TRANS_KEY_MULTIPLE_ENTRIES_LOADED = "multiple_entries_loaded"
TRANS_KEY_WRONG_INTEGRATION_ENTRY = "wrong_integration_entry"
TRANS_KEY_PROFILE_TARGET_REQUIRED = "profile_target_required"
TRANS_KEY_PROFILE_TARGET_NOT_FOUND = "profile_target_not_found"
TRANS_KEY_PROFILE_TARGET_AMBIGUOUS = "profile_target_ambiguous"
TRANS_KEY_FILTER_TARGET_REQUIRED = "filter_target_required"
TRANS_KEY_FILTER_NAME_NOT_FOUND = "filter_name_not_found"
TRANS_KEY_FILTER_NAME_AMBIGUOUS = "filter_name_ambiguous"
TRANS_KEY_SERVICE_TARGET_REQUIRED = "service_target_required"
TRANS_KEY_SERVICE_NAME_NOT_FOUND = "service_name_not_found"
TRANS_KEY_SERVICE_NAME_AMBIGUOUS = "service_name_ambiguous"
TRANS_KEY_RULE_GROUP_TARGET_REQUIRED = "rule_group_target_required"
TRANS_KEY_RULE_GROUP_NAME_NOT_FOUND = "rule_group_name_not_found"
TRANS_KEY_RULE_GROUP_NAME_AMBIGUOUS = "rule_group_name_ambiguous"
TRANS_KEY_RULE_TARGET_REQUIRED = "rule_target_required"
TRANS_KEY_RULE_NAME_NOT_FOUND = "rule_name_not_found"
TRANS_KEY_RULE_NAME_AMBIGUOUS = "rule_name_ambiguous"
TRANS_KEY_OPTION_TARGET_REQUIRED = "option_target_required"
TRANS_KEY_OPTION_NAME_NOT_FOUND = "option_name_not_found"
TRANS_KEY_OPTION_NAME_AMBIGUOUS = "option_name_ambiguous"
TRANS_KEY_DISABLE_PROFILES_FAILED = "disable_profiles_failed"
TRANS_KEY_ENABLE_PROFILES_FAILED = "enable_profiles_failed"
TRANS_KEY_SET_FILTERS_FAILED = "set_filters_failed"
TRANS_KEY_SET_SERVICES_FAILED = "set_services_failed"
TRANS_KEY_SERVICE_MODE_REJECTED = "service_mode_rejected"
TRANS_KEY_MANUAL_SYNC_FAILED = "manual_sync_failed"
TRANS_KEY_FILTER_NOT_FOUND = "filter_not_found"
TRANS_KEY_FILTER_MODE_UNSUPPORTED = "filter_mode_unsupported"
TRANS_KEY_FILTER_MODE_UPDATE_FAILED = "filter_mode_update_failed"
TRANS_KEY_SERVICE_NOT_FOUND = "service_not_found"
TRANS_KEY_SERVICE_MODE_UNSUPPORTED = "service_mode_unsupported"
TRANS_KEY_SERVICE_UPDATE_FAILED = "service_update_failed"
TRANS_KEY_DEFAULT_RULE_MODE_UNSUPPORTED = "default_rule_mode_unsupported"
TRANS_KEY_DEFAULT_RULE_NOT_FOUND = "default_rule_not_found"
TRANS_KEY_DEFAULT_RULE_UPDATE_FAILED = "default_rule_update_failed"
TRANS_KEY_RULE_GROUP_MODE_UNSUPPORTED = "rule_group_mode_unsupported"
TRANS_KEY_RULE_GROUP_NOT_FOUND = "rule_group_not_found"
TRANS_KEY_RULE_GROUP_UPDATE_FAILED = "rule_group_update_failed"
TRANS_KEY_OPTION_NOT_FOUND = "option_not_found"
TRANS_KEY_OPTION_VALUE_UNSUPPORTED = "option_value_unsupported"
TRANS_KEY_OPTION_UPDATE_FAILED = "option_update_failed"
TRANS_KEY_DISABLE_PROFILE_FAILED = "disable_profile_failed"
TRANS_KEY_ENABLE_PROFILE_FAILED = "enable_profile_failed"
TRANS_KEY_ENABLE_FILTER_FAILED = "enable_filter_failed"
TRANS_KEY_DISABLE_FILTER_FAILED = "disable_filter_failed"
TRANS_KEY_ENABLE_RULE_FAILED = "enable_rule_failed"
TRANS_KEY_DISABLE_RULE_FAILED = "disable_rule_failed"
TRANS_KEY_ENABLE_OPTION_FAILED = "enable_option_failed"
TRANS_KEY_DISABLE_OPTION_FAILED = "disable_option_failed"

PURPOSE_INSTANCE_ACTION = "purpose_instance_action"
PURPOSE_INSTANCE_STATUS = "purpose_instance_status"
PURPOSE_INSTANCE_SUMMARY = "purpose_instance_summary"
PURPOSE_ENDPOINT_STATUS = "purpose_endpoint_status"
PURPOSE_PROFILE_PAUSE = "purpose_profile_pause"
PURPOSE_PROFILE_FILTER = "purpose_profile_filter"
PURPOSE_PROFILE_FILTER_MODE = "purpose_profile_filter_mode"
PURPOSE_PROFILE_SERVICE = "purpose_profile_service"
PURPOSE_PROFILE_DEFAULT_RULE = "purpose_profile_default_rule"
PURPOSE_PROFILE_RULE_GROUP = "purpose_profile_rule_group"
PURPOSE_PROFILE_OPTION = "purpose_profile_option"
PURPOSE_PROFILE_RULE = "purpose_profile_rule"

RULE_ACTION_BLOCK = "block"
RULE_ACTION_BYPASS = "bypass"
RULE_ACTION_REDIRECT = "redirect"
RULE_ACTION_OFF = "off"
