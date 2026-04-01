[![Quality Baseline: Platinum-ready](https://img.shields.io/badge/Quality%20Baseline-platinum--ready-1E88E5.svg)](https://github.com/ccpk1/controld-manager-ha)
[![Quality Gates](https://img.shields.io/github/actions/workflow/status/ccpk1/controld-manager-ha/lint-validation.yaml?branch=main&label=Quality%20Gates)](https://github.com/ccpk1/controld-manager-ha/actions/workflows/lint-validation.yaml)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/controld-manager-ha/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs)

# Control D Manager

> Cloud-first Home Assistant integration scaffold for the Control D DNS service.

Control D Manager is a repository-first baseline for a future Home Assistant integration targeting Control D. This repository intentionally focuses on structure, documentation, planning, validation, and collaboration surfaces before implementation begins.

## Why this repository exists

The goal is to start from a high-quality custom integration baseline rather than from an empty folder.

This repository carries forward the working repository standards from Firewalla Local while aiming the eventual integration architecture toward Control D's cloud DNS model. The future runtime direction is expected to resemble the Home Assistant NextDNS integration most closely, with selective ideas borrowed from AdGuard Home and Pi-hole where they improve service ergonomics or user control.

## Current status

This is an implementation scaffold, not a finished integration.

- repository structure is in place
- Home Assistant custom component package is scaffolded
- standards and architecture documents are adapted for Control D
- planning artifacts capture the recommended product direction
- implementation of the actual Control D API client, config flow, entities, and services is intentionally deferred

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