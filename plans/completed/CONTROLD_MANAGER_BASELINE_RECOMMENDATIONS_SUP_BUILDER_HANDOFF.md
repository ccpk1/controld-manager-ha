# Control D Manager builder handoff

## Purpose

This document is the execution brief for the first implementation pass.

Use it together with:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/ENGINEERING_FINDINGS.md`
- `custom_components/controld_manager/quality_scale.yaml`
- `plans/in-process/CONTROLD_MANAGER_BASELINE_RECOMMENDATIONS_IN-PROCESS.md`

This brief is intentionally prescriptive. The builder should not reinterpret major design choices while coding.

## Non-negotiable rules

- do not deviate from the approved architecture or plan without written justification and explicit approval
- do not guess undocumented API behavior
- do not bypass manager ownership, coordinator ownership, or entry-scoped runtime rules for convenience
- do not mark quality-scale rules as done until the corresponding behavior exists in code and tests
- do not merge speculative analytics entities into the first entity slice
- do not create Home Assistant devices for physical endpoints
- do not anchor any unique ID to mutable names

## Build target

The first build pass must deliver the minimal runtime needed to support a platinum-quality foundation:

- one config entry per authenticated Control D instance
- one entry-scoped runtime stored in `ConfigEntry.runtime_data`
- one instance system device and one Home Assistant profile device per profile
- endpoint inventory normalized from `GET /devices`
- profile inventory normalized from `GET /profiles`
- manager-owned lifecycle boundaries
- coordinator-owned refresh orchestration
- boundary tests that prevent architecture drift

This first pass is about correctness, ownership, and future-proofing. It is not about shipping every possible entity.

## First-pass scope

### In scope

- async API client skeleton and exception taxonomy
- config entry setup and unique-ID handling
- entry-scoped runtime models
- refresh-group scaffolding
- manager skeletons and normalized registry contracts
- diagnostics expansion only as needed to support the runtime
- boundary tests and validation discipline

### Out of scope

- exhaustive analytics surfaces
- speculative entity expansion
- broad service catalog expansion beyond the approved first profile disable and enable direction
- Pi-hole compatibility and tamper-oriented add-ons

## Phase 2 closeout decisions the builder must treat as fixed inputs

These are approved and must be treated as fixed inputs unless the repository explicitly approves a change:

1. Refresh groups
Approved groups:

- `configuration_sync`
- `profile_analytics`
- `endpoint_analytics`

Approved defaults:

- `configuration_sync = 15 minutes`
- `profile_analytics = 5 minutes`
- `endpoint_analytics = 5 minutes`

Approved bounds:

- minimum `5 minutes`
- maximum `60 minutes`

2. First entity slice
Approved first slice:

- instance system device: minimal instance metadata only when already supported cleanly by validated runtime data
- profile devices: limited summary analytics and clean profile pause state only if the pause contract is implemented end to end
- endpoint entities: small telemetry surface only

Explicitly excluded from the first slice:

- per-filter entities
- per-service entities
- per-domain entities
- per-country entities

3. Paused-profile read normalization
Approved normalization:

- normalize `disable` and `disable_ttl` into `paused_until: datetime | None`
- derive paused state from that typed field only

4. Attached-profile sibling normalization
Approved normalization:

- normalize attached profile objects such as `profile`, `profile2`, and future siblings into one ordered `attached_profiles` list
- preserve upstream order
- use the first attached profile as the owning Home Assistant profile device
- keep later attached profiles as supplemental membership metadata only

If implementation discovers a conflict with any approved input above, stop and request clarification before implementing around assumptions.

## File-by-file first implementation sequence

### 1. Runtime contract

Primary files:

- `custom_components/controld_manager/models.py`
- `custom_components/controld_manager/const.py`

Required outcome:

- define the entry-scoped runtime types
- define the normalized registry structures
- define typed placeholders for the API client, refresh-group owners, and manager set

### 2. API client skeleton

Primary files:

- `custom_components/controld_manager/api/__init__.py`
- new files under `custom_components/controld_manager/api/` as needed

Required outcome:

- async transport boundary
- explicit envelope normalization for `/users`, `/profiles`, and `/devices`
- typed exception taxonomy
- no `homeassistant.*` imports inside `api/`

### 3. Config entry and coordinator wiring

Primary files:

- `custom_components/controld_manager/config_flow.py`
- `custom_components/controld_manager/__init__.py`
- `custom_components/controld_manager/coordinator.py`

Required outcome:

- authenticate once per instance
- unique config entry anchored to `users.id`
- one runtime created and stored in `ConfigEntry.runtime_data`
- one coordinator-owned refresh path that can load and normalize users, profiles, and devices

### 4. Manager skeletons

Primary files:

- `custom_components/controld_manager/managers/base_manager.py`
- `custom_components/controld_manager/managers/integration_manager.py`
- `custom_components/controld_manager/managers/device_manager.py`
- `custom_components/controld_manager/managers/entity_manager.py`
- `custom_components/controld_manager/managers/profile_manager.py`
- `custom_components/controld_manager/managers/endpoint_manager.py`

Required outcome:

- clear ownership boundaries only
- no ad hoc write logic outside managers
- profile-1 endpoint attachment rule expressed in runtime normalization or reconciliation logic

### 5. Boundary tests

Primary files:

- `tests/components/controld_manager/`
- `tests/conftest.py`

Required outcome:

- tests for unique-ID anchoring
- tests for entry-scoped runtime creation
- tests for normalized envelope handling
- tests for manager ownership and coordinator-owned writes

## Platinum guardrails

The builder must actively aim at platinum behavior even where quality-scale entries remain `todo`.

### Required engineering posture

- strict typing throughout
- async-only transport behavior
- no blocking calls in the event loop
- translation-ready strings from first introduction
- diagnostics-safe data handling
- validation-first config flow behavior
- explicit exceptions and error mapping

### Refresh-group review gate

After the first working runtime exists, the builder must review the refresh-group placement of all fetched data.

Rule:

- if data assigned to a slower refresh group is already sourced by a faster refresh group with no material performance cost, the builder should recommend moving that processing to the faster group
- do not preserve a slower poll interval when it adds latency but no real load reduction benefit
- do not change refresh-group placement silently; document the evidence and request approval before changing the contract

### Required Home Assistant posture

- config flow and reauth-ready architecture
- proper `ConfigEntry.runtime_data` usage
- proper unload and reload behavior
- device registry discipline
- entity unique-ID stability
- manager- and coordinator-owned lifecycle control

## Validation checklist for every implementation step

Run these commands unless the builder has a documented reason for using a narrower scope during iteration:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`

Every progress report must include:

- what files changed
- which validations ran
- what did not run
- any variance from plan
- any newly discovered API ambiguity

## Stop conditions

Stop and request approval if any of the following happen:

- the API contract conflicts with the current architecture or findings
- a required identity anchor appears unstable
- multi-profile attachment needs a different rule than the approved profile-1 ownership model
- analytics scope requires a materially different entity model than currently planned
- the builder needs to bypass a manager, coordinator, or entry-scoped runtime rule to proceed

## Definition of a successful handoff build

The handoff build is successful when:

- one config entry authenticates and creates one runtime
- users, profiles, and devices can be fetched and normalized
- manager and coordinator boundaries are in place and tested
- no code path violates the architecture or development standards
- the repository is ready for the first conservative entity pass without reworking the runtime foundation