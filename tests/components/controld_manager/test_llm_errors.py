"""Error-path tests for the LLM tools.

An MCP client can call a tool directly, bypassing the provider's validation, so a
malformed call must produce a clean error rather than a bare ``KeyError``. These
tests drive each failure mode through the tool layer.
"""

from __future__ import annotations

from typing import Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_FULL,
    LLM_TOOL_MODE_READ_ONLY,
)
from custom_components.controld_manager.llm_tools_common import PROMPT
from custom_components.controld_manager.llm_tools_control import DisableProfileTool

_FIRST_REFRESH: Final = (
    "custom_components.controld_manager.coordinator."
    "ControlDManagerDataUpdateCoordinator.async_config_entry_first_refresh"
)
_PREDICATE: Final = (
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


async def _tools(hass: HomeAssistant, mode: str) -> dict[str, llm.Tool]:
    """Register one entry at the given tier and return its tools by name."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    return {tool.name: tool for tool in api_instance.tools}


@pytest.fixture(name="read_tools")
async def read_tools_fixture(hass: HomeAssistant) -> dict[str, llm.Tool]:
    """Return the read-tier tools by name."""
    return await _tools(hass, LLM_TOOL_MODE_READ_ONLY)


@pytest.fixture(name="control_tools")
async def control_tools_fixture(hass: HomeAssistant) -> dict[str, llm.Tool]:
    """Return the Full-tier tools by name."""
    return await _tools(hass, LLM_TOOL_MODE_FULL)


async def test_missing_required_argument_is_not_a_key_error(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """A required argument that is absent must fail as validation, not KeyError."""
    tool = read_tools[f"{DOMAIN}__test_domain"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_partially_missing_arguments_are_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """Supplying only part of the required set is still a clean failure."""
    tool = read_tools[f"{DOMAIN}__test_domain"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"endpoint_id": "ep-1"}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_unknown_argument_is_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """An argument the schema does not declare must not be silently accepted."""
    tool = read_tools[f"{DOMAIN}__get_account_overview"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"not_a_real_field": 1}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_invalid_enum_value_is_rejected(
    hass: HomeAssistant, control_tools: dict[str, llm.Tool]
) -> None:
    """An out-of-range enum value fails validation before any service call."""
    service_call = AsyncMock()
    tool = control_tools[f"{DOMAIN}__set_filter_state"]
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call

    with pytest.raises(Exception) as err:
        await tool.async_call(
            fake_hass,
            llm.ToolInput(
                tool_name=tool.name,
                tool_args={"filter_id": "ads", "enabled": "maybe"},
            ),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)
    service_call.assert_not_called()


async def test_an_out_of_range_page_size_is_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """A page size beyond the documented maximum fails rather than being sent."""
    tool = read_tools[f"{DOMAIN}__get_activity_log"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"page_size": 5000}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_a_service_failure_is_reported_as_failed(
    hass: HomeAssistant, control_tools: dict[str, llm.Tool]
) -> None:
    """A rejected write returns a failed action result instead of raising."""
    from homeassistant.exceptions import HomeAssistantError

    tool = control_tools[f"{DOMAIN}__disable_profile"]
    # Model an unreadable registry so the pre-check proceeds to the write.
    tool._registry = lambda _hass: None  # type: ignore[method-assign]
    fake_hass = MagicMock()
    fake_hass.services.async_call = AsyncMock(
        side_effect=HomeAssistantError("rejected")
    )

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": "p-1"}),
        _llm_context(),
    )

    assert result.error is True
    assert result.data["status"] == "failed"
    assert result.data["changed"] is False
    assert result.data["after"] is None
    # The reason must survive: without it a caller cannot tell a missing target
    # from a rejected value.
    assert result.data["error"] == "rejected"


async def test_a_successful_write_reports_no_error() -> None:
    """Only a failure carries an `error` reason."""
    service_call = AsyncMock()
    tool = DisableProfileTool(entry_id="e-1")
    tool._registry = lambda _hass: None  # type: ignore[method-assign]
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": "p-1"}),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["error"] is None


def test_prompt_covers_the_shipped_surface() -> None:
    """The prompt must describe the tools that actually exist.

    It is served on every request, so a stale prompt teaches the model about
    tools it cannot call. These are the concepts it must carry.
    """
    required = {
        "profile",
        "endpoint",
        "client",
        "default rule",
        "already_in_state",
        "undo",
        "33 day",
        "analytics logging",
        "triggerValue",
        "get_account_overview",
        "get_activity_log",
        "test_domain",
        "attacker",
        "bypassed",
        "redirected",
    }
    missing = {term for term in required if term.lower() not in PROMPT.lower()}
    assert missing == set(), f"prompt is missing: {sorted(missing)}"


def test_prompt_explains_the_default_rule_sets_the_profile_posture() -> None:
    """The default rule has to read as the profile's top-level control.

    It decides the query nothing else matched, so it changes what every other
    setting means: under `Bypassing` a query passes unless something blocks it,
    and under `Blocking` it is blocked unless something allows it. A model that
    treats the default rule as one setting among several will invert its answer
    about why something was or was not blocked.
    """
    lowered = PROMPT.lower()
    assert "default rule" in lowered
    assert "most important" in lowered

    # Both postures, each stated as how the unmatched query is handled.
    assert "passes unless" in lowered
    assert "blocked unless" in lowered

    # The wider control has to be named, or the posture reads as the ceiling.
    assert "disabling the profile reaches further" in lowered


def test_prompt_names_no_literal_escape_sequences() -> None:
    """A leaked escape reaches the model as text and corrupts the prompt.

    The model string is assembled from concatenated literals, so a doubled
    backslash in one fragment ships a literal `\\n` or `\\u2014` to the model
    instead of the character it was meant to be.
    """
    for leaked in ("\\n", "\\u", '\\"'):
        assert leaked not in PROMPT, f"prompt contains a literal {leaked!r}"


def test_prompt_explains_the_outcomes_are_not_degrees_of_one_thing() -> None:
    """Blocked, bypassed, redirected, and failed all have to be named.

    Bypassed is routine rather than a fault, and redirected relocates a lookup
    rather than refusing it. A model that treats them as grades of blocking
    misreports ordinary traffic.
    """
    lowered = PROMPT.lower()
    for outcome in ("blocked", "bypassed", "redirected", "failed"):
        assert outcome in lowered, outcome

    # Bypassed must be described as normal, not as a problem.
    bypassed_line = next(
        line for line in PROMPT.splitlines() if line.startswith("- **bypassed**")
    )
    assert "allowed" in bypassed_line.lower()
    assert "routine" in bypassed_line.lower()


def test_prompt_bridges_disable_to_the_paused_field() -> None:
    """The model says `disabled`; the overview returns `paused`.

    `get_account_overview` reports the state as `paused`, while the vocabulary,
    the entity naming, and the vendor's own interface all use `disable`. Without
    the field named, an agent reading `paused: true` has to guess that it is the
    disabled profile the model describes, and the profile-pause question in #21
    stays unanswered.
    """
    lowered = PROMPT.lower()
    assert "paused" in lowered
    assert "`paused`" in PROMPT
    assert "get_account_overview" in PROMPT
    assert "disable_profile" in PROMPT
    assert "enable_profile" in PROMPT

    # A disable is time-bound, so the model must not let an agent describe one
    # as permanent.
    assert "always temporary" in lowered
    assert "never permanent" in lowered
    assert "re-enables itself" in lowered


def test_prompt_explains_two_profiles_are_merged_not_ordered() -> None:
    """Two enforced profiles pool their rules rather than applying in turn.

    The merge is what makes a shared baseline plus a device-specific policy
    work, and it is why "which profile did this?" can have two answers. A model
    that assumes an order will name one profile and miss the other.
    """
    lowered = PROMPT.lower()
    assert "merged before matching" in lowered
    assert "applied in order" in lowered
    # Each profile keeps its own posture, so the merge is not a default-rule
    # override.
    assert "each keeps its own default rule" in lowered
    # The reporting consequence has to be stated, not just the mechanism.
    assert "name every enforced profile" in lowered
    # A client inherits both, since it follows what its endpoint enforces.
    assert "follows the profiles its endpoint enforces" in lowered


def test_prompt_does_not_describe_removed_tools() -> None:
    """The ranked analytics tools were dropped, so the prompt must not imply them."""
    for removed in (
        "get_block_breakdown",
        "get_top_blocked_domains",
        "get_block_summary",
        "get_policy",
    ):
        assert removed not in PROMPT


def test_prompt_does_not_claim_a_shipped_capability_is_impossible() -> None:
    """The prompt must never assert that Control D cannot do something.

    It once carried a rule ordering the model to say so, which risked the model
    telling a user a capability was absent when it was merely not exposed here.
    The surface is tier-gated, so the model does not enumerate write tools; what
    it must do instead is frame absence as "no tool here exposes it".
    """
    assert "no tool here exposes it" in PROMPT

    # No wording may return that asserts the vendor lacks a capability.
    for claim in (
        "Control D cannot",
        "cannot do something",
        "the API does not support it",
    ):
        assert claim not in PROMPT, claim


def test_prompt_states_each_cross_cutting_rule_once() -> None:
    """A rule repeated in two places is a rule that can be updated in one.

    The client/endpoint duality and the identifier provenance rule were each
    stated twice, in wordings that had drifted apart.
    """
    paragraphs = [p for p in PROMPT.split("\n\n") if p.strip()]

    # The duality is specifically that one device can be both a client and an
    # endpoint at once. Matching on "both" alone also catches unrelated phrases
    # such as "ids win when both are given".
    duality = [p for p in paragraphs if "appear as both" in p]
    assert len(duality) == 1, f"duality stated in {len(duality)} paragraphs"

    identifiers = [
        p
        for p in paragraphs
        if "never from Home Assistant" in p or "not a Home Assistant device id" in p
    ]
    assert len(identifiers) == 1, f"identifiers stated in {len(identifiers)} paragraphs"
