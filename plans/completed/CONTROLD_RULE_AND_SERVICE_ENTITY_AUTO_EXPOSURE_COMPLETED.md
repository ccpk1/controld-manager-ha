# Service and rule entity auto-exposure

Status: Completed and archived after implementation, release preparation, and full validation for version 1.2.0.

## 1. Initiative snapshot

- Goal: add two profile-level exposure behaviors that keep the entity model aligned with current Control D relevance signals without removing the existing manual exposure paths.
- Service direction: add a `Manual` or `Automatic` profile-level service exposure mode, with `Automatic` enabled by default, so Home Assistant can create entities for explicit profile service rows while excluding categories already managed manually.
- Rule direction: keep the existing custom-rule selector, but add a reserved selector option, `Expose all rules as entities`, that auto-exposes all live rule folders and custom rules for the profile and cannot be combined with manual selections.
- Confirmed service eligibility anchor for this initiative: a service qualifies for auto-exposure when it is present in the profile services response as an explicit service rule row, even if its current mode is Off.
- Upstream product signal: Control D v2.0.14 release notes state, `Updated the Services page to see and access relevant Services more easily`, which supports aligning Home Assistant exposure with profile-relevant service rows instead of only full category mirroring.

## 2. Scope and non-goals

### In scope

- Treat `docs/DEVELOPMENT_STANDARDS.md` as a mandatory acceptance contract for this initiative, not just reference guidance.
- Treat applicable Home Assistant platinum-quality expectations as mandatory acceptance criteria for this initiative, including strict typing, translation-backed user-facing strings, disciplined constant usage, diagnostics hygiene, and complete validation.
- Add a typed per-profile service exposure mode to the stored options contract.
- Extend service registry shaping so profile services can be exposed from the union of:
	- explicit category selections
	- auto-managed explicit service rows for categories not already selected manually
- Preserve current category-based service exposure behavior and current service write behavior.
- Add a reserved custom-rule selector option that means `Expose all rules as entities`.
- Validate that the reserved all-rules option is mutually exclusive with manual rule or folder selections.
- Extend rule entity shaping so the reserved all-rules option exposes all current live rule folders and all current live custom rules for the profile.
- Add options-flow, runtime, and entity-lifecycle tests for both behaviors.
- Update translations, diagnostics, architecture notes, and user-facing docs.

### Non-goals

- Do not remove or replace the current `allowed_service_categories` behavior.
- Do not add `add only` service persistence behavior in this initiative.
- Do not introduce a second top-level rule mode control if the existing selector can carry the all-rules sentinel cleanly.
- Do not mirror full service or rule catalogs into `ConfigEntry.options`.
- Do not persist a copied list of auto-managed service IDs or rule IDs as profile policy.
- Do not change the existing Home Assistant service-layer capability to resolve and mutate non-exposed services or rules.
- Do not broaden entity scope beyond profile-owned services, rule folders, and custom rules already supported by the current runtime.

## 3. Open questions or external dependencies

- Service exposure defaults are intentionally broadened in this initiative:
	- new entries default to `automatic`
	- existing entries migrate to `automatic`
	- release notes and user-facing docs must call out the resulting entity churn explicitly
- The stored service exposure values should be finalized up front. Recommended values: `manual` and `automatic`.
- The reserved rule sentinel should use a collision-proof stored key, not the display label. Recommended shape: a namespaced internal token such as `system:all_rules`.
- The current Control D API is unversioned. The plan assumes `GET /profiles/{profile_pk}/services` remains the authoritative source for explicit service-rule rows and continues to include rows whose current mode is Off.
- Automatic service exposure must remain compact-policy driven:
	- store only the profile mode plus the existing manual category selections
	- derive the live automatic service set from the current profile services response on each refresh
	- let `entity_manager.py` reconcile additions and removals against the current desired set and the Home Assistant entity registry
- Category-managed and automatic service entities should currently share the same entity type and identity pattern; only their inclusion path differs.

## 4. Phase summary table

