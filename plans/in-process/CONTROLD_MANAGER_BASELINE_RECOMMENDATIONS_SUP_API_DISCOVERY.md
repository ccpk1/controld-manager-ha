# Support note: Control D API discovery baseline

## Purpose

This note records the verified Phase 2 API facts gathered from the public Control D docs and API reference.

It reduces ambiguity for implementation planning without promoting unverified assumptions into the architecture contract.

## Verified findings

### Live response envelope and identity findings

- `GET /users` returns `{"success": true, "body": {...account...}}`
- `GET /profiles` returns `{"success": true, "body": {"profiles": [...]}}`
- `GET /devices` returns `{"success": true, "body": {"devices": [...]}}`
- the API does not use one fully uniform `body.<controller>` wrapper across all endpoints because `/users` returns the account object directly in `body`

Planning impact:

- the API client must normalize each endpoint explicitly instead of assuming one generic collection wrapper
- `/users` should deserialize directly from `body`
- `/profiles` should deserialize from `body.profiles`
- `/devices` should deserialize from `body.devices`

### Authentication

- Control D API tokens are created in the dashboard and have `Read` or `Write` scope
- tokens are supplied as `Authorization: Bearer <token>`
- tokens may be restricted by allowed IPs

Planning impact:

- the integration should plan for a single API token per config entry
- diagnostics and setup guidance should account for IP-restricted token failures

### Account and profile access

- `GET /users` returns account data for the authenticated token
- the live account payload includes both `id` and `PK`
- `GET /profiles` lists all profiles associated with the account
- profile-modification calls use the profile primary key, documented as `PK`
- Control D response conventions state that successful responses return `success: true` and place returned objects under `body.<controller_name>`
- every unique upstream object uses a primary-key field named `PK`
- public docs describe a profile as a reusable policy container enforced on one or more endpoints

Planning impact:

- the config-entry unique ID should anchor on `GET /users` `body.id`, with `body.PK` retained as a secondary join key because profile and device payloads reference the short account PK through their `user` field
- the profile identifier used for Home Assistant profile devices should come from the API `PK`
- the API client should normalize the Control D response envelope early so manager and entity code does not depend on controller-specific wrapper names
- one authenticated account can expose multiple profiles, which supports the accepted instance-centric config-entry model

### Endpoint or device access

- public product docs use the term `Endpoint`
- API reference uses `/devices` and `device_id` for the same concept
- `GET /devices` lists all endpoints associated with an account or organization
- `PUT /devices/{device_id}` modifies an endpoint
- device modification supports `profile_id` for the primary enforced profile
- device modification supports `profile_id2` for a second enforced profile, and the public docs state up to two profiles for personal use and up to three for organization contexts with a global profile
- live device payloads include both `PK` and `device_id`, and in the inspected account they matched for every endpoint
- live device payloads expose a single nested `profile` object with `PK`, `updated`, and `name`

Planning impact:

- internal integration naming should continue to use `endpoint` while the API client maps that concept to Control D `device` endpoints
- endpoint entity unique IDs should anchor on `device_id`, with `PK` retained as an alias for diagnostics and defensive comparisons
- roaming-endpoint reconciliation must be based on refreshed endpoint-to-profile assignments from the device list
- the live read model currently looks single-profile even though the write contract supports `profile_id2`, so multi-profile endpoints remain an explicit unresolved case that must not be guessed into the first entity model

### Organization behavior

- the Profiles API supports `X-Force-Org-Id` to impersonate a child sub-organization from a parent organization token
- public docs state that organization accounts can manage sub-organizations and global profiles

Planning impact:

- multi-instance support remains the correct baseline
- organization impersonation should be treated as a later explicit design choice, not an implicit part of the first config flow

## Verified product-behavior findings

### Profiles and endpoints

- a profile does nothing by itself until it is enforced on an endpoint
- a single profile can be enforced on one or more endpoints
- endpoints are intended to map 1:1 to physical devices in the product model

Planning impact:

- the accepted Home Assistant model remains valid: profile devices as containers, endpoint entities attached beneath them

### Multiple enforced profiles

- Control D supports multiple enforced profiles on one endpoint
- rule evaluation merges those profiles according to documented rule priority
- the documented rule order is: custom rules, then service rules, then filters, then default rule
- the product behavior is not described as a primary-profile override model; matching is based on the merged rule set across enforced profiles
- schedules are not supported on endpoints that enforce multiple profiles
- the inspected live `GET /devices` payload did not expose any multi-profile endpoint sample or any secondary-profile fields

Planning impact:

- the first implementation should explicitly decide whether it supports multi-profile endpoints at launch or treats them as a constrained case
- endpoint attachment and state derivation must not assume one enforced profile is authoritative for runtime behavior just because the write API names a primary and secondary profile field
- if multi-profile endpoints are included, entity purpose and attachment rules must stay unambiguous

Open interpretation risk:

- the docs clearly define cross-category precedence, but they do not fully specify how conflicts are resolved within the same rule class when multiple enforced profiles both match
- until a live multi-profile sample is available, the integration should avoid presenting synthesized per-endpoint policy state that implies more certainty than the upstream read model provides

## Unverified or unresolved items

### Instance identity anchor

Live inspection exposed two candidate account identifiers on `GET /users`: `id` and `PK`.

`id` is UUID-shaped and separate from user-facing identity fields. `PK` is still important because profile and device payloads reference it through their `user` field.

Required next step:

- implement the config-entry identity contract as `users.id` primary plus `users.PK` secondary unless a later authenticated write or reauth flow proves that assumption wrong

### Pause semantics

- `PUT /profiles/{profile_id}` supports `disable_ttl`
- the reference describes `disable_ttl` as disabling a profile until the specified Unix timestamp
- `disable_ttl = 0` removes a previous deactivation
- live `GET /profiles` payloads expose a top-level `disable` field rather than `disable_ttl`
- in the inspected account, `disable` was present and `null` for every profile

Planning impact:

- `controld_manager.pause_profile` can target the profile resource directly rather than treating pause as an unresolved endpoint-side workaround
- the first implementation should treat pause as a profile disable-until write, with service duration translated into an absolute Unix timestamp
- resume semantics can be modeled by writing `disable_ttl = 0`

Required next step:

- verify from a non-default authenticated sample how disabled profiles are represented when `disable` is populated so entities can reflect paused state after refresh
- confirm whether disabling one profile on a multi-profile endpoint produces any additional endpoint-side status changes worth surfacing

### Entity inventory boundaries

The public docs confirm profiles, endpoints, services, filters, and analytics as product concepts, but they do not determine which subset makes the best first Home Assistant entity surface.

Required next step:

- lock the first entity slice only after live payload examples are available

### Device-to-profile read contract

The inspected live `GET /devices` payload did not return `profile_id` or `profile_id2`. Instead, each endpoint exposed a single nested `profile` object.

Required next step:

- treat nested `device.profile.PK` as the current read-side parent-profile signal for endpoint attachment
- keep multi-profile handling unresolved until a live payload actually exposes how additional enforced profiles are represented on reads

## Planning consequences

- keep the instance-centric config-entry model
- keep profile devices and endpoint entities as the accepted Home Assistant hierarchy
- treat `users.id`, `profile PK`, and `device_id` as the current best primary upstream identifiers
- retain `users.PK` and endpoint `PK` as secondary correlation fields
- treat `pause_profile` as viable for implementation once service input and post-write refresh behavior are locked
- add a first-implementation decision for multi-profile endpoints before entity modeling begins