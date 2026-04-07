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
- when an endpoint is enforced by multiple profiles, the integration always assigns the endpoint entity to the first attached upstream profile exposed by the published API payload
- additional attached profiles remain part of normalized runtime metadata, but they do not change the owning Home Assistant profile device in v1
- this attachment rule is a Home Assistant presentation and organization rule only; it does not imply policy precedence inside Control D

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
- refresh groups must be defined in a way that allows additional poll categories to be added, removed, or rebalanced without reshaping the whole runtime
- each refresh group must have its own bounded interval contract so the options flow can tune cadence per group without exposing unbounded polling
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

### Entity naming contract

The default Home Assistant naming contract is intentionally scope-specific.

- account entities use explicit count-oriented names because the Account device alone is not specific enough for summary metrics
- profile entities stay short when the surface is small, but high-cardinality profile items use a hierarchical type/category/item naming pattern
- endpoint entities always start with the endpoint name because endpoints do not become Home Assistant devices
- duplicate endpoint names do not require an integration-owned fallback naming ladder; Home Assistant owns the final `entity_id` and may suffix duplicates with `_2` or similar when required

Examples:

- Account device: `Account`
- Account entities: `Account Profile Count`, `Account Endpoint Count`
- Profile device: upstream profile name
- Small profile entity set: `Disable`
- High-cardinality profile entities: `Options / Disable`, `Filters / Ads & Trackers`, `Services / Hosting / Alibaba Cloud`, `Rules / Domain / example.com`
- Filter mode entities: `Filters / Ads & Trackers Mode`
- Endpoint entities: `<endpoint name> Status`

Critical rules:

- entity display names must remain human-first; they must not expose internal field keys such as `last_active`
- endpoint names are presentation only; unique IDs and device attachment rules remain anchored to immutable upstream identifiers
- duplicate endpoint display names are acceptable; the integration does not need to pre-disambiguate them in v1
- use Control D's user-facing vocabulary where it is stable enough to be meaningful, for example `Disable` instead of `Paused`
- when one upstream filter exposes both enablement and a mode, model it as two entities: a switch for the overall enabled state and a select for the mode
- do not embed the profile name into endpoint entity names; the owning profile device already provides that context

### Entity exposure contract

The integration does not aim to mirror every available Control D surface by default.

- account summary entities may be default-enabled when they are low-cardinality and broadly useful
- only a small curated subset of profile controls should be default-enabled
- high-cardinality profile surfaces such as filters, services, and rules should be opt-in
- endpoint entities should also be opt-in
- endpoint scope should start with one compact status-oriented surface rather than many narrow sensors

Exposure policy storage contract:

- `ConfigEntry.options` stores compact integration-owned exposure policy, not mirrored Control D catalogs
- exposure policy may include a small set of global integration settings, but profile-specific exposure choices must live under the immutable profile identifier for that profile
- each profile policy may independently control profile management state, endpoint-sensor exposure, service-category exposure, category auto-enable behavior, exposed custom-rule targets, and later profile-scoped advanced settings
- live entity creation always derives from the current API data filtered through that stored policy

Per-profile policy direction:

- all discovered profiles are included by default when the entry is first created
- users may later disable any profile from participation through the options flow without deleting the config entry
- endpoint exposure is a per-profile toggle; when disabled, no endpoint entities are created for that profile
- filter entities are created automatically for every profile and do not require per-item options storage
- service entities are created dynamically from the current service catalog based on the categories enabled for that profile
- rule entities are created only for the explicitly selected folder or domain targets stored for that profile

Service creation direction:

- service categories are the correct options-flow unit for service exposure in v1
- service entities created from an enabled category should default to disabled in the entity registry
- an explicit override may allow category-created service entities to default to enabled, but that path should be presented as an advanced option with a warning about entity volume

Recommended first endpoint shape:

- one endpoint `binary_sensor` named `<endpoint name> Status`
- attributes hold supporting details such as last active, recent DNS activity, recent blocked activity, attached profiles, and parent-device metadata
- additional endpoint entities should only be added when they are clearly more useful than attributes on the status surface

Recommended `ConfigEntry.options` posture:

- store profile policy keyed by immutable profile identifier
- store service exposure by category, not by full mirrored service catalogs
- store explicit rule selections by immutable typed identity, not by display name alone
- do not store full filter, service, rule, or endpoint payloads in `ConfigEntry.options`

Recommended options-flow structure:

- follow the Firewalla Local menu pattern: one top-level menu that branches into focused submenus
- include one integration-settings area for polling and entry-wide behavior
- include one profile-selector area that lists all live Control D profiles
- include one per-profile edit form that owns management state, endpoint-sensor exposure, service-category exposure, category auto-enable behavior, and custom-rule exposure

## Service architecture

The integration exposes one shared service model across the entry.

Required behavior:

- service target resolution must support `entity_id`, `device_id`, and `config_entry_id`
- service handling must remain entry-scoped by default
- mixed-instance targeting must be rejected unless a service explicitly supports it
- mutation services must delegate to manager-owned write paths
- duration-based profile disable behavior must remain stateless in Home Assistant when the upstream API supports a cloud-owned disable timer
- profile disable and enable behavior should be exposed as paired services rather than as one overloaded mutation surface
- future disable behavior for profile sub-resources such as filters or services may share a typed target-resolution model only if validation remains explicit and unambiguous

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