| Phase | Outcome | Primary files |
| --- | --- | --- |
| 1 | Finalize stored policy, selector contract, rollout defaults, and validation rules | `custom_components/controld_manager/const.py`, `custom_components/controld_manager/models.py`, `custom_components/controld_manager/config_flow.py`, `custom_components/controld_manager/diagnostics.py`, `tests/components/controld_manager/test_config_flow.py`, `tests/components/controld_manager/test_runtime.py` |
| 2 | Implement layered automatic service exposure on top of manual categories | `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/integration_manager.py`, `custom_components/controld_manager/managers/entity_manager.py`, `custom_components/controld_manager/select.py`, `custom_components/controld_manager/translations/en.json`, `tests/components/controld_manager/test_runtime.py`, `tests/components/controld_manager/test_phase4.py` |
| 3 | Implement all-rules sentinel exposure and mutually exclusive validation | `custom_components/controld_manager/config_flow.py`, `custom_components/controld_manager/models.py`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/entity_manager.py`, `custom_components/controld_manager/translations/en.json`, `tests/components/controld_manager/test_config_flow.py`, `tests/components/controld_manager/test_phase4.py` |
| 4 | Document behavior, diagnostics visibility, and release-safe rollout semantics | `README.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`, `custom_components/controld_manager/quality_scale.yaml` |
| 5 | Post-completion follow-up: replace registry-heuristic service defaults with provenance-aware persistence | `custom_components/controld_manager/models.py`, `custom_components/controld_manager/config_flow.py`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/entity_manager.py`, `custom_components/controld_manager/diagnostics.py`, `docs/ARCHITECTURE.md`, `tests/components/controld_manager/test_runtime.py`, `tests/components/controld_manager/test_phase4.py` |

## 5. Per-phase details with checkboxes

### Phase 1. Finalize policy and selector contracts

- [x] Add new profile-policy constants in `custom_components/controld_manager/const.py` for the service exposure field and its allowed values `manual` and `automatic`.
- [x] Extend `ControlDProfilePolicy` in `custom_components/controld_manager/models.py` so service exposure round-trips as a typed per-profile field without storing any mirrored service rows or copied service-ID lists.
- [x] Keep the existing `exposed_custom_rules` storage field, but reserve one internal token for `Expose all rules as entities` and document that it cannot be mixed with other target values.
- [x] Update `custom_components/controld_manager/config_flow.py` so the per-profile form shows a two-choice service exposure selector immediately above `Allowed service categories`, using `Manual` and `Automatic` as the user-facing choices, and injects the all-rules sentinel as the first custom-rule selector option.
- [x] Add options-flow validation that rejects any custom-rule selection set containing both the all-rules sentinel and one or more explicit folder or rule targets.
- [x] Define the migration behavior in the coordinator-owned config-entry write path so existing entries receive the new default `automatic` service mode intentionally instead of only through passive read-time defaults.
- [x] Update `custom_components/controld_manager/diagnostics.py` so diagnostics expose the new service auto-exposure mode and clearly surface whether the all-rules sentinel is active for a profile.
- [x] Add focused tests in `tests/components/controld_manager/test_config_flow.py` and `tests/components/controld_manager/test_runtime.py` for policy round-trip, form defaults, and invalid mixed all-rules selections.

### Phase 2. Layer automatic service exposure on top of manual categories

- [x] Update `custom_components/controld_manager/coordinator.py` so profile detail fetches include services when either the manual category list is non-empty or the new service exposure mode is `automatic`.
- [x] Refactor service normalization in `custom_components/controld_manager/managers/integration_manager.py` so the service registry is built from the union of:
	- all services from manually allowed categories
	- all explicit live service-rule rows whose categories are not already manually selected
