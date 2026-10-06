"""Contract tests for every registered LLM tool.

These assert the shared spec in ``docs/MCP_TOOL_REFERENCE.md`` against the tools
as they are actually registered, so the surface cannot drift from its contract.
"""

from __future__ import annotations

import json
import re
from typing import Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_FULL,
    LLM_TOOL_MODE_OFF,
    LLM_TOOL_MODE_READ_AND_CONTROL,
    LLM_TOOL_MODE_READ_ONLY,
    LLM_TOOL_MODE_SUMMARY_ONLY,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
)

_FIRST_REFRESH: Final = (
    "custom_components.controld_manager.coordinator."
    "ControlDManagerDataUpdateCoordinator.async_config_entry_first_refresh"
)
_PREDICATE: Final = (
    "custom_components.controld_manager.helpers.llm_support.llm_tools_supported"
)

# The read surface delivered by Phase 2. Control tools land in Phase 3.
_READ_TOOLS: Final = frozenset(
    {
        "get_account_overview",
        "get_inventory",
        "get_activity_log",
        "test_domain",
        "get_catalog",
    }
)

# Reversible controls, plus the non-idempotent rule create.
_CONTROL_TOOLS: Final = frozenset(
    {
        "set_filter_state",
        "set_service_state",
        "delete_service",
        "set_option_state",
        "set_rule_state",
        "set_default_rule_state",
        "enable_profile",
        "disable_profile",
        "rename_endpoint",
        "create_endpoint",
        "set_endpoint_profile",
        "set_endpoint_description",
        "set_endpoint_analytics_logging",
        "set_client_alias",
        "clear_client_alias",
        "create_rule",
    }
)

# Irreversible and bulk actions, registered only in the Full tier.
_DESTRUCTIVE_TOOLS: Final = frozenset(
    {"delete_rule", "delete_client", "delete_endpoint"}
)


def _enum_field_descriptions(schema: object) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Return {field: (description, allowed_values)} for each enumerated field.

    Enumerations live in the schema *values*, while the field name and its
    description live on the *keys*, so both sides are read. `vol.All` wrappers are
    unwrapped to reach a nested `vol.In`.
    """
    found: dict[str, tuple[str, tuple[str, ...]]] = {}

    def collect(validators: object) -> tuple[str, ...]:
        for validator in validators if isinstance(validators, tuple) else (validators,):
            container = getattr(validator, "container", None)
            if isinstance(container, tuple | frozenset) and all(
                isinstance(value, str) for value in container
            ):
                return tuple(container)
        return ()

    for key, value in getattr(schema, "schema", {}).items():
        allowed = getattr(value, "container", None)
        if not (
            isinstance(allowed, tuple | frozenset)
            and all(isinstance(item, str) for item in allowed)
        ):
            allowed = collect(getattr(value, "validators", ()))
        if not allowed:
            continue
        name = str(getattr(key, "schema", key))
        found[name] = (getattr(key, "description", "") or "", tuple(allowed))
    return found


async def test_enum_values_are_stated_exactly_in_their_descriptions(
    hass: HomeAssistant,
) -> None:
    """Every allowed value must appear verbatim in that field's description.

    A description that paraphrases its enum sends the model to a value the schema
    rejects. This bit both the default-rule and service tools live: the
    descriptions said "blocking"/"blocked" while the schemas required
    "Blocking"/"Blocked", so the first attempt always failed.
    """
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    problems: list[str] = []
    checked = 0

    for tool in tools:
        for field, (description, allowed) in _enum_field_descriptions(
            tool.parameters
        ).items():
            checked += 1
            for value in allowed:
                # Word-boundary matching, so a value is found whether or not it
                # is quoted, while "block" is still not satisfied by "blocked"
                # and a case change is still caught.
                if not re.search(rf"\b{re.escape(value)}\b", description):
                    problems.append(
                        f"{tool.name}.{field}: {value!r} not stated in description"
                    )

    # Guard against a vacuous pass: if the extraction stops finding enums this
    # test would silently check nothing.
    assert checked >= 10, f"only {checked} enumerated fields found"
    assert problems == [], "enum values missing from descriptions: " + "; ".join(
        problems
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


async def _tools(hass: HomeAssistant, mode: str) -> list[llm.Tool]:
    """Register one entry at the given tier and return its tools."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Control D",
        data={CONF_API_TOKEN: "token-value"},
        options={CONF_LLM_TOOL_MODE: mode},
        unique_id="user-123",
    )
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
    return list(api_instance.tools)


@pytest.fixture(name="read_tools")
async def read_tools_fixture(hass: HomeAssistant) -> list[llm.Tool]:
    """Return the tools registered at the read tier."""
    return await _tools(hass, LLM_TOOL_MODE_READ_ONLY)


async def test_read_tier_registers_exactly_the_read_surface(
    read_tools: list[llm.Tool],
) -> None:
    """The read tier exposes the Phase 2 tools and nothing else."""
    assert {tool.name for tool in read_tools} == {
        f"{DOMAIN}__{name}" for name in _READ_TOOLS
    }


