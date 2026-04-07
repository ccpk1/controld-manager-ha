"""Config flow tests for Control D Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.config_flow import ControlDManagerOptionsFlow
from custom_components.controld_manager.const import CONF_API_TOKEN, DOMAIN
from custom_components.controld_manager.models import ControlDUser


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