- [x] Preserve category exclusion precedence so a service from a manually selected category is owned only by the manual category path and never double-counted by the auto-managed path.
- [x] Keep automatic service exposure manager-derived rather than storage-derived: the runtime should recompute the desired automatic service set from the current profile services response on each refresh and should not persist copied live service identifiers in options or policy models.
- [x] Update `custom_components/controld_manager/managers/entity_manager.py` so service entity reconciliation removes automatic-service entities that are no longer justified when upstream service rows disappear or when profile policy changes from `automatic` to `manual`, while preserving services still justified by selected categories.
- [x] Preserve the existing write-time live service normalization helper so Home Assistant services continue to target services outside the entity surface when explicitly requested.
- [x] Update `custom_components/controld_manager/select.py` only as needed so automatic and category-managed services preserve one stable entity identity and one stable entity type, with inclusion controlled by policy rather than by alternate unique-ID schemes.
- [x] Add translated selector labels and descriptions in `custom_components/controld_manager/translations/en.json` that explain the new service exposure control, its overlap rule with categories, and the removal behavior when a service stops appearing in the profile services response or when the profile switches back to `manual`.
- [x] Add runtime and end-to-end tests in `tests/components/controld_manager/test_runtime.py` and `tests/components/controld_manager/test_phase4.py` for:
	- `manual` mode preserving current behavior
	- `automatic` mode exposing explicit service rows even when current mode is Off
	- exclusion of services whose categories are manually selected
	- removal of auto-managed service entities when the live profile services response drops a row
	- removal of no-longer-justified automatic-service entities when profile policy changes from `automatic` to `manual`
	- safe coexistence with the existing service mutation services

### Phase 3. Add all-rules sentinel exposure

- [x] Add a reserved all-rules target in the rule-target choice builder used by `custom_components/controld_manager/config_flow.py`, with the user-facing label `Expose all rules as entities` and a translation-backed description.
- [x] Extend `ControlDProfilePolicy.exposed_rule_identities` and `ControlDProfilePolicy.exposed_rule_group_pks` in `custom_components/controld_manager/models.py` so the all-rules sentinel resolves to every live rule identity and every live rule-group identifier for the profile.
- [x] Update `custom_components/controld_manager/coordinator.py` so profile detail fetches include rules whenever either explicit custom-rule selections exist or the all-rules sentinel is active.
- [x] Keep `custom_components/controld_manager/managers/entity_manager.py` as the single source of desired rule and rule-group entity keys, relying on the updated policy helpers instead of introducing a second rule exposure path.
- [x] Update `custom_components/controld_manager/managers/entity_manager.py` so policy transitions from the all-rules sentinel back to explicit manual targets, or to no targets at all, remove stale rule and rule-group entities while preserving any still justified by the remaining explicit selections.
- [x] Add config-flow validation tests in `tests/components/controld_manager/test_config_flow.py` that prove the all-rules sentinel cannot be combined with explicit folder or rule targets and that the error remains user-actionable.
- [x] Add end-to-end tests in `tests/components/controld_manager/test_phase4.py` that prove the sentinel causes all live rule folders and custom rules to appear with the same entity types they would have under manual selection, and that removed upstream rules are removed from Home Assistant automatically.
- [x] Add runtime coverage in `tests/components/controld_manager/test_runtime.py` for sentinel-based policy resolution, including the case where a previously valid explicit rule target disappears from the live profile detail payload.

### Phase 4. Document rollout, semantics, and operator guidance

- [x] Update `docs/ARCHITECTURE.md` narrowly so the compact category-based service model is extended, not replaced: manual category exposure remains valid, while automatic service exposure adds a second manager-derived inclusion path based on current profile service rows.
- [x] Update `docs/ARCHITECTURE.md` to explain that custom-rule exposure remains opt-in and can now be satisfied either by explicit manual selection or by the reserved all-rules sentinel, but never both at once.
- [x] Update `README.md` and `docs/USER_GUIDE.md` with concise operator guidance for when to use `Manual` service exposure, `Automatic` service exposure, explicit custom-rule picks, and `Expose all rules as entities`.
- [x] Review `custom_components/controld_manager/quality_scale.yaml` only for accuracy; do not claim any new behavior as complete unless the options flow, runtime shaping, tests, translations, and docs all land together.
- [x] Record rollout guidance in the docs and release notes so users understand that automatic service exposure is now the default for both migrated and newly created entries.
- [x] Perform a final code review against `docs/DEVELOPMENT_STANDARDS.md`, the applicable Home Assistant platinum-quality standards, and this plan, working in reverse from the finished diff to confirm constants, translations, typing, layer boundaries, diagnostics, tests, docs, and cleanup behavior all meet the required contract before the initiative is considered complete.

