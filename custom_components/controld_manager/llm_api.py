"""LLM API exposing Control D Manager data to assistants.

This module is imported only when ``llm_tools_supported()`` is true, so the Core
2026.10-only ``homeassistant.helpers.llm`` names below are never imported on
older Home Assistant. Do not rename this module to ``llm.py`` — that is Home
Assistant's LLM integration-platform filename and is auto-imported by the ``llm``
integration outside this integration's version guard. A package named ``llm/``
is equally hazardous for the same reason.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import (
    CATALOG_TYPES,
    DOMAIN,
    LLM_TOOL_MODE_FULL,
    LLM_TOOL_MODE_OFF,
    LLM_TOOL_MODE_READ_AND_CONTROL,
    LLM_TOOL_MODE_SUMMARY_ONLY,
)
from .llm_tools_common import api_prompt
from .llm_tools_control import build_control_tools
from .llm_tools_read import build_account_overview_tools, build_read_tools
from .models import ControlDManagerRuntime

LOGGER = logging.getLogger(__name__)


class ControlDManagerAPI(llm.API):
    """LLM API owned by the Control D Manager integration.

    Registered once per config entry. The registered tool set is selected by the
    configured tier. Phase 2 adds the overview first; further read tools land in
    the same phase and control tools land in Phase 3.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api_id: str,
        name: str,
        entry_id: str,
        mode: str,
    ) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=api_id, name=name)
        self._entry_id = entry_id
        self._mode = mode

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the API instance for one LLM request.

        Built per request so the user's timezone is read fresh: it is a Home
        Assistant setting that can change while the integration is loaded.
        """
        time_zone = self.hass.config.time_zone
        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt(time_zone),
            llm_context=llm_context,
            tools=self._build_tools(time_zone),
        )

    def _build_tools(self, time_zone: str | None = None) -> list[llm.Tool]:
        """Return the tools registered for the configured tier.

        Summary registers only the overview. Read tiers add the read tools.
        Read-and-control adds the reversible controls, and Full additionally adds
        the destructive delete. Every write service requires an admin user, so a
        non-admin caller is rejected by the service layer regardless of tier. The
        mode is the only thing deciding what is reachable.
        """
        if self._mode == LLM_TOOL_MODE_OFF:
            return []
        tools = build_account_overview_tools(entry_id=self._entry_id)
        if self._mode == LLM_TOOL_MODE_SUMMARY_ONLY:
            return tools
        tools.extend(build_read_tools(entry_id=self._entry_id, time_zone=time_zone))
        if self._mode in (LLM_TOOL_MODE_READ_AND_CONTROL, LLM_TOOL_MODE_FULL):
            tools.extend(
                build_control_tools(
                    entry_id=self._entry_id,
                    include_destructive=self._mode == LLM_TOOL_MODE_FULL,
                )
            )
        # Logged once per build so the running process reports the surface it
        # actually registered, including the catalog types it will accept. A
        # client can only offer what this list contains, so this is the
        # authoritative answer to "why was a value rejected".
        LOGGER.debug(
            "Built Control D LLM tools: mode=%s count=%d catalog_types=%s",
            self._mode,
            len(tools),
            CATALOG_TYPES,
        )
        return tools


def _resolve_api_name(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return a display name unique among this integration's entries.

    Home Assistant derives a merged tool's namespace from the API *name*, and it
    only enforces uniqueness of ids, not names. Two entries the user titled
    identically would otherwise produce two identically-named tool sets, leaving
    the model no way to tell which account it is acting on. The discriminator is
    decided from the config entries themselves rather than from what is currently
    registered, so every entry reaches the same verdict regardless of
    registration order and names do not move on reload.
    """
    title = entry.title
    others = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not any(other.title == title for other in others):
        return title
    return f"{title} [{entry.entry_id[:6]}]"


def async_register_control_d_api(
    hass: HomeAssistant, entry: ConfigEntry[ControlDManagerRuntime]
) -> Callable[[], None]:
    """Register the Control D Manager LLM API for one config entry."""
    api = ControlDManagerAPI(
        hass,
        # The config entry id is the account's stable identity: assigned by Home
        # Assistant, never reissued, and unaffected by a rename or by another
        # entry appearing. This id is both the MCP URL and the value
        # `mcp_server` stores to select an API, so it must not move.
        api_id=f"{DOMAIN}-{entry.entry_id}",
        # The title is the display name only, so renaming changes what users see
        # without moving the id.
        name=_resolve_api_name(hass, entry),
        entry_id=entry.entry_id,
        mode=entry.runtime_data.options.llm_tool_mode,
    )
    return llm.async_register_api(hass, api)
