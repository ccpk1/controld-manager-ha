"""End-to-end test for the Control D profile id translation.

The unit tests stub the device manager, so they prove the translation logic but
not that it is wired to the real one. This test sets up the integration for real,
lets it create the Profile devices, then calls the tool through the registered
LLM API and lets the **real** service resolve the target.

That is the closest thing to the live check that can run without an MCP client,
and it fails with the exact production error ("Device ... is not a Control D
target") if the translation is missing or wrong.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_READ_ONLY,
)

from .test_phase4 import _async_setup_entry, _inventory

_PROFILE_PK = "profile-1"
_PREDICATE = (
    "custom_components.controld_manager.helpers.llm_support.llm_tools_supported"
)


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def _setup(hass: HomeAssistant) -> tuple[MockConfigEntry, list[llm.Tool]]:
    """Set up a real entry at the Read only tier and return its tools."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Control D",
        data={CONF_API_TOKEN: "token-value"},
        options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_READ_ONLY},
        unique_id="user-123",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", _PROFILE_PK))
    with patch(_PREDICATE, return_value=True):
        api = await llm.async_get_api(
            hass, f"{DOMAIN}-{entry.entry_id}", _llm_context()
        )
    return entry, list(api.tools)


async def test_get_catalog_reaches_the_real_service_with_a_profile_pk(
    hass: HomeAssistant,
) -> None:
    """A tool call with a Control D PK resolves through the real service.

    This is the live failure replayed as a test: before the translation, the
    service looked the PK up in the device registry and raised.
    """
    entry, tools = await _setup(hass)
    (catalog_tool,) = [tool for tool in tools if tool.name == f"{DOMAIN}__get_catalog"]

    result = await catalog_tool.async_call(
        hass,
        llm.ToolInput(
            tool_name=catalog_tool.name,
            tool_args={"catalog_type": "filters", "profile_id": _PROFILE_PK},
        ),
        _llm_context(),
    )

    payload: Any = result.data["result"]
    assert result.error is not True
    # The real service resolved the profile, so the catalog is scoped to it.
    assert [row["profile_id"] for row in payload["profiles"]] == [_PROFILE_PK]
    assert payload["catalog_type"] == "filters"
    assert entry.entry_id == payload["config_entry_id"]


async def test_get_inventory_passes_the_profile_pk_through_to_the_real_service(
    hass: HomeAssistant,
) -> None:
    """get_inventory's service filters on the PK, so the tool must not translate."""
    _entry, tools = await _setup(hass)
    (inventory_tool,) = [
        tool for tool in tools if tool.name == f"{DOMAIN}__get_inventory"
    ]

    result = await inventory_tool.async_call(
        hass,
        llm.ToolInput(
            tool_name=inventory_tool.name,
            tool_args={"detail": "summary", "profile_id": _PROFILE_PK},
        ),
        _llm_context(),
    )

    payload: Any = result.data["result"]
    assert result.error is not True
    assert [row["profile_id"] for row in payload["profiles"]] == [_PROFILE_PK]


async def test_an_unrecognised_profile_id_reaches_the_service_unchanged(
    hass: HomeAssistant,
) -> None:
    """An id the map does not know is passed through, not dropped.

    Pass-through is required, not merely tolerated: the translation must never
    quietly discard a scope. An unrecognised value has to reach the service so it
    can report the problem, which is exactly what a missing or stale id should do.

    This also keeps the fix backward compatible — a caller that still passes a
    Home Assistant device id is resolved by the service as before.
    """
    entry, tools = await _setup(hass)
    (catalog_tool,) = [tool for tool in tools if tool.name == f"{DOMAIN}__get_catalog"]
    runtime = entry.runtime_data
    device_id = runtime.managers.device.profile_device_ids[_PROFILE_PK]

    # A device id is not a key in the map, so it is forwarded verbatim and the
    # service accepts it.
    result = await catalog_tool.async_call(
        hass,
        llm.ToolInput(
            tool_name=catalog_tool.name,
            tool_args={"catalog_type": "filters", "profile_id": device_id},
        ),
        _llm_context(),
    )

    assert result.error is not True
    assert [row["profile_id"] for row in result.data["result"]["profiles"]] == [
        _PROFILE_PK
    ]

    # A value that is neither is forwarded too, and the service reports it.
    with pytest.raises(Exception) as err:
        await catalog_tool.async_call(
            hass,
            llm.ToolInput(
                tool_name=catalog_tool.name,
                tool_args={"catalog_type": "filters", "profile_id": "not-an-id"},
            ),
            _llm_context(),
        )

    assert "not a Control D target" in str(err.value)
