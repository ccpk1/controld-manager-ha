[![Quality Baseline: Platinum-ready](https://img.shields.io/badge/Quality%20Baseline-platinum--ready-1E88E5.svg)](https://github.com/ccpk1/controld-manager-ha)
[![Quality Gates](https://img.shields.io/github/actions/workflow/status/ccpk1/controld-manager-ha/lint-validation.yaml?branch=main&label=Quality%20Gates)](https://github.com/ccpk1/controld-manager-ha/actions/workflows/lint-validation.yaml)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/controld-manager-ha/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs)

# Control D Manager

> Cloud-first Home Assistant custom integration for the Control D DNS service.

Control D Manager is a standalone Home Assistant custom integration for managing
one Control D account per config entry. The repository still carries planning
and architecture artifacts, but it now includes a working runtime, config flow,
entity surfaces, service layer, and validation coverage.

## Why this repository exists

The goal is to keep Control D support in a focused standalone repository with a
high-quality Home Assistant integration baseline.

This repository carries forward the working repository standards from
Firewalla Local while adapting the runtime and service model to Control D's
cloud DNS API.

## Current status

This is an implemented custom integration with active runtime behavior.

- one config entry represents one authenticated Control D instance
- one Home Assistant device is created for the account and one per managed
	profile
- filters, services, rules, profile options, and endpoint status surfaces are
	available according to profile policy
- Home Assistant services support profile enable or disable, filter mutation,
	and read-only catalog discovery
- planning and standards documents remain in the repository as implementation
	guardrails and future work tracking

## Naming contract

- GitHub repository: `controld-manager-ha`
- Home Assistant UI name: `Control D Manager`
- Home Assistant integration domain: `controld_manager`
- Home Assistant package path: `custom_components/controld_manager/`

The repository slug keeps the hyphenated product naming, while the Home Assistant integration domain uses an underscore because Home Assistant package and domain conventions require a valid Python-style module name.

## Planned product shape

The intended product direction is:

- a cloud-polling Home Assistant service integration
- one config entry per authenticated Control D instance with multi-instance-safe runtime isolation
- one instance system device plus one Home Assistant device per Control D profile, with physical endpoints modeled as entities instead of Home Assistant devices
- coordinator-backed split refresh groups for analytics, configuration, and connection/runtime data
- manager-based runtime orchestration with a base manager, integration manager, device manager, entity manager, profile manager, and endpoint manager
- strong translation, diagnostics, typing, and quality-scale discipline from the first real implementation phase

## Current service surface

The integration currently exposes these shared Home Assistant services:

- `controld_manager.disable_profile`
- `controld_manager.enable_profile`
- `controld_manager.set_filter_state`
- `controld_manager.get_catalog`

See `docs/USER_GUIDE.md` for concrete examples and service field behavior.

## Documentation index

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/USER_GUIDE.md`
- `plans/in-process/CONTROLD_MANAGER_BASELINE_RECOMMENDATIONS_IN-PROCESS.md`

## Validation

Repository validation commands:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/controld_manager
python -m pytest tests/ -v
```

## Support posture

- questions and usage help: GitHub Discussions
- bugs and feature requests: GitHub Issues
- security concerns: see `SECURITY.md`

## License

This project is licensed under the GPL-3.0 license. See `LICENSE`.