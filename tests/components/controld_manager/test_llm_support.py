"""Tests for the LLM/MCP tool surface foundation (Phase 1)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DEFAULT_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_OFF,
    LLM_TOOL_MODE_READ_ONLY,
    MIN_LLM_TOOLS_HA_VERSION,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
)
from custom_components.controld_manager.helpers.llm_support import llm_tools_supported
from custom_components.controld_manager.llm_api import _resolve_api_name
from custom_components.controld_manager.models import ControlDOptions

# Modules that are guard-loaded (imported only when LLM tools are supported) and
# are therefore allowed to import Core 2026.10-only LLM names at module level.
_GUARD_LOADED_MODULES: Final = frozenset(
    {
        "llm_api.py",
        "llm_tools_common.py",
        "llm_tools_read.py",
        "llm_tools_control.py",
    }
)
_FORBIDDEN_MODULES: Final = frozenset({"probatio", "homeassistant.helpers.llm"})
_PACKAGE_ROOT: Final = (
    Path(__file__).resolve().parents[3] / "custom_components" / "controld_manager"
)

_FIRST_REFRESH: Final = (
    "custom_components.controld_manager.coordinator."
    "ControlDManagerDataUpdateCoordinator.async_config_entry_first_refresh"
)
# ``const.py`` holds only the version tuple; the predicate lives in helpers
# because it needs ``homeassistant.const``. Patch the definition there.
_PREDICATE: Final = (
    "custom_components.controld_manager.helpers.llm_support.llm_tools_supported"
)


@pytest.mark.parametrize(
    ("major", "minor", "expected"),
    [
        pytest.param(
            MIN_LLM_TOOLS_HA_VERSION[0],
            MIN_LLM_TOOLS_HA_VERSION[1] - 1,
            False,
            id="just_below",
        ),
        pytest.param(*MIN_LLM_TOOLS_HA_VERSION, True, id="at_boundary"),
        pytest.param(
            MIN_LLM_TOOLS_HA_VERSION[0],
            MIN_LLM_TOOLS_HA_VERSION[1] + 1,
            True,
            id="just_above",
        ),
    ],
)
def test_llm_tools_supported_boundaries(major: int, minor: int, expected: bool) -> None:
    """The version predicate compares the integration's bound version tuple."""
    with (
        patch(
            "custom_components.controld_manager.helpers.llm_support.MAJOR_VERSION",
            major,
        ),
        patch(
            "custom_components.controld_manager.helpers.llm_support.MINOR_VERSION",
            minor,
        ),
    ):
        assert llm_tools_supported() is expected


def test_no_guard_loaded_module_is_imported_eagerly() -> None:
    """Unconditionally loaded modules must not import Core 2026.10-only names.

    A module-level ``import probatio`` or ``from homeassistant.helpers.llm ...``
    is an ``ImportError`` at load time on older Core that a latest-only test run
    never surfaces. This is the highest-value guard test.
    """
    offenders: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if path.name in _GUARD_LOADED_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module} if node.module is not None else set()
            else:
                continue
            for name in names:
                if name in _FORBIDDEN_MODULES:
                    offenders.append(f"{path.relative_to(_PACKAGE_ROOT)}: {name}")

    assert offenders == [], f"eager LLM-only imports found: {offenders}"