async def test_every_tool_name_is_namespaced(read_tools: list[llm.Tool]) -> None:
    """Tool names carry the integration prefix so merged APIs stay unambiguous."""
    for tool in read_tools:
        assert tool.name.startswith(f"{DOMAIN}__"), tool.name


async def test_every_tool_declares_its_integration(read_tools: list[llm.Tool]) -> None:
    """A tool without `integration` is deprecated by Home Assistant."""
    for tool in read_tools:
        assert tool.integration == DOMAIN, tool.name


async def test_every_tool_has_a_title_and_description(
    read_tools: list[llm.Tool],
) -> None:
    """Both are served to clients; an empty one leaves the model guessing."""
    for tool in read_tools:
        assert tool.title, tool.name
        assert tool.description, tool.name
        assert len(tool.description) > 80, tool.name


async def test_read_tools_declare_all_four_annotations(
    read_tools: list[llm.Tool],
) -> None:
    """Annotation defaults are the least safe case, so reads must be explicit."""
    for tool in read_tools:
        annotations = tool.annotations
        assert annotations is not None, tool.name
        assert annotations.read_only is True, tool.name
        assert annotations.destructive is False, tool.name
        assert annotations.idempotent is True, tool.name
        assert annotations.open_world is True, tool.name


async def test_control_tool_annotations_are_accurate(hass: HomeAssistant) -> None:
    """Only the deletes are destructive, and only the creates and deletes
    are not idempotent."""
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    by_name = {tool.name: tool for tool in tools}

    for name in _CONTROL_TOOLS | _DESTRUCTIVE_TOOLS:
        annotations = by_name[f"{DOMAIN}__{name}"].annotations
        assert annotations is not None, name
        assert annotations.read_only is False, name
        assert annotations.open_world is True, name

    # A repeat of create_rule has an effect, so it must not claim idempotency.
    assert by_name[f"{DOMAIN}__create_rule"].annotations.idempotent is False
    # Every irreversible delete declares itself destructive, and nothing else does.
    for name in _DESTRUCTIVE_TOOLS:
        assert by_name[f"{DOMAIN}__{name}"].annotations.destructive is True, name
        assert by_name[f"{DOMAIN}__{name}"].annotations.idempotent is False, name
    for name in _CONTROL_TOOLS:
        assert by_name[f"{DOMAIN}__{name}"].annotations.destructive is False, name


async def test_no_tool_claims_a_closed_world(hass: HomeAssistant) -> None:
    """Every tool calls the Control D cloud API, so none is closed-world.

    Home Assistant's own platform tools are all `open_world=False` because they
    act on local state, and its default is `True`, so this guards both a copied
    local-state pattern and a newly added annotation set.
    """
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    for tool in tools:
        assert tool.annotations.open_world is True, tool.name


async def test_delete_service_is_not_a_destructive_tool(hass: HomeAssistant) -> None:
    """Removing a service is reversible, so it must not claim destructiveness.

    The row is removed, but configuring the service again restores it, and the
    tool names that call as its undo. It therefore belongs at the control tier
    alongside the other reversible tools, not behind the destructive gate.
    """
    tools = await _tools(hass, LLM_TOOL_MODE_READ_AND_CONTROL)
    by_name = {tool.name: tool for tool in tools}
    tool = by_name[f"{DOMAIN}__delete_service"]

    assert tool.annotations.destructive is False
    assert tool.annotations.read_only is False
    assert tool.annotations.idempotent is True


async def test_irreversible_tools_never_claim_an_undo(
    hass: HomeAssistant,
) -> None:
    """Tools that cannot be reversed must not name an undo call."""
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    by_name = {tool.name: tool for tool in tools}
    # Deletion destroys the rule's identity; the endpoint summary carries no
    # current logging level to restore; a deleted client row and its history
    # cannot be recovered.
    assert by_name[f"{DOMAIN}__delete_rule"]._undo(hass, {}) is None
    assert by_name[f"{DOMAIN}__delete_client"]._undo(hass, {"client_id": "c-1"}) is None
    assert (
        by_name[f"{DOMAIN}__delete_endpoint"]._undo(hass, {"endpoint_id": "ep-1"})
        is None
    )
    assert (
        by_name[f"{DOMAIN}__set_endpoint_analytics_logging"]._undo(
            hass, {"endpoint_id": "ep-1", "mode": "Full"}
        )
        is None
    )


async def test_create_rule_names_delete_as_its_undo(hass: HomeAssistant) -> None:
    """create_rule is reversible only by deleting, and says so."""
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    (create,) = [tool for tool in tools if tool.name == f"{DOMAIN}__create_rule"]
    undo = create._undo(hass, {"hostname": "example.com", "profile_id": "p-1"})
    assert undo is not None
    assert any(f"{DOMAIN}__delete_rule" in call for call in undo)


