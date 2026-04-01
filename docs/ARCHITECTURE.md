# Control D Manager architecture

## Purpose

This document defines the durable architecture contract for the Control D Manager integration.

It captures the chosen runtime model, ownership boundaries, and registry behavior that all implementation work must follow.

## Naming baseline

- GitHub repository name: `controld-manager-ha`
- Home Assistant UI name: `Control D Manager`
- Home Assistant integration domain: `controld_manager`
- Home Assistant package path: `custom_components/controld_manager/`

## Architectural principles

- one config entry represents one authenticated Control D instance
- runtime behavior is strictly entry-scoped so multiple instances can coexist safely
- business logic lives in managers, not in entities, services, or flows
- the coordinator layer owns refresh orchestration and config-entry lifecycle routing
- Home Assistant devices are used sparingly as containers, not as a mirror of every upstream object
- entity identity is immutable, translation-ready, and independent from mutable display names

## Official lexicon

Use these terms consistently across code and docs.

| Term | Meaning |
| --- | --- |
| Domain | The Home Assistant integration domain `controld_manager` only |
| Config entry | The single authenticated Home Assistant connection to one Control D instance |
| Device | A Home Assistant device registry object used only as a logical and visual container |
| Entity | A Home Assistant platform object only |
| Profile | A Control D configuration container holding rules, services, and blocklists |
| Endpoint | A physical client such as a phone, PC, or tablet |
| Runtime snapshot | The coordinator-owned in-memory view of current Control D state |
| Registry | The manager-owned indexed runtime structure derived from API payloads |
| Policy | A Control D rule, filter, service toggle, or other supported profile-level control |
| Unique ID | The stable Home Assistant registry identifier supplied by the integration |
| Entity ID | The Home Assistant registry string generated and owned by Home Assistant |

Critical rules:

- never use `entity` to describe a Control D profile, endpoint, policy, or API object
- never use `device` to describe a physical Control D endpoint
- never use `domain` to describe DNS domains or Control D policy categories inside integration code

## Core runtime model

### Config-entry model

- one config entry maps to one authenticated Control D instance
- credentials are stored once per instance
- all runtime objects, services, diagnostics, reload behavior, and cleanup remain scoped to the owning entry

Rationale: this avoids credential duplication and keeps multi-instance behavior deterministic.

### Device and entity hierarchy

- one instance system device represents the Control D instance
- one profile device is created for each Control D profile
- physical endpoints do not become Home Assistant devices
- endpoint telemetry and control surfaces are modeled as entities attached to the owning profile device

Rationale: profiles are a useful organizational unit in Home Assistant; endpoints are not.

### Identity model

- the config-entry unique ID must use an immutable Control D instance identifier
- the instance system device must use the same instance identity anchor as the owning config entry
- profile devices must use immutable profile identifiers
- entity unique IDs must include entry scope, immutable upstream object identity, and a stable surface suffix
- display names, email addresses, usernames, and API keys must never be used as unique IDs

### Roaming endpoint behavior

- endpoint entities must be reattached to the correct profile device when profile membership changes upstream
- this reassignment must happen during normal refresh handling and must not require an integration reload

## Layered design

### API layer

Files under `custom_components/controld_manager/api/` own:

- authentication
- HTTP transport
- request and response handling
- API exception taxonomy

Rules:

- `api/` is the only protocol boundary
- nothing in `api/` may import `homeassistant.*`

### Coordinator layer

The coordinator layer owns:

- refresh scheduling and execution
- availability transitions
- log-once unavailable and recovery behavior
- routing refresh outputs into manager-owned runtime state
- config-entry writes and reload routing when entry-scoped lifecycle updates are required

Rules:

- the coordinator layer is a router, not a business-logic owner
- entities must not poll the API directly for routine state

### Manager layer

The manager layer owns:

- normalized registry shaping
- device lifecycle management
- entity lifecycle management
- profile and endpoint orchestration
- mutation orchestration and validated write paths
- optimistic in-memory state updates when justified

The minimum manager set is:

- `BaseManager`
- `IntegrationManager`
- `DeviceManager`
- `EntityManager`
- `ProfileManager`
- `EndpointManager`

Manager role contract:

- `IntegrationManager` owns entry-scoped runtime orchestration and shared integration behavior
- `DeviceManager` owns Home Assistant device registry behavior
- `EntityManager` owns add, update, remove, cleanup, and reattachment behavior for dynamic entities
- `ProfileManager` owns profile business logic and profile-scoped mutation flows
- `EndpointManager` owns endpoint normalization, inventory, and profile mapping

### Entity and service layer

Entities and services own:

- Home Assistant presentation
- input validation
- translation-ready exception mapping
- delegation to manager methods

Rules:

- entities and services must not perform protocol calls directly
- services must not become a second business-logic path
- shared entity behavior belongs in `entity.py`

## Polling architecture

The integration uses split polling when data cadence differs materially.

Required posture:

- a fast analytics refresh path for query counts, heartbeat-style activity, and dashboard telemetry
- a slower configuration refresh path for rules, services, and profile configuration
- bulk fetching is preferred when the API supports it
- after a successful mutation, the integration must request an immediate refresh of the affected configuration state

Rationale: analytics and configuration data have different freshness requirements and should not share one oversized poll path.

## Entity architecture

The initial entity surface must stay conservative and high value.

Baseline direction:

- `switch` for stable profile-level controls
- `sensor` for analytics and endpoint telemetry
- `binary_sensor` only for stable boolean states with clear user value
- `button` only for safe stateless actions

Rules:

- not every upstream field becomes an entity
- `_attr_has_entity_name = True` should be used where appropriate
- user-facing naming must be translation-backed
- mutable labels must not affect identity
- purpose metadata should be exposed when it materially clarifies the entity's role

## Service architecture

The integration exposes one shared service model across the entry.

Required behavior:

- service target resolution must support `entity_id`, `device_id`, and `config_entry_id`
- service handling must remain entry-scoped by default
- mixed-instance targeting must be rejected unless a service explicitly supports it
- mutation services must delegate to manager-owned write paths
- duration-based pause behavior must remain stateless in Home Assistant when the upstream API supports a cloud-owned disable timer

## Runtime data contract

`ConfigEntry.runtime_data` is the single owner of the live integration runtime for one entry.

It must hold:

- the authenticated API client
- the coordinator objects or refresh-group owners
- the manager objects required by the entry
- the current normalized runtime state needed by entities, services, and diagnostics

## Diagnostics and lifecycle

- diagnostics must redact credentials and secrets
- unload, reload, reauth, and repairs must remain entry-scoped
- cleanup must remove only resources owned by the affected config entry
- availability behavior must degrade gracefully without corrupting registry identity

## Implementation guardrails

- do not duplicate business logic outside the manager layer
- do not create Home Assistant devices for endpoints
- do not anchor identity to mutable names
- do not let helper modules become alternate write paths
- do not bypass the shared service targeting and lifecycle rules