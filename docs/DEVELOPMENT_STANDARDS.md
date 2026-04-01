# Control D Manager development standards

## Purpose

This document defines the prescriptive build rules for the Control D Manager integration.

It specifies how implementation work must be written, reviewed, and extended so the repository stays aligned with the architecture contract.

## Naming baseline

- Product name: `Control D Manager`
- Integration domain: `controld_manager`
- Package path: `custom_components/controld_manager/`
- Pure protocol boundary: `custom_components/controld_manager/api/`

## General rules

- prefer the smallest coherent change that solves the real problem
- keep typing explicit and complete
- keep user-facing behavior translation-ready from day one
- preserve layer boundaries even when a shortcut looks faster
- avoid convenience fallbacks for identity, transport, or mutation behavior
- do not guess undocumented Control D API behavior

## Lexicon standards

Use repository terminology consistently.

- use `domain` only for the Home Assistant integration domain `controld_manager`
- use `profile`, `endpoint`, `policy`, `runtime snapshot`, and `registry` for Control D data concepts
- use `entity` only for Home Assistant platform objects
- use `device` only for Home Assistant device registry objects
- use `unique ID` for the stable registry identifier and `entity_id` for the Home Assistant registry string

Critical rules:

- never call a Control D profile, endpoint, policy, or API object an entity
- never call a physical client a device inside integration code or docs; use `endpoint`
- never use `domain` inside the integration to describe DNS domains or list items

## Constants taxonomy

Use explicit constants instead of scattered literals.

Approved constant families:

- `DOMAIN`
- `CONF_*`
- `DEFAULT_*`
- `ATTR_*`
- `SERVICE_*`
- `SERVICE_FIELD_*`
- `TRANS_KEY_*`
- `TRANS_PLACEHOLDER_*`
- flow-step constants once flow complexity justifies them

The constant system must stay disciplined but compact.

Usage matrix:

- `CONF_*`: config-entry data or options keys only
- `DEFAULT_*`: default values only
- `ATTR_*`: Home Assistant entity state attributes only
- `SERVICE_*`: service names only
- `SERVICE_FIELD_*`: service schema keys and `call.data` access only
- `TRANS_KEY_*`: translation identifiers only
- `TRANS_PLACEHOLDER_*`: translation placeholder names only

Rules:

- do not use `ATTR_*` constants in service schemas or `call.data`
- do not use `CONF_*` constants for service selector fields
- prefer compact, honest families over a large taxonomy the repository does not need

## Type system

- all public and internal functions must be type hinted
- use modern Python typing syntax
- use dataclasses, enums, or `TypedDict` for stable structures with fixed keys
- use dynamic mappings only where the upstream payload is genuinely variable
- avoid `dict[str, object]` for stable API, config, manager, or service payload shapes when a stronger type is available
- avoid type suppressions unless no honest type expression can represent the pattern cleanly

## Module and layer boundaries

### `api/`

Files in `custom_components/controld_manager/api/` own:

- authentication
- HTTP transport
- response parsing
- API-specific exception types

Rules:

- nothing inside `api/` may import `homeassistant.*`
- `api/` must not become a single-file monolith
- transport, auth, and response handling should stay separated when they justify separate files
- the API layer must translate transport and auth failures into integration-specific exceptions instead of leaking raw client exceptions upward

### Coordinator

The coordinator layer owns:

- routing refresh outputs into the runtime layer
- polling cadence
- refresh orchestration
- availability transitions
- config-entry writes and reload-triggering config updates when mutable entry-scoped settings are introduced
- normalized refresh inputs handed to managers when one shared contract is needed

Rules:

- the coordinator is primarily a router and refresh orchestrator, not a business-logic owner
- the coordinator must not own profile business logic, service dispatch, dynamic entity reconciliation, or mutation payload construction
- config-entry writes belong to the coordinator layer, not to managers, helpers, services, or platform files

### Manager layer

Manager modules own:

- instance-scoped registry shaping
- supported policy resolution
- mutation orchestration
- optimistic updates when justified
- shared indexed runtime lookups
- device lifecycle reconciliation
- entity lifecycle reconciliation

Rules:

- all supported mutations above the API layer must flow through manager methods
- entities, flows, and services must not duplicate command logic or payload construction once manager methods exist
- managers must not become a miscellaneous dumping ground for unrelated helpers
- direct cross-manager writes are forbidden
- direct read-only manager calls are acceptable only when they do not create hidden mutation coupling

Required minimum manager set:

