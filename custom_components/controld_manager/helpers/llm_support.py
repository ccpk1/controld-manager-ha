"""Version support checks for the LLM/MCP tool surface.

``const.py`` holds only the pure ``MIN_LLM_TOOLS_HA_VERSION`` tuple, because it
sits inside the ``api/`` import graph and that layer must stay free of
``homeassistant.*``. The version check itself needs ``homeassistant.const``, so
it lives here in ``helpers/``, which the standards designate for Home
Assistant-aware glue and which ``api/`` never imports.
"""

from __future__ import annotations

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from ..const import MIN_LLM_TOOLS_HA_VERSION


def llm_tools_supported() -> bool:
    """Return whether this Home Assistant version supports LLM tools.

    The LLM tool contract (``llm.ToolResult``, ``llm.ToolAnnotations``,
    ``Tool.integration``) lands in Core 2026.10. On older Core nothing is
    registered and the integration loads exactly as before.
    """
    return (MAJOR_VERSION, MINOR_VERSION) >= MIN_LLM_TOOLS_HA_VERSION