## 5a. Current implementation status

- Phases 1 through 4 are implemented in code and documentation.
- Architecture, development standards, README, user guide, release metadata, and release-note draft now all reflect automatic service exposure and the all-rules sentinel contract.
- Focused validation and full repository validation are complete: config-flow, targeted runtime coverage, targeted phase4 coverage, `quick_lint`, `ruff`, `mypy`, and the full `pytest tests/ -v` suite now pass.
- Test-only Pylint suppressions were added narrowly for intentional `protected-access` and oversized test modules. Import-related IDE Pylint diagnostics were intentionally left unsuppressed because they appear to be editor-environment resolution noise rather than repo-level failures.
- Release draft prepared: `docs/RELEASE_NOTES_1.2.0_DRAFT.md`.
- No implementation-phase validation gaps remain inside this initiative.

## 5b. Post-completion follow-up phase: provenance-aware service persistence

Status: Deferred design follow-up. This phase is not complete and is intentionally separated from the archived implementation above.

### Why this follow-up is needed

- The current service entity model tries to preserve too much inferred intent across policy transitions.
- That creates avoidable complexity in three places:
	- options-flow state, where `automatic` versus manual categories can drift apart
	- entity reconciliation, where the integration tries to decide whether an old entity should keep or lose prior enablement state
	- registry interaction, where `disabled_by` is being asked to carry more meaning than it reliably can
- The desired user experience is simpler than the current design pressure:
	- in `automatic`, active services should exist and be enabled
	- in manual category mode, selected-category services should exist and start disabled
	- when a service no longer matches the chosen exposure rule, it should be removed
	- when it becomes eligible again, it should come back in the mode's expected default state

### Best-outcome recommendation for option 1

- Preferred direction: replace the separate `automatic` versus manual mode toggle with one service exposure selector that expresses the user's intent directly.
- The service selector should support three outcomes only:
	- explicit `automatic` sentinel selected
	- one or more manual categories selected
	- nothing selected
- Validation should keep this contract strict:
	- the `automatic` sentinel cannot be combined with manual categories
	- manual categories can be combined with each other
	- empty selection means no service entities should be exposed
- Runtime contract:
	- in `automatic`, active services exist and are enabled
	- in manual category mode, selected-category services exist and are disabled by default
	- when a service becomes ineligible, remove it
	- when a service becomes eligible again, apply the mode's default behavior
	- if a service transitions into `automatic`, automatic takes precedence and the entity becomes enabled even if it had previously been disabled under manual behavior
- This intentionally favors a simpler, more predictable product model over preserving fine-grained historical intent for each service

### Simplified storage and migration model

- Store one service exposure selection per profile rather than a separate mode plus category list.
- Recommended representation:
	- explicit `automatic` sentinel for automatic exposure
	- category identifiers for manual exposure
	- empty list for no service exposure
- Migration rule for existing users:
	- if stored service categories are empty, migrate that profile to the `automatic` sentinel
	- if stored service categories already contain one or more categories, preserve them as manual exposure selections
- Default for new users:
	- initialize service exposure to the `automatic` sentinel
- This migration deliberately treats an empty preexisting category list as the historical equivalent of automatic exposure for first-time rollout

### Practical operating examples

#### Example 1. New profile or migrated empty-selection profile

- Starting state:
	- profile has no prior manual category selections
	- service exposure is initialized to the `automatic` sentinel
- Desired result:
	- active services are created and enabled
	- no separate mode field exists to keep in sync

#### Example 2. Clean manual category creation

- Starting state:
	- profile currently uses the `automatic` sentinel or no service entities exist yet
- User selects category `gaming` instead of `automatic`
- Desired result:
	- gaming service entities are created disabled by default
	- automatic-only services that are no longer eligible are removed
- Why this is better:
	- the user's service exposure choice is represented directly in one selector

#### Example 3. User enables one manual-category service

- Starting state:
	- `zynga` exists because `gaming` is selected manually
	- entity is disabled by default
