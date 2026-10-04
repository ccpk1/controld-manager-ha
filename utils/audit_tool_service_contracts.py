"""Compare every LLM tool's declared schema with its backing service schema.

The tool layer is a separate contract from the service layer: a tool declares
arguments, then forwards them to a service with its own schema. Nothing
mechanically ties the two together, which is how a mismatch like passing a
Control D profile PK to a device selector survived review. This script makes the
two layers checkable against each other.

Run from the repository root:
    python utils/audit_tool_service_contracts.py
"""

from __future__ import annotations

import pathlib
import sys

import yaml

TOOL_MODULES = ("llm_tools_read", "llm_tools_control")

# Resolved by the shared service resolver rather than named by each tool.
ENTRY_TARGET_FIELDS = {"config_entry_id", "config_entry_name"}


def _declared_fields(schema: object) -> dict[str, bool]:
    """Return {field_name: required} for a voluptuous schema."""
    fields: dict[str, bool] = {}
    for marker in getattr(schema, "schema", {}):
        fields[str(getattr(marker, "schema", marker))] = bool(
            getattr(marker, "required", False)
        )
    return fields


def main() -> int:
    """Report tool/service contract mismatches and return a shell status."""
    import importlib

    # Run from anywhere: the integration is imported as a top-level package.
    root = pathlib.Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    services_path = root / "custom_components/controld_manager/services.yaml"
    specs = yaml.safe_load(services_path.read_text())

    tools: list[type] = []
    for module_name in TOOL_MODULES:
        module = importlib.import_module(
            f"custom_components.controld_manager.{module_name}"
        )
        for attribute in vars(module).values():
            if (
                isinstance(attribute, type)
                and hasattr(attribute, "_service")
                and hasattr(attribute, "parameters")
            ):
                tools.append(attribute)

    problems = 0
    header = f"{'tool':34} {'service':30} {'tool-only':26} service-only"
    print(header)
    print("-" * len(header))

    for tool in sorted(tools, key=lambda item: item.__name__):
        service = tool._service
        spec = specs.get(service)
        if spec is None:
            print(f"{tool.__name__:34} {service:30} !! service not in services.yaml")
            problems += 1
            continue

        tool_fields = _declared_fields(tool.parameters)
        service_fields = set(spec.get("fields") or {}) | ENTRY_TARGET_FIELDS
        tool_only = sorted(set(tool_fields) - service_fields)
        service_only = sorted(service_fields - set(tool_fields))
        required_omitted = [
            name
            for name in service_only
            if (spec.get("fields") or {}).get(name, {}).get("required") is True
        ]

        note = ""
        if tool_only or required_omitted:
            problems += 1
            note = "  <-- CHECK"
        print(f"{tool.__name__:34} {service:30} {tool_only!s:26} {service_only}{note}")
        if required_omitted:
            print(f"{'':34} required but never sent: {required_omitted}")

    print()
    print(f"tools checked: {len(tools)}   flagged: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
