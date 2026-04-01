# Control D Manager quality reference

## Purpose

This document maps repository quality expectations to the source documents and implementation surfaces that enforce them.

It is a compact reference for review and maintenance. It should stay focused on durable contracts, not temporary project status.

## Source documents

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `AGENTS.md`
- `custom_components/controld_manager/quality_scale.yaml`

## Quality mapping

| Quality area | Contract | Evidence surface |
| --- | --- | --- |
| Layer boundaries | Protocol work stays inside `api/`; coordinator routes refreshes and owns config-entry writes; managers own business orchestration | `docs/ARCHITECTURE.md`, `custom_components/controld_manager/api/`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/` |
| Strict typing | Stable structures use strong typing and mypy remains authoritative | `docs/DEVELOPMENT_STANDARDS.md`, `pyproject.toml`, `custom_components/controld_manager/` |
| Entry scope safety | Runtime behavior remains scoped to one config entry representing one authenticated Control D instance | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, flow, services, and runtime code |
| Entity reliability | Entities have stable identity, defined lifecycle handling, correct device attachment, and roaming-endpoint reassignment behavior | `docs/ARCHITECTURE.md`, platform files, entity base logic |
| Device lifecycle discipline | Only the instance system device and profile devices are created, and all device registry behavior is manager-owned | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `custom_components/controld_manager/managers/` |
| Mutation discipline | Manager methods are the single write path above the API layer | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, manager and service code |
| Translation posture | User-facing failures and service surfaces are translation-ready | translations, flows, services, repair surfaces |
| Error handling | API exceptions are typed and Home Assistant exception mapping is specific | `custom_components/controld_manager/api/`, flows, services, coordinator |
| Diagnostics and supportability | Sensitive data is redacted while diagnostics remain useful | `custom_components/controld_manager/diagnostics.py` |
| Runtime efficiency | Refreshes are grouped by actual data cadence instead of a single oversized poll path, and entities do not poll the API directly | coordinators, managers, platform code |
| Documentation quality | Repository guidance reflects durable rules and stays aligned with implementation | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `docs/QUALITY_REFERENCE.md` |

## Architecture quality contracts

### Terminology contract

- Control D runtime records are profiles, endpoints, policies, snapshots, and registry entries
- Home Assistant platform objects are entities
- Home Assistant devices are registry containers only; physical clients remain endpoints

### Layer contract

- `api/` is framework-independent
- coordinator routes refreshes and owns config-entry writes
- manager layer owns device lifecycle, entity lifecycle, selection, and mutation orchestration
- entities and services remain presentation and interaction surfaces

### Multi-instance contract

- one authenticated Control D instance should map cleanly to one config entry
- device identity remains instance- and profile-anchored, while endpoints remain entity-only surfaces
- cleanup and signaling remain entry-scoped
- unique IDs must remain stable across profile renames and endpoint roaming

### Polling contract

- refresh paths should be split by data cadence when analytics and configuration payloads differ materially
- the preferred baseline is a fast analytics poller and a slower configuration poller
- successful mutations should request an immediate refresh of the affected configuration state

### Translation contract

- user-facing failures and operational surfaces use translation-backed messaging
- English source files remain the source of truth for translation keys

## Validation model

### Automated gates

Run:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`

### Review gates

Review changes for:

- boundary violations
- duplicated business logic outside the manager layer
- identity instability
- missing translation readiness
- non-specific exception handling
- unvalidated API assumptions
- endpoint-device modeling mistakes that would bloat the device registry

## Maintenance rule

Update this document only when:

- a quality contract changes
- a source-of-truth document moves or is replaced
- the repository adds a new required validation or review gate