- User enables `zynga` in Home Assistant
- Desired result after reload:
	- `zynga` stays enabled
	- the integration does not attempt to force it back to disabled while `gaming` remains selected

#### Example 4. User leaves the category selected but disables a service again

- Starting state:
	- `zynga` exists under manual `gaming`
	- entity is enabled in Home Assistant
- User disables it in Home Assistant
- Desired result:
	- entity stays disabled
	- reload does not re-enable it as long as the service remains in manual-category mode

#### Example 5. User disables one automatic service

- Starting state:
	- profile is `automatic`
	- `spotify` is currently active
	- entity is enabled by default
- User disables `spotify` in Home Assistant
- Desired result after reload:
	- `spotify` stays disabled
	- other active services remain enabled
	- if `spotify` later stops qualifying and then reappears again under `automatic`, it returns enabled because `automatic` is authoritative for active services

#### Example 6. Transition from manual category to automatic

- Starting state:
	- `amazonmusic` exists because `music` was selected manually
	- the entity may currently be disabled under manual defaults
- User changes service exposure from category-based manual selection to the `automatic` sentinel
- Later, `amazonmusic` becomes active in Control D
- Desired result:
	- `amazonmusic` exists as an automatically exposed active service and is enabled
	- this is intentional even if it had previously been disabled under manual behavior
- Why this works better:
	- `automatic` remains easy to explain: active services are on

#### Example 7. Service becomes ineligible

- Starting state:
	- a service entity currently exists under either automatic or manual exposure
	- the service no longer qualifies because it is no longer active and no selected manual category includes it
- Desired result:
	- the entity is removed because it is no longer eligible
	- if it becomes eligible again later, it returns in the current mode's default state

#### Example 8. Existing users during first migration

- Starting state:
	- Profile A has no stored service categories
	- Profile B has stored categories `gaming` and `social`
- Migration runs
- Desired result:
	- Profile A is migrated to the `automatic` sentinel
	- Profile B keeps `gaming` and `social` exactly as selected
	- no existing user with chosen categories is silently switched to automatic

### Practical implementation approach

#### Phase 5.1. Model and persistence contract

- Replace the stored service mode plus category combination with one service exposure selection field in `custom_components/controld_manager/models.py`.
- Add an explicit automatic sentinel constant alongside category values.
- Add migration logic in config-entry setup or options normalization:
	- if stored categories are empty, write back the automatic sentinel
	- if stored categories are present, preserve them unchanged
	- use the automatic sentinel as the default for new profiles

#### Phase 5.2. Runtime reconciliation rules

- Update `custom_components/controld_manager/managers/integration_manager.py` and `custom_components/controld_manager/coordinator.py` so service eligibility is derived only from the single selector state.
- Update `custom_components/controld_manager/managers/entity_manager.py` so it:
	- creates eligible service entities in the mode's expected default state
	- removes service entities that are no longer eligible
	- re-enables a service when it becomes automatically active under the automatic sentinel
- Do not add service-level override persistence for this follow-up.

#### Phase 5.3. Lifecycle and removal rules

- Define one explicit transition table in `docs/ARCHITECTURE.md` for:
	- automatic sentinel selected
	- manual categories selected
	- empty selection
	- migration from empty legacy categories to automatic
	- user disable under automatic
	- user enable under manual
	- category removal
	- upstream service disappearance
- Keep entity removal rules simple:
	- remove the entity when it is no longer justified by current policy or current upstream presence
	- when it reappears, apply the current selector's default state rather than trying to restore historical intent

#### Phase 5.4. Validation and diagnostics

- Add diagnostics output that surfaces the single service exposure selection per profile so runtime behavior is debuggable without inspecting the entity registry directly.
- Add end-to-end tests for the eight examples above in `tests/components/controld_manager/test_phase4.py`.
- Add runtime tests in `tests/components/controld_manager/test_runtime.py` that prove:
	- empty legacy categories migrate to automatic
	- existing category selections remain unchanged
	- automatic services return enabled when they become active again

### Scope guard rails for this follow-up

