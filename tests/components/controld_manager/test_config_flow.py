"""Config flow tests for Control D Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from custom_components.controld_manager.config_flow import ControlDManagerOptionsFlow
from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    DOMAIN,
    TRANS_KEY_CANNOT_CONNECT,
    TRANS_KEY_INVALID_AUTH,
    TRANS_KEY_UNKNOWN,
)
from custom_components.controld_manager.models import ControlDUser


async def _submit_token_flow(
    hass,
    flow_kind: str,
    api_token: str,
):
    """Start and submit one token-based config-flow path."""
    if flow_kind == "user":
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: api_token}
        )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "old-token", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    if flow_kind == "reauth":
        result = await entry.start_reauth_flow(hass)
    else:
        result = await entry.start_reconfigure_flow(hass)

    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: api_token}
    )


async def test_user_flow_creates_entry(hass) -> None:
    """The user flow should create one entry for one authenticated instance."""
    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-123",
                account_pk="pk-1",
                display_name="Control D Home",
            )
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "token-value"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Control D"
    assert result["data"] == {
        CONF_API_TOKEN: "token-value",
        "entry_name": "Control D",
    }


async def test_user_flow_numbers_second_entry_title(hass) -> None:
    """The user flow should number later entries with the default title base."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "existing-token", "entry_name": "Control D"},
        unique_id="user-123",
        title="Control D",
    )
    existing_entry.add_to_hass(hass)

    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-456",
                account_pk="pk-2",
                display_name="ignored@example.com",
            )
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "token-two"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Control D 2"
    assert result["data"] == {
        CONF_API_TOKEN: "token-two",
        "entry_name": "Control D 2",
    }


async def test_user_flow_rejects_duplicate_instance(hass) -> None:
    """The config flow should prevent duplicate entries for the same instance."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "existing-token"},
        unique_id="user-123",
    )
    existing_entry.add_to_hass(hass)

    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-123",
                account_pk="pk-1",
                display_name="Control D Home",
            )
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "new-token"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("flow_kind", "raised_error", "expected_error", "expected_step_id"),
    [
        (
            "user",
            ControlDApiAuthError,
            TRANS_KEY_INVALID_AUTH,
            "user",
        ),
        (
            "user",
            ControlDApiConnectionError,
            TRANS_KEY_CANNOT_CONNECT,
            "user",
        ),
        (
            "user",
            ControlDApiResponseError,
            TRANS_KEY_UNKNOWN,
            "user",
        ),
        (
            "reauth",
            ControlDApiAuthError,
            TRANS_KEY_INVALID_AUTH,
            "reauth_confirm",
        ),
        (
            "reauth",
            ControlDApiConnectionError,
            TRANS_KEY_CANNOT_CONNECT,
            "reauth_confirm",
        ),
        (
            "reauth",
            ValueError,
            TRANS_KEY_UNKNOWN,
            "reauth_confirm",
        ),
        (
            "reconfigure",
            ControlDApiAuthError,
            TRANS_KEY_INVALID_AUTH,
            "reconfigure",
        ),
        (
            "reconfigure",
            ControlDApiConnectionError,
            TRANS_KEY_CANNOT_CONNECT,
            "reconfigure",
        ),
        (
            "reconfigure",
            ControlDApiResponseError,
            TRANS_KEY_UNKNOWN,
            "reconfigure",
        ),
    ],
)
async def test_token_flows_show_expected_errors(
    hass,
    flow_kind: str,
    raised_error: type[Exception],
    expected_error: str,
    expected_step_id: str,
) -> None:
    """Token-entry flows should surface specific translated error keys."""
    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(side_effect=raised_error),
    ):
        result = await _submit_token_flow(hass, flow_kind, "bad-token")

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == expected_step_id
    assert result["errors"] == {"base": expected_error}


async def test_options_flow_edit_profile_exposes_external_filters_and_hides_auto_enable(
    hass,
) -> None:
    """The profile form should show the external-filter toggle and hide auto-enable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    flow = ControlDManagerOptionsFlow(entry)
    flow.hass = hass
    flow._selected_profile_pk = "profile-1"

    with (
        patch.object(
            flow,
            "_async_get_profile_choices",
            new=AsyncMock(return_value={"profile-1": "Primary"}),
        ),
        patch.object(
            flow,
            "_async_get_service_category_choices",
            new=AsyncMock(return_value={"audio": "Audio"}),
        ),
        patch.object(
            flow,
            "_async_get_rule_target_choices",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await flow.async_step_edit_profile()

    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    field_names = [marker.schema for marker in schema.schema]
    assert field_names[0] == "managed_in_home_assistant"
    assert field_names[1] == "expose_external_filters"
    assert field_names[-2] == "endpoint_sensors_enabled"
    assert field_names[-1] == "endpoint_inactivity_threshold_minutes"
    assert "auto_enable_service_switches" not in field_names


async def test_reauth_flow_updates_api_token(hass) -> None:
    """The reauth flow should update the stored API token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "old-token", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-123",
                account_pk="pk-1",
                display_name="Control D Home",
            )
        ),
    ):
        result = await entry.start_reauth_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "new-token"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == "new-token"


async def test_reauth_flow_rejects_different_instance(hass) -> None:
    """The reauth flow should abort when the token belongs to another instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "old-token", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-999",
                account_pk="pk-9",
                display_name="Other Home",
            )
        ),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "other-token"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_reconfigure_flow_updates_api_token(hass) -> None:
    """The reconfigure flow should validate and update the stored API token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "old-token", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_instance_identity",
        new=AsyncMock(
            return_value=ControlDUser(
                instance_id="user-123",
                account_pk="pk-1",
                display_name="Control D Home",
            )
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "new-token"}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_TOKEN] == "new-token"


async def test_options_flow_integration_settings_only_exposes_active_poller(
    hass,
) -> None:
    """The integration settings form should only expose active polling controls."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )

    flow = ControlDManagerOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_integration_settings()

    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    field_names = [marker.schema for marker in schema.schema]
    assert field_names == ["configuration_sync_interval_minutes"]


@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (ControlDApiAuthError, TRANS_KEY_INVALID_AUTH),
        (ControlDApiConnectionError, TRANS_KEY_CANNOT_CONNECT),
        (ValueError, TRANS_KEY_UNKNOWN),
    ],
)
async def test_options_flow_select_profile_surfaces_lookup_errors(
    hass,
    raised_error: type[Exception],
    expected_error: str,
) -> None:
    """Profile selection should return a form-level error when lookup fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    flow = ControlDManagerOptionsFlow(entry)
    flow.hass = hass

    with patch.object(
        flow,
        "_async_get_profile_choices",
        new=AsyncMock(side_effect=raised_error),
    ):
        result = await flow.async_step_select_profile()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_profile"
    assert result["errors"] == {"base": expected_error}
