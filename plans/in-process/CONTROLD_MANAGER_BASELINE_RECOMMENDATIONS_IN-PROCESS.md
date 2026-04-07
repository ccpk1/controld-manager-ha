# Control D Manager baseline recommendations

## Initiative snapshot

The architecture and standards baseline is now locked around one Home Assistant config entry per authenticated Control D instance, one Home Assistant device per profile, and endpoint entities attached to profile devices.

This plan now focuses on the remaining work required to validate the Control D API contract and build the runtime in a sequence that preserves those decisions.

The target direction solves four concrete problems:

- users should enter one API credential set once per Control D instance
- multiple Control D instances must coexist cleanly in one Home Assistant deployment
- one integration service surface should be able to target any supported Control D entity, device, profile, or the entire instance without duplicate entry setup
- the implementation must avoid Home Assistant device-registry bloat by modeling physical clients as endpoint entities instead of Home Assistant devices

Implementation standard:

- all build work must target a platinum-quality Home Assistant integration posture, even where the repository honestly leaves `quality_scale.yaml` items as `todo` until behavior exists

## Scope and non-goals

This plan covers:

- API validation work that must happen before implementation can proceed honestly
- the runtime build sequence for coordinators, managers, devices, entities, and services
- the implementation checkpoints needed to preserve the accepted architecture
- late-phase evaluation points for optional compatibility and tamper-oriented features

This plan does not cover:

- unverified Control D endpoint contracts
- final write-action schemas before the API is confirmed
- a complete entity catalog for every profile field
- speculative hierarchy beyond what Home Assistant and the Control D API can support cleanly
- the late-phase Pi-hole compatibility and tamper-oriented add-ons unless their value and API fit are explicitly validated

Latest approved direction:

- the next implementation slice should follow the Firewalla Local options-flow and menu posture closely
- all discovered profiles should be included by default when a config entry is created
- users must be able to exclude any profile later through the options flow without deleting the config entry
- profile-specific exposure policy should live under immutable profile IDs in `ConfigEntry.options`
- filters should be auto-created for every included profile and should rely on entity-registry defaults rather than per-item options storage
- services should be exposed by per-profile category policy and should default to disabled when category-created
- rules should be exposed by explicit per-profile selection using typed rule identities
- endpoint status should be a compact opt-in surface with a configurable per-profile activity threshold
- the first dedicated profile-option slice should always create and enable, for
	each included profile:
	- one Default Rule select using Control D terms `Blocking`, `Bypassing`, and
	  `Redirecting`
	- one AI Malware Filter select with `Off`, `Minimal`, `Standard`, and
	  `Aggressive`
	- one Safe Search toggle
	- one Restricted Youtube toggle
- the edit-profile form should gain one per-profile advanced-options exposure
	flag; when enabled, the remaining profile-option entities for that profile
	should be created in disabled-by-default entity-registry state

## Execution guardrails

These guardrails are mandatory for the builder.

- no production-code deviation from this plan is allowed without written justification and explicit approval
- if implementation discovers a conflicting API behavior, stop, document the conflict, update the supporting note, and request approval before changing direction
- every code change must remain aligned with:
	- `docs/ARCHITECTURE.md`
	- `docs/DEVELOPMENT_STANDARDS.md`
	- `docs/ENGINEERING_FINDINGS.md`
	- `custom_components/controld_manager/quality_scale.yaml`
- all new behavior must be typed, translation-ready, and entry-scoped
- suppressions, fallback identity behavior, and API guesswork are forbidden unless the repository first records why no compliant alternative exists
- each implementation phase must end with the required validations and a short variance report stating whether the work matched the plan exactly

Required validation discipline:

- run `python -m ruff check .`
- run `python -m ruff format .`
- run `python -m mypy custom_components/controld_manager`
- run `python -m pytest tests/ -v`
- if a narrower validation scope is used during iteration, the final phase report must state the exact narrower scope and the reason