- Do not change service unique IDs in option 1.
- Do not persist the full live service catalog.
- Do not keep a separate automatic/manual field once the single-selector migration is complete.
- Do not support mixing the automatic sentinel with manual categories.
- Do not add service-level provenance or override storage for this simplified model.
- Accept the product tradeoff that a service returning under automatic should be enabled even if it had previously been disabled under manual behavior.

## 6. Validation strategy

1. Verify policy round-trip and config-flow validation before touching entity-lifecycle behavior.
2. Verify registry shaping in runtime tests before relying on entity add and remove assertions.
3. Verify dynamic entity creation and cleanup end to end with Home Assistant setup tests for both service and rule paths.
4. Verify translations, diagnostics, and docs only after behavior is stable and the final user-facing wording is set.
5. End with a reverse code review of the full change set against `docs/DEVELOPMENT_STANDARDS.md`, applicable Home Assistant platinum-quality standards, and the implementation plan before sign-off.

Focused validation targets after implementation:

- [x] `python -m pytest tests/components/controld_manager/test_config_flow.py -v`
- [x] Focused runtime slices covering policy defaults, coordinator fetch behavior, alias-target setup, auth/recovery, and analytics window requests
- [x] Focused phase4 slices covering automatic service lookup, diagnostics shape, automatic-service pruning, and all-rules sentinel behavior
- [x] `python -m ruff check .`
- [x] `python -m ruff format .`
- [x] `python -m mypy custom_components/controld_manager`

Latest focused validation status:

- `python -m pytest tests/components/controld_manager/test_config_flow.py -q` passed
- `python -m pytest tests/components/controld_manager/test_runtime.py -q -k 'setup_entry_creates_entry_scoped_runtime or setup_entry_populates_client_alias_targets_from_analytics_clients or coordinator_refresh_raises_auth_failed_for_reauth or coordinator_requests_last_day_analytics_window or coordinator_logs_unavailable_once_and_recovery'` passed
- `python -m pytest tests/components/controld_manager/test_phase4.py -q -k 'removed_dynamic_entities_are_pruned_across_platforms or set_service_state_supports_live_lookup_without_enabled_categories or diagnostics_redact_entry_data_and_report_runtime_scope'` passed
- `python -m ruff check .` passed
- `python -m mypy custom_components/controld_manager` passed

Release-validation status:

- `bash ./utils/quick_lint.sh` passed
- `python -m mypy custom_components/controld_manager` passed
- `python -m pytest tests/ -v` passed with `207 passed`

Required final review checklist:

- confirm all new or changed user-facing strings are translation-backed and documented in `custom_components/controld_manager/translations/en.json`
- confirm all new config keys, defaults, selectors, and sentinel identifiers follow the constant taxonomy in `docs/DEVELOPMENT_STANDARDS.md`
- confirm typing stays explicit and complete without avoidable suppressions
- confirm layer ownership still matches the architecture and development standards, especially coordinator write ownership and manager-owned business logic
- confirm diagnostics stay compact and redact-safe
- confirm docs, tests, and quality-scale statements match the actual delivered behavior

## 7. References

- Current options-flow profile editor: `custom_components/controld_manager/config_flow.py`.
- Current profile policy contract: `custom_components/controld_manager/models.py`.
- Current service fetch gating and registry shaping: `custom_components/controld_manager/coordinator.py` and `custom_components/controld_manager/managers/integration_manager.py`.
- Current dynamic entity reconciliation: `custom_components/controld_manager/managers/entity_manager.py`.
- Current service entity behavior: `custom_components/controld_manager/select.py`.
- Current diagnostics exposure for profile policy: `custom_components/controld_manager/diagnostics.py`.
- Current options-flow strings: `custom_components/controld_manager/translations/en.json`.
- Current architecture guidance that needs updating: `docs/ARCHITECTURE.md`.
- Current config-flow, runtime, and end-to-end test coverage: `tests/components/controld_manager/test_config_flow.py`, `tests/components/controld_manager/test_runtime.py`, and `tests/components/controld_manager/test_phase4.py`.
- External product signal supplied for this initiative: Control D v2.0.14 release notes, `Updated the Services page to see and access relevant Services more easily`.