- `base_manager.py` defines the shared typed contract for manager modules
- `integration_manager.py` owns shared entry-scoped lifecycle, instance-wide orchestration, and cross-platform behavior
- `device_manager.py` owns Home Assistant device registry lifecycle for the instance system device and profile devices
- `entity_manager.py` owns entity add, update, remove, cleanup, and reassignment behavior
- `profile_manager.py` owns profile business logic and profile-scoped mutation orchestration
- `endpoint_manager.py` owns endpoint normalization, endpoint-to-profile mapping, and endpoint-specific business logic

### Helpers

Helper modules under `custom_components/controld_manager/helpers/` own shared Home Assistant-aware support code.

Rules:

- helpers may import Home Assistant APIs
- helpers must not own business orchestration or write paths
- helpers should contain reusable integration glue such as entity lookup or input normalization helpers
- report-style helpers belong in `helpers/` only if they are read-only views over manager-owned data

### Utils

Utility modules under `custom_components/controld_manager/utils/` own pure reusable functions.

Rules:

- utils must not import `homeassistant.*`
- utils are the correct home for pure parsing, formatting, and value-normalization helpers
- utils must not accumulate orchestration logic that belongs in managers

### Entities and services

Rules:

- entities and services are presentation and interaction surfaces only
- they must delegate business logic to manager methods
- they must not perform protocol calls directly
- they must map failures into specific Home Assistant exception types and translation keys

## Async and event loop rules

- all network requests in `custom_components/controld_manager/api/` must use async I/O
- the `requests` library is forbidden
- do not perform blocking I/O in the Home Assistant event loop
- keep executor usage tightly scoped to actual blocking work if any unavoidable non-async library call exists

## Identity and config-entry scope rules

- the Home Assistant config entry identity must use an immutable Control D instance identifier
- display names, usernames, email addresses, and API keys must never be used as unique IDs
- profile devices must use immutable profile identifiers rather than profile names
- entity unique IDs must remain stable under reauthentication, profile renames, and endpoint roaming between profiles
- all runtime behavior must operate within one explicit config-entry scope
- do not rely on first-loaded-entry behavior
- services, reloads, unloads, diagnostics, repairs, and reauth flows must target the owning entry only
- signal names, cleanup logic, and unique-ID construction must preserve per-entry isolation for multi-instance support

## Device standards

- create exactly one instance system device per config entry and one device per Control D profile unless a future architecture decision explicitly changes that rule
- never create Home Assistant devices for physical endpoints
- all device registry creation, updates, and cleanup must flow through `device_manager.py`
- profile devices must remain stable under profile renames and reauthentication

## Entity standards

### Entity naming

- prefer `_attr_has_entity_name = True` for entities attached to the instance system device or a profile device
- user-facing names must be owned by translation keys
- do not hardcode `_attr_name` for production entity names
- mutable labels such as profile names and endpoint labels may use translation placeholders

### Entity identity

- unique IDs must be based on immutable identifiers
- unique IDs must include the config-entry instance identifier, the immutable object identifier, and a stable suffix
- Home Assistant owns the final `entity_id`

### Entity lifecycle

- dynamic entity add, update, remove, cleanup, and orphan handling must follow one shared lifecycle policy owned by `entity_manager.py`
- endpoint entity cleanup must be deterministic when endpoints disappear from the upstream inventory
- when an endpoint roams to another profile, the integration must update its device attachment during the refresh cycle instead of requiring an integration reload
- shared entity base classes are allowed only when at least two platforms need the same abstraction

### Shared entity base

- `custom_components/controld_manager/entity.py` is part of the expected core runtime layout for the first multi-platform buildout
- use `entity.py` as the shared base for common availability handling, typed coordinator access, typed manager access, `DeviceInfo`, identity behavior, purpose metadata, translation-placeholder refresh, and device attachment helpers
- shared entity behavior must stay focused on platform-common concerns and must not become a second business-logic layer

### Entity scope

- not every Control D setting needs a Home Assistant entity
- prefer a smaller entity set with clear user value over exhaustive API mirroring
- endpoint telemetry should remain entity-scoped under the owning profile device rather than expanding the Home Assistant device registry

### Entity metadata

- add concise purpose-oriented metadata when it materially helps users understand what an entity controls or represents
- keep purpose metadata stable, readable, and manager-derived
- do not expose internal debugging structures or sensitive payloads as entity attributes

### Platform concurrency

- coordinator-based platforms should set `PARALLEL_UPDATES = 0` explicitly when entities do not poll independently
- any non-zero or non-default parallel update limit must be justified by platform behavior and protocol constraints
- platform concurrency policy should be declared in the platform module rather than left implicit