def _entry(
    *, options: dict[str, object] | None = None, title: str = "Control D"
) -> MockConfigEntry:
    """Return a Control D config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_API_TOKEN: "token-value"},
        options=options or {},
        unique_id="user-123",
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


def _api_ids(hass: HomeAssistant) -> set[str]:
    """Return the registered Control D API ids."""
    return {
        api.id for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    }


async def test_setup_registers_api_when_supported(hass: HomeAssistant) -> None:
    """Setup registers an owned API with a per-entry id."""
    entry = _entry()
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _api_ids(hass) == {f"{DOMAIN}-{entry.entry_id}"}
    # The id is never the bare domain, so it cannot move when another entry is
    # added later.
    assert DOMAIN not in _api_ids(hass)


async def test_setup_registers_no_api_on_older_core(hass: HomeAssistant) -> None:
    """On unsupported Core, setup succeeds and registers no LLM API."""
    entry = _entry()
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=False),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _api_ids(hass) == set()


async def test_api_instance_is_served_with_the_prompt(hass: HomeAssistant) -> None:
    """The registered API serves the shared prompt and the overview tool."""
    entry = _entry()
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(
            hass, f"{DOMAIN}-{entry.entry_id}", _llm_context()
        )

    assert api_instance.api_prompt
    assert "Control D" in api_instance.api_prompt
    # Summary is the default tier, and it registers the overview only.
    assert {tool.name for tool in api_instance.tools} == {
        f"{DOMAIN}__get_account_overview"
    }


async def test_read_tier_adds_the_inventory_tool(hass: HomeAssistant) -> None:
    """Read tiers add the read set; Summary does not."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_READ_ONLY})
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(
            hass, f"{DOMAIN}-{entry.entry_id}", _llm_context()
        )

    assert {tool.name for tool in api_instance.tools} == {
        f"{DOMAIN}__get_account_overview",
        f"{DOMAIN}__get_inventory",
        f"{DOMAIN}__get_activity_log",
        f"{DOMAIN}__test_domain",
        f"{DOMAIN}__get_catalog",
    }


async def test_off_tier_registers_no_api(hass: HomeAssistant) -> None:
    """The Off tier registers nothing at all, not an empty API."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_OFF})
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _api_ids(hass) == set()


async def test_overview_tool_contract(hass: HomeAssistant) -> None:
    """The overview tool declares its contract and injects its own entry."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_READ_ONLY})
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(
            hass, f"{DOMAIN}-{entry.entry_id}", _llm_context()
        )

    tools = {tool.name: tool for tool in api_instance.tools}
    tool = tools[f"{DOMAIN}__get_account_overview"]
    assert tool.integration == DOMAIN
    assert tool.annotations.read_only is True
    assert tool.annotations.destructive is False
    assert tool.annotations.idempotent is True
    assert tool.annotations.open_world is True
    assert tool.title
    # The model must never have to pick an account; the tool supplies the entry.
    assert SERVICE_FIELD_CONFIG_ENTRY_ID not in tool.parameters.schema
    assert not tool.parameters.schema


async def test_api_is_unregistered_on_entry_unload(hass: HomeAssistant) -> None:
    """Unloading the entry removes the registered LLM API."""
    entry = _entry()
    entry.add_to_hass(hass)

    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert _api_ids(hass)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert _api_ids(hass) == set()


@pytest.mark.parametrize(
    ("titles", "expected"),
    [
        pytest.param(["Control D"], "Control D", id="sole_entry_uses_title"),
        pytest.param(
            ["Control D", "Control D"],
            "Control D [00ab12]",
            id="duplicate_title_is_disambiguated",
        ),
    ],
)
def test_api_name_is_unique_across_entries(
    hass: HomeAssistant, titles: list[str], expected: str
) -> None:
    """Duplicate entry titles get a stable, entry-scoped display name."""
    entries: list[MockConfigEntry] = []
    for index, title in enumerate(titles):
        entry = MockConfigEntry(
            domain=DOMAIN, title=title, entry_id=f"00ab12{index:02d}"
        )
        entry.add_to_hass(hass)
        entries.append(entry)

    resolved = _resolve_api_name(hass, entries[-1])
    assert resolved == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        pytest.param(None, DEFAULT_LLM_TOOL_MODE, id="missing_defaults_to_summary"),
        pytest.param("off", LLM_TOOL_MODE_OFF, id="off_is_kept"),
        pytest.param("bogus", DEFAULT_LLM_TOOL_MODE, id="unknown_falls_back"),
        pytest.param(7, DEFAULT_LLM_TOOL_MODE, id="non_string_falls_back"),
    ],
)
def test_options_normalize_llm_tool_mode(stored: object, expected: str) -> None:
    """The stored mode is validated against the supported tier set."""
    raw = {} if stored is None else {CONF_LLM_TOOL_MODE: stored}
    assert ControlDOptions.from_mapping(raw).llm_tool_mode == expected


def test_options_round_trip_llm_tool_mode() -> None:
    """The mode survives an options round-trip."""
    options = ControlDOptions.from_mapping(
        {CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_READ_ONLY}
    )
    restored = ControlDOptions.from_mapping(options.as_mapping())
    assert restored.llm_tool_mode == LLM_TOOL_MODE_READ_ONLY
