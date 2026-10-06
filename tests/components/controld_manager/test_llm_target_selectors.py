"""Tests for addressing a target by id or by name.

Every write tool that acts on an endpoint, and every read that can be scoped to
one, accepts either an id or a name. These pin the three things that makes true:
the name is resolved before the hooks read it, the overloaded `endpoint_name` on
`create_endpoint` is left alone, and a schema that offers both selectors still
insists on at least one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import probatio
import pytest
from homeassistant.core import Context
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import (
    CreateEndpointTool,
    DeleteEndpointTool,
    RenameEndpointTool,
    SetEndpointDescriptionTool,
)
from custom_components.controld_manager.services import (
    _resolve_read_endpoint_ids,
    _resolve_read_profile_ids,
)

_ENDPOINTS = {
    "ep-1": SimpleNamespace(device_id="ep-1", name="kadens-phone"),
    "ep-2": SimpleNamespace(device_id="ep-2", name="Firewalla-VLAN60"),
}


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


def _hass_with_endpoints(service_call: AsyncMock) -> MagicMock:
    """Return a hass whose entry exposes a resolvable endpoint inventory."""

    def resolve(
        *, endpoint_id: str | None = None, endpoint_name: str | None = None
    ) -> Any:
        if endpoint_id is not None:
            if endpoint_id not in _ENDPOINTS:
                raise ValueError("Unknown endpoint target for selector 'id'")
            return _ENDPOINTS[endpoint_id]
        matches = [e for e in _ENDPOINTS.values() if e.name == endpoint_name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError("Ambiguous endpoint target for selector 'name'")
        raise ValueError("Unknown endpoint target for selector 'name'")

    endpoint_manager = SimpleNamespace(resolve_endpoint_target=resolve)
    runtime = SimpleNamespace(managers=SimpleNamespace(endpoint=endpoint_manager))
    entry = SimpleNamespace(runtime_data=runtime)

    fake = MagicMock()
    fake.services.async_call = service_call
    fake.config_entries.async_get_entry.return_value = entry
    return fake


async def test_an_endpoint_name_is_resolved_to_its_id_before_the_write() -> None:
    """A caller holding only the device name can still address the endpoint.

    The service accepts either selector, but the tool's own hooks read
    `endpoint_id` against the registry, so the name has to become an id first or
    the pre-check and the undo would both come up empty.
    """
    service_call = AsyncMock()
    tool = RenameEndpointTool(entry_id="e-1")

    result = await tool.async_call(
        _hass_with_endpoints(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"endpoint_name": "kadens-phone", "new_name": "Kadens"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    # The service is handed the id, and the caller is told which one it was.
    assert service_call.await_args.args[2]["endpoint_id"] == "ep-1"
    assert result.data["target"]["id"] == "ep-1"


async def test_an_unknown_endpoint_name_fails_as_an_action_result() -> None:
    """A name that matches nothing is reported, not raised past the caller."""
    service_call = AsyncMock()
    tool = DeleteEndpointTool(entry_id="e-1")

    result = await tool.async_call(
        _hass_with_endpoints(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"endpoint_name": "no-such-device"},
        ),
        _llm_context(),
    )

    assert result.error is True
    assert result.data["status"] == "failed"
    assert "selector 'name'" in result.data["error"]
    service_call.assert_not_called()


async def test_an_ambiguous_endpoint_name_is_refused() -> None:
    """Names are not unique, so a collision must not pick one arbitrarily."""
    endpoint_manager = SimpleNamespace(
        resolve_endpoint_target=MagicMock(
            side_effect=ValueError("Ambiguous endpoint target for selector 'name'")
        )
    )
    runtime = SimpleNamespace(managers=SimpleNamespace(endpoint=endpoint_manager))
    fake = MagicMock()
    fake.services.async_call = AsyncMock()
    fake.config_entries.async_get_entry.return_value = SimpleNamespace(
        runtime_data=runtime
    )
    tool = SetEndpointDescriptionTool(entry_id="e-1")

    result = await tool.async_call(
        fake,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"endpoint_name": "watch", "description": "x"},
        ),
        _llm_context(),
    )

    assert result.error is True
    assert "Ambiguous" in result.data["error"]


async def test_create_endpoint_treats_endpoint_name_as_the_new_name() -> None:
    """The field is overloaded, so creation must not resolve it as a selector.

    `create_endpoint` takes `endpoint_name` as the name of the endpoint to
    create. Resolving that against the inventory would reject every creation,
    which is why the resolution is opt-in per tool.
    """
    service_call = AsyncMock()
    tool = CreateEndpointTool(entry_id="e-1")

    result = await tool.async_call(
        _hass_with_endpoints(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"endpoint_name": "brand-new", "profile_id": "profile-1"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    # The name is passed through untouched rather than treated as a selector.
    assert service_call.await_args.args[2]["endpoint_name"] == "brand-new"


@pytest.mark.parametrize(
    "tool_class",
    [
        RenameEndpointTool,
        DeleteEndpointTool,
        SetEndpointDescriptionTool,
    ],
)
def test_endpoint_selector_tools_require_a_target(
    tool_class: type[llm.Tool],
) -> None:
    """Offering two selectors must not make the target optional."""
    tool = tool_class(entry_id="e-1")

    with pytest.raises(probatio.Invalid):
        tool.parameters({})


def test_create_endpoint_does_not_require_a_selector() -> None:
    """Creation has no target to select, so the rule must not apply to it."""
    tool = CreateEndpointTool(entry_id="e-1")

    validated = tool.parameters({"endpoint_name": "new-one", "profile_id": "p-1"})
    assert validated["endpoint_name"] == "new-one"


def _entry(runtime: Any) -> Any:
    """Return a config entry stand-in carrying one runtime."""
    return SimpleNamespace(runtime_data=runtime)


def _call(**data: Any) -> Any:
    """Return a service call stand-in carrying the given data."""
    return SimpleNamespace(data=data)


def test_a_read_resolves_a_profile_name_to_its_pk() -> None:
    """A read accepted only a PK, so a name had to be looked up first."""
    runtime = SimpleNamespace(
        registry=SimpleNamespace(
            profiles={"pk-1": SimpleNamespace(profile_pk="pk-1", name="Kids")}
        ),
        managers=SimpleNamespace(device=SimpleNamespace(managed_profile_pks={"pk-1"})),
    )

    resolved = _resolve_read_profile_ids(_entry(runtime), _call(profile_name="Kids"))

    assert resolved == frozenset({"pk-1"})


def test_a_read_resolves_an_endpoint_name_to_its_id() -> None:
    """The same gap existed for endpoints, which had no name selector at all."""
    endpoint_manager = SimpleNamespace(
        resolve_endpoint_target=lambda *, endpoint_name: _ENDPOINTS["ep-1"]
    )
    runtime = SimpleNamespace(managers=SimpleNamespace(endpoint=endpoint_manager))

    resolved = _resolve_read_endpoint_ids(
        _entry(runtime), _call(endpoint_name="kadens-phone")
    )

    assert resolved == frozenset({"ep-1"})


def test_an_explicit_id_wins_over_a_name_on_a_read() -> None:
    """Ids are exact, so a co-supplied name must not widen or replace them."""
    endpoint_manager = SimpleNamespace(
        resolve_endpoint_target=MagicMock(
            side_effect=AssertionError("name must not be resolved when an id is given")
        )
    )
    runtime = SimpleNamespace(managers=SimpleNamespace(endpoint=endpoint_manager))

    resolved = _resolve_read_endpoint_ids(
        _entry(runtime), _call(endpoint_id="ep-2", endpoint_name="kadens-phone")
    )

    assert resolved == frozenset({"ep-2"})


def test_a_read_with_no_selectors_is_unscoped() -> None:
    """Omitting both selectors keeps reading every profile, as before."""
    runtime = SimpleNamespace(managers=SimpleNamespace(endpoint=SimpleNamespace()))

    assert _resolve_read_endpoint_ids(_entry(runtime), _call()) == frozenset()