## Mutation and write-path standards

- manager methods are the single write path above the API layer
- services, flows, and platform files must not construct ad hoc mutation payloads independently once manager APIs exist
- successful commands may update in-memory runtime state optimistically
- optimistic changes must remain in memory only
- the next coordinator refresh remains the source of truth
- if refreshed state disagrees with optimistic state, the refreshed state wins and the discrepancy must be handled as reconciliation, not hidden silently

## Runtime registry standards

- normalize upstream payloads once per refresh path when practical
- shared indexed lookups must be built centrally
- future platforms, services, and diagnostics must consume shared normalized outputs instead of repeating full payload scans
- lazy lookup or caching is acceptable only when it preserves correctness and does not create a second source of truth

## Polling standards

- direct API calls from entities are forbidden except for narrowly justified, user-initiated actions that cannot be expressed through the manager path
- prefer split refresh groups over one oversized poll path when analytics and configuration data have materially different cadences
- benchmark the final polling shape against Home Assistant cloud integrations such as NextDNS before locking the intervals
- current target posture is a fast analytics poller at 3 to 5 minutes and a slow configuration poller at 30 to 60 minutes
- after a successful mutation, trigger an immediate refresh of the affected configuration path so the Home Assistant UI reflects the new cloud state promptly

## Config flow standards

- the config flow must validate account access before entry creation
- the main user flow must authenticate once per Control D instance and create one config entry for that instance rather than one entry per profile
- do not let users supply a free-form config entry name in the main user step
- duplicate prevention must use the immutable instance identifier
- implement reauthentication and reconfiguration explicitly once credentials and instance identity semantics are confirmed

## Service standards

- service handlers must resolve one explicit config-entry scope
- validate entry scope and loaded state before mutation calls
- service target resolution must accept `entity_id`, `device_id`, and `config_entry_id` as first-class selectors
- service handlers must validate Home Assistant-facing input and then delegate to manager methods
- services must reject ambiguous or mixed-instance targets with specific, translation-ready exceptions
- the first planned mutation-oriented custom service is `controld_manager.pause_profile`, which should compute the future disable timestamp locally and let the Control D cloud own the countdown state

## Exception handling rules

- catch the narrowest exception that accurately describes the failure
- map API failures to specific Home Assistant exceptions at the edge layer
- do not use broad catch-all exception handling in normal runtime code unless a background-task safety boundary genuinely requires it

## Logging rules

- log useful operational state without exposing credentials, tokens, or sensitive payloads
- use lazy logging
- keep repeated unavailability logging under control through log-once unavailable and recovery behavior

## Localization and translation rules

- production user-facing strings must be translation-backed
- English source files are the only manually edited translation source
- user-facing failures, service errors, and flow errors must use stable translation keys once those surfaces exist

## Diagnostics and security rules

- diagnostics must redact secrets and tokens using Home Assistant redaction helpers
- diagnostics should include enough normalized state to troubleshoot instance identity, auth, profile and endpoint inventory, and supported runtime surfaces
- never expose raw credentials, tokens, or user secrets

## Testing standards

- keep `tests/components/controld_manager/` aligned with the integration structure
- mock all external API behavior
- config-flow paths should reach full coverage once config flow is implemented
- test instance setup, auth failures, reauth, reconfigure, and entry scoping explicitly when those behaviors exist
- test profile-device lifecycle, endpoint roaming between profile devices, multi-instance unique-ID isolation, and service target resolution explicitly

## Review rules

Review changes against these questions:

- does this change preserve the `api/` boundary?
- does business logic remain in manager methods instead of entities, flows, or services?
- do config-entry writes stay in coordinator-owned paths?
- do specialized shared modules live under `managers/`, `helpers/`, or `utils/` instead of becoming unowned root files?
- does the change preserve entry-scoped behavior?
- are user-facing failures translation-ready and specifically typed?
- does the change keep entity identity stable?
- does the change reuse the shared registry pipeline instead of introducing another ad hoc lookup path?
- does the change introduce orphan-prone lifecycle behavior without an explicit reconciliation policy?

## Boundary enforcement

- maintain boundary checks that enforce purity boundaries, write ownership, and layer placement rules
- boundary checks should reject Home Assistant imports in `utils/`
- boundary checks should reject duplicated business logic or write paths in services, flows, and platform files
- boundary checks should reject unowned specialized root modules when the code clearly belongs under `managers/`, `helpers/`, or `utils/`

## Validation workflow

Run these commands for relevant changes:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`

Documentation and translations must be updated when behavior changes require them.