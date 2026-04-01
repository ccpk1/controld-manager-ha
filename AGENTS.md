# Control D Manager agent guide

This repository is a standalone Home Assistant custom integration scaffold for Control D.

## Mission

- Keep the repo standalone. Do not move logic into other repositories.
- Keep the architecture minimal, typed, and translation-ready.
- Aim for a Home Assistant platinum-quality implementation without claiming completed quality-scale status before behavior exists.
- Use Home Assistant Core in the workspace for reference patterns and local validation only. Do not make unrelated changes under `/workspaces/core`.

## First files to inspect

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `pyproject.toml`
- `custom_components/controld_manager/manifest.json`
- `custom_components/controld_manager/config_flow.py`
- `custom_components/controld_manager/coordinator.py`
- `custom_components/controld_manager/api/`
- `custom_components/controld_manager/quality_scale.yaml`
- `tests/conftest.py`

## Source map

- Integration code: `custom_components/controld_manager/`
- Tests: `tests/components/controld_manager/`
- Shared pytest setup: `tests/conftest.py`
- Translations: `custom_components/controld_manager/translations/en.json`
- Quality tracking: `custom_components/controld_manager/quality_scale.yaml`
- Plans: `plans/in-process/`

## Implementation rules

- Prefer the smallest change that solves the real problem.
- Keep runtime typing clean and explicit.
- Keep user-facing strings translation-ready from day one.
- Extend the scaffold in place before introducing new layers or helper modules.
- Be honest in `quality_scale.yaml`; mark `todo` or `exempt` until behavior actually exists.
- Do not guess the Control D API contract. Confirm authentication, profile model, rate limits, and mutation semantics before implementation.

## Validation commands

Run these in this repository unless the task clearly does not affect code:

```bash
python -m ruff check .
python -m ruff format .
python -m mypy custom_components/controld_manager
python -m pytest tests/ -v
```

For focused work, narrower pytest scopes are allowed during iteration, but the final report should say what was and was not run.

## Planning convention

- Main plans live in `plans/in-process/`.
- Main plan name: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting notes: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`
- Plans should be executable, phase-based, and reference concrete files.
- Durable architecture and standards guidance belongs in `docs/`, not inside planning files.

## Definition of done

- Code is minimal and coherent with existing scaffold patterns.
- Typing remains strict.
- Translations stay ready.
- Validation results are reported clearly.
- Any open API assumptions, auth gaps, or follow-up work are called out explicitly.