async def test_a_service_failure_becomes_a_failed_action_result(
    hass: HomeAssistant,
) -> None:
    """A rejected write returns status=failed with error set, not an exception."""
    tools = await _tools(hass, LLM_TOOL_MODE_READ_AND_CONTROL)
    (disable,) = [tool for tool in tools if tool.name == f"{DOMAIN}__disable_profile"]

    fake_hass = MagicMock()
    fake_hass.services.async_call = AsyncMock(side_effect=HomeAssistantError("nope"))
    result = await disable.async_call(
        fake_hass,
        llm.ToolInput(tool_name=disable.name, tool_args={"profile_id": "p-1"}),
        _llm_context(),
    )
    assert result.error is True
    assert result.data["status"] == "failed"
    assert result.data["changed"] is False
    assert result.data["target"] == {"profile_id": "p-1"}


async def test_every_parameter_is_described(read_tools: list[llm.Tool]) -> None:
    """Field guidance reaches the client through the schema marker description."""
    missing: list[str] = []
    for tool in read_tools:
        for marker in tool.parameters.schema:
            if not getattr(marker, "description", None):
                missing.append(f"{tool.name}:{marker.schema}")
    assert missing == [], f"parameters without a description: {missing}"


async def test_tools_never_expose_the_config_entry_selector(
    read_tools: list[llm.Tool],
) -> None:
    """The tool binds its own entry, so the model never picks an account."""
    for tool in read_tools:
        assert SERVICE_FIELD_CONFIG_ENTRY_ID not in tool.parameters.schema, tool.name


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        pytest.param(
            LLM_TOOL_MODE_SUMMARY_ONLY,
            {"get_account_overview"},
            id="summary",
        ),
        pytest.param(LLM_TOOL_MODE_READ_ONLY, _READ_TOOLS, id="read"),
        pytest.param(
            LLM_TOOL_MODE_READ_AND_CONTROL,
            _READ_TOOLS | _CONTROL_TOOLS,
            id="read_and_control",
        ),
        pytest.param(
            LLM_TOOL_MODE_FULL,
            _READ_TOOLS | _CONTROL_TOOLS | _DESTRUCTIVE_TOOLS,
            id="full",
        ),
    ],
)
async def test_each_tier_registers_exactly_its_surface(
    hass: HomeAssistant, mode: str, expected: frozenset[str]
) -> None:
    """A tier registers exactly its own tools — no more, and no fewer."""
    tools = await _tools(hass, mode)
    assert {tool.name for tool in tools} == {f"{DOMAIN}__{name}" for name in expected}


async def test_off_tier_exposes_no_api(hass: HomeAssistant) -> None:
    """The Off tier registers nothing at all."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Control D",
        data={CONF_API_TOKEN: "token-value"},
        options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_OFF},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)
    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not [
        api for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    ]


async def test_tool_result_envelope_is_json_serializable(
    hass: HomeAssistant, read_tools: list[llm.Tool]
) -> None:
    """MCP serves the envelope as JSON text, so it must serialize cleanly."""
    overview = next(
        tool for tool in read_tools if tool.name == f"{DOMAIN}__get_account_overview"
    )
    result = await overview.async_call(
        hass,
        llm.ToolInput(tool_name=overview.name, tool_args={}),
        _llm_context(),
    )
    assert json.dumps(result.data)


async def test_a_missing_required_argument_is_a_clean_error(
    hass: HomeAssistant, read_tools: list[llm.Tool]
) -> None:
    """An MCP client can call directly, so a bad call must not raise KeyError."""
    test_domain = next(
        tool for tool in read_tools if tool.name == f"{DOMAIN}__test_domain"
    )
    with pytest.raises(Exception) as err:
        await test_domain.async_call(
            hass,
            llm.ToolInput(tool_name=test_domain.name, tool_args={}),
            _llm_context(),
        )
    assert not isinstance(err.value, KeyError)


async def test_every_tool_declares_a_probatio_schema(hass: HomeAssistant) -> None:
    """Tool schemas must be probatio validators, not voluptuous ones.

    `llm.Tool.parameters` is annotated `probatio.Schema`, and probatio replaced
    voluptuous as the validation engine in Core 2026.10. Importing voluptuous
    still resolves at runtime because HA aliases it to probatio in `sys.modules`,
    so a wrong import is invisible until something type-checks it. This asserts
    the validator's own module rather than relying on that alias.

    A tool needing a cross-field rule composes `probatio.All(Schema(...), rule)`,
    which is not nominally a `Schema`, so requiring exactly that type would fail
    a correct tool. What matters is the origin, and that is also the thing the
    alias can hide.
    """
    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    assert tools

    wrong = {
        tool.name: type(tool.parameters).__module__
        for tool in tools
        if not type(tool.parameters).__module__.startswith("probatio")
    }
    assert wrong == {}, f"tools not using a probatio validator: {wrong}"


async def test_tool_schemas_still_convert_for_an_mcp_client(
    hass: HomeAssistant,
) -> None:
    """A probatio schema must survive the conversion an MCP client triggers.

    `mcp_server` builds each tool's published input schema with
    `probatio.to_openapi`, so a schema probatio cannot convert would break the
    MCP surface rather than just the type check.
    """
    import probatio

    tools = await _tools(hass, LLM_TOOL_MODE_FULL)
    for tool in tools:
        schema = probatio.to_openapi(tool.parameters, openapi_version="3.1.0")
        assert schema["type"] == "object", tool.name
        assert "properties" in schema, tool.name
