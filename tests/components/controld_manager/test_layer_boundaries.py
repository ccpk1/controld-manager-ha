"""Architecture boundary tests for Control D Manager.

The ``api/`` layer owns HTTP transport and must stay independent of Home
Assistant, per ``docs/DEVELOPMENT_STANDARDS.md`` ("nothing inside ``api/`` may
import ``homeassistant.*``"). ``const.py`` and ``models.py`` sit inside the
``api/`` import graph and therefore count as part of that boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

# Modules reachable from api/client.py, so an eager Home Assistant import in any
# of them pulls Home Assistant into the transport layer.
_API_GRAPH_MODULES: Final = (
    "api/__init__.py",
    "api/client.py",
    "api/exceptions.py",
    "const.py",
    "models.py",
)
_PACKAGE_ROOT: Final = (
    Path(__file__).resolve().parents[3] / "custom_components" / "controld_manager"
)


def _module_level_imports(tree: ast.Module) -> set[str]:
    """Return the top-level (non-function-body) import targets of one module."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_api_import_graph_never_imports_home_assistant() -> None:
    """No module in the api/ import graph may import Home Assistant.

    ``api/`` must not depend on Home Assistant, and ``const.py``/``models.py``
    are inside that graph. A module-level ``homeassistant`` import in any of them
    would break the layer contract and make transport code Home-Assistant-aware.
    """
    offenders: dict[str, list[str]] = {}
    for relative_path in _API_GRAPH_MODULES:
        path = _PACKAGE_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _module_level_imports(tree)
        hits = sorted(name for name in imports if name.split(".")[0] == "homeassistant")
        if hits:
            offenders[relative_path] = hits

    assert offenders == {}, (
        "api/ import graph must stay free of homeassistant imports; found "
        f"{offenders}. Move the constant or helper out of the api/ graph."
    )