Required review discipline:

- no phase is complete until architecture, standards, and quality-scale impacts are reviewed explicitly
- `quality_scale.yaml` must be updated only to reflect actual behavior delivered in code
- any unresolved gap must be recorded as follow-up work instead of silently deferred

## Open questions or external dependencies

- How should the runtime normalize attached-profile sibling fields such as `profile`, `profile2`, and possible future variants while keeping organization cases open?
- What mutation rate limits, write consistency guarantees, and rollback behavior apply when one service targets multiple profiles or the whole instance?
- Does the API support bulk operations natively, or will the integration need manager-level fan-out across multiple profile targets?
- Should billing product and analytics-region metadata remain diagnostics-only, or should some of it surface on the instance system device?
- Should profile disable or enable behavior and any later policy-level disable
	behavior ultimately share one service family with typed target resolution, or
	should profile, filter, and service service surfaces remain separate?
- What immutable typed identity should be stored for grouped-rule selections so folders and rule rows survive renames cleanly?
- Should the endpoint activity threshold be stored only per profile, or should the options flow also support an entry-wide default that profiles may inherit?

## Phase summary table

| Phase | Status | Goal | Primary files | Exit outcome |
| --- | --- | --- | --- | --- |
| 1 | Complete | Lock the lexicon, hierarchy, and manager architecture | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `docs/QUALITY_REFERENCE.md`, `README.md` | Durable docs agree on the instance-centric model and minimum manager set |
| 2 | Complete | Validate instance identity, API topology, and polling design | `custom_components/controld_manager/api/`, `custom_components/controld_manager/models.py`, tests, supporting notes if needed | Verified instance anchor, normalized read contract, deterministic multi-profile attachment policy, disable-state refresh contract, and dynamic polling contract, with deeper analytics research explicitly deferred as non-blocking follow-up |
| 3 | Complete | Build the entry-scoped runtime and lifecycle managers | `custom_components/controld_manager/__init__.py`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/`, `custom_components/controld_manager/entity.py` | One config entry owns one runtime with manager-backed device and entity lifecycle control |
| 4 | Complete | Add conservative entities, shared services, and later add-on evaluation | platform files, `services.yaml`, translations, tests, optional supporting notes | Stable profile devices, endpoint entities, shared service targeting, and documented late-phase add-on decisions |
| 5 | Complete | Add scalable per-profile options policy and high-cardinality profile surfaces | `config_flow.py`, `models.py`, manager layer, platform files, translations, tests, plan docs | Menu-driven options flow, per-profile inclusion and exposure policy, auto-created filters, category-driven service exposure, typed rule selection, and endpoint-status threshold support |
| 6 | In progress | Add a shared mutation-service layer with Control D terminology and multi-entry-safe targeting | `__init__.py`, `services.yaml`, `const.py`, manager helpers, translations, tests, plan docs | A small reusable service family supports flexible profile-scoped actions without one custom service per entity type |

## Immediate implementation kickoff

This is the shortest practical path from planning into runtime work.

1. Apply the approved Phase 2 closeout decisions for refresh groups, first entity slice, paused-profile read normalization, and attached-profile sibling normalization.
2. Define the entry-scoped runtime contract in `custom_components/controld_manager/models.py` for the API client, refresh-group owners, normalized registries, and manager objects.
3. Build the async API client skeleton in `custom_components/controld_manager/api/` around the validated envelope and identity contracts.
4. Rework `custom_components/controld_manager/config_flow.py`, `custom_components/controld_manager/__init__.py`, and `custom_components/controld_manager/coordinator.py` so one config entry creates one runtime and one coordinator-owned refresh system.
5. Add manager skeletons under `custom_components/controld_manager/managers/` and boundary tests that lock ownership before entity platforms are added.

Builder handoff:

- use `plans/in-process/CONTROLD_MANAGER_BASELINE_RECOMMENDATIONS_SUP_BUILDER_HANDOFF.md` as the execution brief for the first build pass

## Completed implementation slice

Phase 5 is complete.

Current status update:

- config flow and user-selection behavior are now broadly implemented for the
	currently approved scope:
	- per-profile include or exclude policy
	- per-profile advanced-options exposure flag
	- per-profile service-category selection
	- explicit custom-rule and folder selection
	- endpoint-status opt-in controls
- the profile edit form has been polished so high-cardinality service exposure
	and custom-rule choices stay grouped ahead of the endpoint controls, while the
	endpoint controls now remain at the bottom of the form
- the profile-edit wording now explicitly reflects that category-created
	service entities are created disabled by default because some categories can
	create a large number of entities
- the first approved always-on profile-option slice is now implemented for each
	included profile:
	- Default Rule select
	- AI Malware Filter select
	- Safe Search toggle
	- Restricted Youtube toggle
- grouped custom rules now support both folder-level mode entities and
	explicit child-rule toggle entities when selected
- dynamic entity lifecycle cleanup is now handled by stable unique ID against
	the Home Assistant entity registry, not only by in-memory live entities
- removed custom rules, removed rule folders, and other no-longer-desired
	dynamic entities are now pruned correctly from the entity registry during
	reconciliation

Remaining follow-on scope after the current slice:

- broader advanced profile options remain intentionally partial and should stay
	in a follow-on slice until their read and write semantics are fully closed
- `ecs_subnet` remains intentionally excluded from entity exposure
- TTL-style options remain intentionally limited to advanced toggle behavior
	rather than editable numeric controls
- the next implementation phase should focus on the shared service layer,
	including renaming profile pause or resume terminology to Control D-aligned
	enable profile and disable profile behavior

### Phase 5: Add scalable per-profile options policy and high-cardinality profile surfaces

- [x] Rework `custom_components/controld_manager/config_flow.py` so the options flow follows the Firewalla Local pattern: top-level menu, one live profile selector, one focused per-profile edit form, and one integration-settings form.
- [x] Add a typed `ConfigEntry.options` contract in `custom_components/controld_manager/models.py` and related helpers that stores compact exposure policy keyed by immutable profile identifier.
- [x] Implement profile inclusion policy so all discovered profiles are included by default on first setup and any profile may later be excluded without deleting the config entry.
- [x] Add the service catalog reads needed to evaluate `GET /services/categories`, `GET /services/categories/all`, and any required follow-on filtering contract before service entities are generated.
- [x] Implement auto-created filter entities for every included profile, including both switches and selects for modal filters, and assign entity-registry defaults so only the curated core filter subset is enabled by default.
- [x] Implement per-profile service-category policy and generate service switches dynamically from the current catalog, defaulting newly created category-driven entities to disabled unless the user opts into the advanced default-enabled override.
- [x] Implement typed per-profile custom-rule exposure using the proven `groups`, `rules`, and `rules/all` contracts so only explicitly selected folders or domains become Home Assistant entities.
- [x] Implement the first endpoint status surface as an opt-in endpoint entity with attributes, using a per-profile activity-threshold option bounded to 5 to 60 minutes and defaulting to 15 minutes if no stronger upstream status contract is proven.
- [x] Add focused tests for menu navigation, persisted per-profile policy, profile inclusion or exclusion behavior, service-category defaults, grouped-rule persistence, and endpoint-threshold behavior.
- [x] Close the dynamic entity lifecycle gap so removed rules, removed rule folders, and other no-longer-desired dynamic entities are removed from the Home Assistant entity registry by stable unique ID during reconciliation.
- [x] Polish the profile-edit options form so `Expose endpoint sensors` and the
	endpoint inactivity threshold remain the last two fields, and clarify that
	service-category-created entities default to disabled state because category
	counts can be high.

### Phase 6: Add a shared mutation-service layer and align profile terminology

- [x] Implement Control D-aligned profile services `disable_profile` and
	`enable_profile`, and update user-facing text to match the Control D
	wording `Temporarily disable all filters, services and rules.`
- [x] Define one shared target-resolution helper path for services so every
	service can safely resolve exactly one loaded config entry and one or more
	profiles without duplicating logic.
- [ ] Keep routine entity actions on native Home Assistant entity services and
	add only a small set of integration services where they provide real value,
	such as bulk targeting, profile-wide actions, or operations that are not a
	natural fit for a single entity.
- [x] Prefer capability-based service families over one service per toggle or
	option so the integration remains compact while still supporting future
	profile options, filters, services, rules, and rule-folder actions.
- [x] Ensure every custom service is translation-ready, multi-entry safe, and
	validated through manager-owned mutation paths rather than direct entity or
	API-layer payload construction.
- [x] Add reusable service-schema and resolution helpers where the same config
	entry, profile, or item-target selection pattern repeats across services.
- [x] Update `services.yaml`, translations, and tests so the final service
	surface is documented, localized, and aligned with platinum-quality Home
	Assistant patterns.
- [x] Add the capability-style filter mutation service `set_filter_state`, and
	resolve filters by raw key or user-facing name across the selected profile
	targets.
- [x] Keep external or 3rd-party filters loaded in runtime for service writes
	even when their entities stay hidden, and expose them only through a
	per-profile `Expose 3rd-party filters` option with disabled-by-default
	entity-registry posture.

Current Phase 6 service posture:

- `enable_profile` and `disable_profile` now share the same explicit profile
	targeting contract
- both services require at least one explicit profile selector rather than
	falling back to all profiles in a single loaded entry
- both services accept `profile_id` and `profile_name`, with `profile_id`
	taking precedence when both are supplied
- both services keep `config_entry_id` and `config_entry_name` as optional
	multi-entry disambiguators, with `config_entry_id` taking precedence
- both services reject generic `entity_id` targets and reject the Control D
	account device as a profile target
- the shared profile-target helper path is now the expected reuse base for any
	future profile-scoped bulk service

Phase 5 required research closeouts before code for that specific surface starts:

- prove the best persisted typed identity for grouped rules
- confirm whether endpoint status remains timestamp-derived or gains a stronger upstream signal

Additional follow-on work discovered after Phase 5 completion:

- main profile-option controls from the full Control D profile page remain
	partially unimplemented and should be treated as a separate detail-driven
	follow-on slice, beginning with the dedicated default-rule endpoint
	`/profiles/{profile_id}/default`
- browser-backed captures now also prove a second dedicated family under
	`/profiles/{profile_id}/options/{option_key}` with at least three payload
	shapes: boolean toggles, enabled-plus-value controls, and unresolved TTL-style
	controls
- browser-backed captures also prove a global discovery catalog at
	`GET /profiles/options`, which provides stable option keys, upstream titles,
	types, defaults, and documentation links but not per-profile current state
- browser-backed captures now strongly indicate per-profile current state is
	read from `GET /profiles/{profile_id}/options`, with a sparse list of option
	keys and active values that must be joined to the global catalog
- browser-backed captures now also prove that `ecs_subnet` uses concrete value
	mappings `0` and `1`, and that `ttl_blck` is an enabled numeric field whose
	disable state collapses to `value = 0`
- browser-backed captures now also prove the default-rule read contract at
	`GET /profiles/{profile_id}/default`, and the repository now implements that
	surface as the first always-on profile-option select

Current approved execution target for that slice:

- ship a small always-on option surface first:
	- Default Rule select
	- AI Malware Filter select
	- Safe Search toggle
	- Restricted Youtube toggle
- add a per-profile advanced-options flag in the edit-profile form
- create the remaining profile-option entities only when that flag is enabled,
	and register those additional entities as disabled by default
- keep `ecs_subnet` out of entity exposure for now
- surface TTL options only as advanced toggles, not as editable numeric
	controls

## Per-phase details with checkboxes

### Phase 1: Lock the lexicon, hierarchy, and manager architecture

- [x] Update `docs/ARCHITECTURE.md` with the official lexicon so `config entry`, `device`, `entity`, `profile`, and `endpoint` have one unambiguous meaning.
- [x] Update `docs/DEVELOPMENT_STANDARDS.md` so the minimum manager set is explicit: `BaseManager`, `IntegrationManager`, `DeviceManager`, `EntityManager`, `ProfileManager`, and `EndpointManager`.
- [x] Update `docs/QUALITY_REFERENCE.md` so quality gates encode instance-scoped entries, profile devices, endpoint-entity-only modeling, and roaming-endpoint lifecycle behavior.
- [x] Update `README.md` so the public product shape no longer implies profile-per-entry setup.
- [x] Record that the only planned Home Assistant devices are one instance system device plus one device per Control D profile, while physical endpoints remain entities.

### Phase 2: Validate instance identity, API topology, and polling design

- [x] Verify which Control D API field from `GET /users` can serve as the immutable config-entry unique ID for one instance and document the fallback strategy if no dedicated instance identifier exists.
- [x] Verify the profile inventory contract and endpoint topology at the public-doc level: profiles are listed separately, endpoints are exposed in the API as `/devices`, endpoint modification uses `device_id`, and profile assignment uses `profile_id` and `profile_id2`.
- [x] Verify the live read-envelope contract: `/users` returns `body` directly, `/profiles` returns `body.profiles`, and `/devices` returns `body.devices`.
- [x] Benchmark Control D polling needs against integrations such as NextDNS and Firewalla Local and lock a dynamic refresh-group design whose per-group intervals can be tuned through bounded options-flow settings.
- [x] Lock the initial entity inventory for the instance system device, profile devices, and endpoint entities before platform code begins so device-registry growth stays intentional, using `GET /profiles` as the summary discovery source and profile-scoped list endpoints as the detailed source for item-level controls.
- [x] Defer exhaustive regional analytics-surface decisions such as `v2/statistic/count`, `v2/statistic/count/triggerValue`, `v2/statistic/count/question`, and `v2/statistic/count/srcCountry` to a later analytics follow-up, while keeping the approved first entity slice conservative and avoiding speculative default entity commitments.
- [x] Decide whether endpoint-scoped summary analytics should join the initial entity model alongside profile and instance analytics, now that `endpointId[]` samples show derivable top-level metrics such as total traffic, encrypted-DNS ratio, and home-country ratio.
- [x] Lock the refreshed-read contract for profile disable and enable behavior,
	including normalization of `disable` and `disable_ttl` into one
	paused-until representation and what profile state Phase 3 may represent
	after refresh.
- [x] Capture the current API uncertainties and verified public-doc findings in a supporting note because they materially affect implementation sequencing.
- [x] Declare the deterministic multi-profile endpoint attachment policy: always create the endpoint entity under the first attached upstream profile exposed by the published API payload.
- [x] Define the runtime data needed to execute that policy honestly at the current two-profile level: derive enforced-profile membership from attached device fields such as `profile` and `profile2`, use `profile` as the owning Home Assistant profile device, and keep additional attached profiles as normalized metadata.
- [x] Define the generic normalization rule for attached-profile sibling fields so the runtime stays open to possible organization cases such as `profile3` without changing the profile-1 ownership rule.
- [x] Lock the profile discovery contract: use `GET /profiles` for summary counts and option discovery, and use profile-scoped list endpoints for services, filters, and rule detail only when the selected entity model needs them.
- [x] Lock endpoint discovery boundaries for Firewalla-managed child clients: explicit endpoint inventory remains authoritative, and child clients must not be inferred from parent metadata alone.
- [x] Defer final verification of the regional `/v2/client` analytics contract until the runtime foundation exists, keeping child-client analytics enrichment out of the initial runtime contract.
- [x] Defer exhaustive verification of the regional `/v2/statistic/count`, `/v2/statistic/count/triggerValue`, `/v2/statistic/count/question`, and `/v2/statistic/count/srcCountry` contracts to a later analytics follow-up because they are non-blocking to runtime scaffolding.
- [x] Defer final verification of the derived security-overview metric contract, including exact `Benign Blocks` denominator behavior, to a later analytics follow-up.
- [x] Defer broader dashboard-backed API inspection for endpoint, profile, service, filter, and rule pages until after the runtime foundation is stable.
- [x] Lock the first paired mutation-service direction around profile-wide
	enable or disable behavior, while deferring the broader shared target-family
	decision for filter, service, rule, and option services to the later service
	phase.

Phase 2 to Phase 3 gate:

- Phase 3 does not begin until the repo has frozen `users.id` as the config-entry anchor, `users.PK` as the secondary join key, profile `PK` as the profile-device anchor, `device_id` as the endpoint anchor with endpoint `PK` as an alias, the endpoint-specific read envelopes, the pause refresh behavior, the profile-1 multi-profile attachment rule, and the dynamic refresh-group options contract.

Phase 2 required artifacts:

- updated supporting note with every newly verified API contract
- an approved first entity slice
- an approved refresh-group table with default, minimum, and maximum intervals
- an approved runtime normalization note for attached profile sibling fields and paused-profile reads

Phase 2 deferred follow-up scope:

- analytics host-selection refinement from `stats_endpoint`
- `/v2/client` correlation against `/devices`
- exhaustive analytics count and ranking contract verification
- derived security-overview denominator verification
- broader dashboard-backed API inspection
- exact later service-family split or unification for profile, filter, service, rule, and option disable semantics

Approved Phase 2 closeout decisions:

- refresh groups:
	- `configuration_sync`
	- `profile_analytics`
	- `endpoint_analytics`
- refresh-group defaults:
	- `configuration_sync = 15 minutes`
	- `profile_analytics = 5 minutes`
	- `endpoint_analytics = 5 minutes`
- refresh-group bounds:
	- minimum `5 minutes`
	- maximum `60 minutes`
- first entity slice:
	- instance system device: minimal instance metadata only when already supported cleanly by validated runtime data
	- profile devices: limited summary analytics and clean profile pause state only if the pause contract is implemented end to end
	- endpoint entities: small telemetry surface only
	- excluded from the first slice: per-filter, per-service, per-domain, and per-country entities
- paused-profile read normalization:
	- normalize upstream read variants into `paused_until: datetime | None`
	- derive paused state from that typed field only
- attached-profile sibling normalization:
	- normalize attached profile objects such as `profile`, `profile2`, and future siblings into one ordered `attached_profiles` list
	- preserve upstream order
	- the first attached profile is the owning Home Assistant profile device
	- later attached profiles remain supplemental membership metadata only

Phase 3 first-pass output:

- a working config entry that authenticates once and stores one entry-scoped runtime
- a coordinator-owned refresh path that can fetch and normalize users, profiles, and devices
- manager skeletons with clear ownership boundaries
- tests that lock identity anchors, envelope normalization, and manager ownership before entity platforms expand

Phase 3 review gate:

- once real runtime fetch paths exist, review whether any data currently assigned to `profile_analytics` or `endpoint_analytics` is already sourced by the faster `configuration_sync` path
- if the data is already available from the faster path with no material performance cost, reassign it to the faster refresh group instead of preserving a slower interval without benefit
- any refresh-group reassignment must be documented with the data-source evidence and approved before the polling contract changes

### Phase 3: Build the entry-scoped runtime and lifecycle managers

- [x] Implement the async API client under `custom_components/controld_manager/api/` so one authenticated session can enumerate the full instance inventory without duplicating credentials per profile.
- [x] Rework `custom_components/controld_manager/config_flow.py` so the user authenticates once, the flow validates the instance, and duplicate prevention is based on the immutable instance identifier.
- [x] Replace the current placeholder runtime shape with an entry-scoped runtime contract in `custom_components/controld_manager/coordinator.py` and `custom_components/controld_manager/models.py` that supports dynamic split polling, indexed registries, manager attachment, and options-backed per-group intervals.
- [x] Add `custom_components/controld_manager/managers/` implementations for the required minimum manager set, with clearly separated responsibilities for shared lifecycle, device lifecycle, entity lifecycle, profile logic, and endpoint logic, and implement the profile-1 multi-profile endpoint attachment policy inside the runtime reconciliation path.
- [x] Update `custom_components/controld_manager/__init__.py` and `custom_components/controld_manager/diagnostics.py` so setup, unload, reload, and diagnostics all reflect one entry with many managed profiles and one stored credential set.
- [x] Add boundary tests that prove config-entry writes remain coordinator-owned, manager responsibilities do not overlap, and runtime state stays entry-scoped.

Phase 3 required validations:

- all repository validation commands
- focused tests that prove one config entry produces one runtime
- focused tests that prove normalized users, profiles, and devices can be loaded without entity platforms
- focused tests that prove manager ownership boundaries

### Phase 4: Add conservative entities, shared services, and later add-on evaluation

- [x] Build the shared entity base in `custom_components/controld_manager/entity.py` so unique IDs, translation placeholders, purpose metadata, availability, and device attachment logic are centralized.
- [x] Add the smallest useful entity set first: instance summary sensors, profile-level pause switches, and endpoint last-active telemetry entities from the documented inventory surface.
- [x] Implement roaming-endpoint reconciliation so the entity manager updates an endpoint entity's parent profile device during refresh when profile membership changes, including profile-1 ownership for multi-profile endpoints.
- [x] Register shared services only after manager write paths exist, including first-pass `controld_manager.disable_profile` and `controld_manager.enable_profile` services and a target-resolution path that supports `entity_id`, `device_id`, and `config_entry_id` safely.
- [x] Evaluate whether profile, filter, and service disable semantics can share one typed target-resolution family without making service validation ambiguous; keep profile disable and enable as the explicit first service pair and defer broader filter, service, rule, and option mutation services to a later follow-on pass.
- [x] Evaluate the Pi-hole compatibility option and the later tamper-oriented features only after the core runtime is stable, and capture an explicit deferral note: keep both out of the current implementation until the profile and endpoint surfaces mature.
- [x] Reassess `custom_components/controld_manager/quality_scale.yaml` only after the runtime, entity lifecycle, and service contracts exist in working code.

Phase 4 required validations:

- all repository validation commands
- focused entity tests for device attachment, availability, and unique-ID stability
- focused service tests for scope enforcement and error handling
- diagnostics tests proving redaction and entry-scoped output

## Validation strategy

Use the normal repository checks during implementation work, but do not treat them as complete until the relevant behavior exists:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`

Implementation review should explicitly confirm:

- one config entry is created per verified Control D instance
- credentials are not duplicated across profile surfaces
- physical endpoints do not create Home Assistant devices
- devices and entities remain stable when profile names change
- roaming endpoints move to the correct profile device without an integration reload
- service dispatch cannot accidentally cross instance boundaries unless the contract explicitly allows it
- coordinator-owned writes, manager-owned orchestration, and shared registry use remain intact

## References

- Firewalla Local for repository standards, minimum manager architecture, shared entity patterns, and multi-instance runtime discipline
- NextDNS for cloud DNS integration patterns, profile inventory discovery, and split refresh tradeoffs
- AdGuard Home for explicit mutation-oriented service patterns when Control D write operations are verified
- Pi-hole for user-facing bulk or temporary-action ergonomics when the Control D API supports them
- `plans/in-process/CONTROLD_MANAGER_BASELINE_RECOMMENDATIONS_SUP_API_DISCOVERY.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/ENGINEERING_FINDINGS.md`
- `docs/QUALITY_REFERENCE.md`