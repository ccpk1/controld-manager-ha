"""Tests for the admin requirement on write services.

Changing Control D policy is an administrative action, so every write service is
registered as admin-only. Home Assistant's admin handler only applies the check
when the call carries a user, which is what keeps automations and scripts working
while blocking a non-admin user or a non-admin assistant request.

The write payloads below are schema-valid but deliberately unresolvable. A
non-admin call must therefore fail on authorization, before any target is
resolved.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    DOMAIN,
    LLM_TOOL_MODE_READ_AND_CONTROL,
)

from .test_llm_contract import _tools
from .test_phase4 import _async_setup_entry, _inventory

_WRITE_PAYLOADS: dict[str, dict[str, Any]] = {
    "clear_client_alias": {"endpoint_mac": "AA:BB"},
    "create_rule": {"hostname": "example.com"},
    "delete_rule": {"rule_identity": "example.com"},
    "disable_profile": {},
    "enable_profile": {},
    "rename_endpoint": {"endpoint_id": "missing", "new_name": "Renamed"},
    "set_client_alias": {"endpoint_mac": "AA:BB", "alias": "Phone"},
    "set_default_rule_state": {"mode": "Blocking"},
    "set_endpoint_analytics_logging": {"endpoint_id": "missing", "mode": "None"},
    "set_filter_state": {"filter_id": "missing", "enabled": True},
    "set_option_state": {"option_id": "missing", "enabled": True},
    "set_rule_state": {"rule_identity": "example.com"},
    "set_service_state": {"service_id": "missing", "mode": "Blocked"},
}

_READ_PAYLOADS: dict[str, dict[str, Any]] = {
    "get_account_overview": {},
    "get_inventory": {},
    "get_catalog": {"catalog_type": "filters"},
}


async def _setup(hass: HomeAssistant) -> None:
    """Set up one entry so the services are registered."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        unique_id="user-123",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))


async def _non_admin_id(hass: HomeAssistant) -> str:
    """Create an owner plus a plain user and return the plain user's id.

    Home Assistant makes the first user the owner, and the owner is an admin, so
    the admin account has to exist before the non-admin one.
    """
    await hass.auth.async_create_user("Owner", group_ids=[GROUP_ID_ADMIN])
    user = await hass.auth.async_create_user("Bob", group_ids=[GROUP_ID_USER])
    return user.id


@pytest.mark.parametrize(
    ("service", "payload"),
    list(_WRITE_PAYLOADS.items()),
    ids=list(_WRITE_PAYLOADS),
)
async def test_a_non_admin_user_cannot_call_a_write_service(
    hass: HomeAssistant, service: str, payload: dict[str, Any]
) -> None:
    """Every write service rejects a non-admin user."""
    user_id = await _non_admin_id(hass)
    await _setup(hass)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            payload,
            blocking=True,
            context=Context(user_id=user_id),
        )


@pytest.mark.parametrize(
    ("service", "payload"),
    list(_WRITE_PAYLOADS.items()),
    ids=list(_WRITE_PAYLOADS),
)
async def test_a_write_service_allows_an_admin_user(
    hass: HomeAssistant, service: str, payload: dict[str, Any]
) -> None:
    """An admin user gets past the gate and into the handler.

    The payload is unresolvable, so the handler reports a target problem. That
    failure is the evidence the call was authorized.
    """
    await _setup(hass)
    user = await hass.auth.async_create_user("Alice", group_ids=[GROUP_ID_ADMIN])

    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            payload,
            blocking=True,
            context=Context(user_id=user.id),
        )

    assert not isinstance(err.value, Unauthorized)


@pytest.mark.parametrize(
    ("service", "payload"),
    list(_WRITE_PAYLOADS.items()),
    ids=list(_WRITE_PAYLOADS),
)
async def test_a_write_service_allows_a_call_without_a_user(
    hass: HomeAssistant, service: str, payload: dict[str, Any]
) -> None:
    """Automations and scripts carry no user, so the gate must not apply."""
    await _setup(hass)

    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            payload,
            blocking=True,
            context=Context(),
        )

    assert not isinstance(err.value, Unauthorized)


@pytest.mark.parametrize(
    ("service", "payload"),
    list(_READ_PAYLOADS.items()),
    ids=list(_READ_PAYLOADS),
)
async def test_a_non_admin_user_can_call_a_read_service(
    hass: HomeAssistant, service: str, payload: dict[str, Any]
) -> None:
    """Read services stay reachable for a non-admin user, including a non-admin
    assistant request made on that user's behalf."""
    user_id = await _non_admin_id(hass)
    await _setup(hass)

    response = await hass.services.async_call(
        DOMAIN,
        service,
        payload,
        blocking=True,
        return_response=True,
        context=Context(user_id=user_id),
    )

    assert response is not None


async def test_an_assistant_write_reports_the_rejection_as_a_failure(
    hass: HomeAssistant,
) -> None:
    """A non-admin assistant gets a failed action result, not a raised error.

    The tool layer catches ``HomeAssistantError``, and ``Unauthorized`` is one,
    so the model is told the write failed instead of the request blowing up.
    """
    tools = await _tools(hass, LLM_TOOL_MODE_READ_AND_CONTROL)
    (disable,) = [tool for tool in tools if tool.name == f"{DOMAIN}__disable_profile"]
    user_id = await _non_admin_id(hass)
    context = llm.LLMContext(
        platform="test",
        context=Context(user_id=user_id),
        language="en",
        assistant="conversation",
        device_id=None,
    )

    result = await disable.async_call(
        hass,
        llm.ToolInput(tool_name=disable.name, tool_args={}),
        context,
    )

    assert result.error is True
    assert result.data["status"] == "failed"
    assert result.data["changed"] is False
    assert result.data["undo"] is None
