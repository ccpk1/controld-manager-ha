# Service and rule entity auto-exposure builder handoff

Status: Completed and archived. This handoff was fully executed and is retained as the implementation blueprint record for the completed initiative.

## Purpose

This note is the implementation blueprint for the initiative in `CONTROLD_RULE_AND_SERVICE_ENTITY_AUTO_EXPOSURE_COMPLETED.md`.

The builder is expected to follow this document exactly.

No deviation is permitted without explicit user approval after explaining:

1. what must change
2. why the current blueprint is insufficient
3. what new risk the deviation introduces
4. what tests and docs must expand because of that deviation

## Non-negotiable guardrails

These are direct repository constraints that must be preserved.

### Standards baseline

- `docs/DEVELOPMENT_STANDARDS.md` is a mandatory implementation contract for this initiative.
- Applicable Home Assistant platinum-quality standards are mandatory acceptance criteria for this initiative, not optional stretch goals.
- The builder must explicitly satisfy and preserve at least these standards wherever this initiative touches code:
    - translation-backed user-facing strings
    - disciplined constant usage and taxonomy
    - strict typing with explicit annotations
    - manager-owned business logic and coordinator-owned config-entry writes
    - diagnostics hygiene and redaction-safe outputs
    - documentation and test updates landing with behavior changes
- If any requested implementation step appears to conflict with `docs/DEVELOPMENT_STANDARDS.md` or an applicable platinum-quality expectation, stop and ask for approval before proceeding.

### Architecture guardrails

- Keep one bounded configuration-sync poller. Do not add a second poller for this initiative.
- Keep compact profile policy in `ConfigEntry.options`. Do not store mirrored service or rule payloads.
- Keep service exposure as a compact policy surface. The new automatic service mode extends the model; it does not replace manual category exposure.
- Keep rule exposure opt-in. `Expose all rules as entities` is a compact opt-in sentinel, not a new mirrored rule inventory.
- Keep all dynamic add, remove, cleanup, and stale-registry removal in `entity_manager.py`.
- Keep service and rule entity unique IDs stable. Do not create alternate identity schemes for automatic versus manual exposure.
- Keep entity types unchanged:
  - services remain selects
  - rule folders remain selects
  - individual rules remain switches

### Development guardrails

- Coordinator owns config-entry writes and migration writes.
- Managers own business logic and registry shaping.
- Entities, services, and flows remain thin surfaces only.
- No direct protocol calls from entities, services, or flows.
- No new unowned root modules.
- No new helper or utils module unless existing files become genuinely overloaded and the user explicitly approves it.
- No reuse of `CONF_AUTO_ENABLE_SERVICE_SWITCHES` for this feature. That existing field controls default registry enablement, not exposure mode.
- No storage of copied automatic service IDs or copied automatic rule IDs in options, runtime policy, or diagnostics.
- All new config keys, defaults, selector tokens, and sentinel identifiers must be introduced through the approved constant families instead of scattered literals.
- All new user-facing labels, descriptions, and validation errors must be translation-backed.
- All touched functions and internal helpers must keep typing explicit and complete.

## Feature contract to implement

### Services

Implement a per-profile two-choice selector:

- `Manual`
- `Automatic`

Contract:

- `Manual` keeps the current category-driven behavior.
- `Automatic` derives live service exposure from `GET /profiles/{profile_id}/services`.
- A service qualifies when it is present in the profile services response as an explicit service row, even if current mode is Off.
- Manually selected categories still win.
- Automatic mode must exclude services whose category is already selected in `allowed_service_categories`.
- On every refresh, the manager computes the desired automatic service set from current upstream data.
- The entity manager compares current desired keys to the Home Assistant entity registry and removes no-longer-justified service entities.
- If the profile switches from `Automatic` to `Manual`, automatic-only service entities must be removed unless they are still justified by selected categories.

### Rules

Keep the existing `Expose custom rules` multi-select, but add a reserved first option:

- `Expose all rules as entities`

Contract:

- The sentinel is mutually exclusive with every explicit folder or rule target.
- If selected, expose every current live rule folder and every current live custom rule for the profile.
- If the sentinel is later removed, the entity manager must remove rule entities that are no longer justified by remaining explicit selections.
- The sentinel remains opt-in.

## Execution order

Follow the phases in this order. Do not overlap phases until the phase gate is satisfied.

### Phase 1. Policy and options-flow contract

#### Files to touch

1. `custom_components/controld_manager/const.py`
Anchor: around line 16 onward.
Why:
- add the new config key for service exposure mode
- add compact constant values for `manual` and `automatic`
- add the reserved internal rule sentinel constant

Current anchor snippet:

```python
CONF_ALLOWED_SERVICE_CATEGORIES = "allowed_service_categories"
CONF_AUTO_ENABLE_SERVICE_SWITCHES = "auto_enable_service_switches"
CONF_EXPOSED_CUSTOM_RULES = "exposed_custom_rules"
```

Required change shape:

```python
CONF_SERVICE_EXPOSURE_MODE = "service_exposure_mode"
SERVICE_EXPOSURE_MANUAL = "manual"
SERVICE_EXPOSURE_AUTOMATIC = "automatic"
RULE_TARGET_ALL_ENTITIES = "system:all_rules"
```

2. `custom_components/controld_manager/models.py`
Anchor: around `ControlDProfilePolicy` at line 411.
Why:
- add typed profile policy storage for service exposure mode
- preserve compact storage
- extend rule-target resolution helpers to recognize the all-rules sentinel
- do not store copied live service IDs or rule IDs

Current anchor snippet:

```python
allowed_service_categories: frozenset[str] = frozenset()
auto_enable_service_switches: bool = False
exposed_custom_rules: frozenset[str] = frozenset()
```

Required change shape:

```python
service_exposure_mode: str = SERVICE_EXPOSURE_AUTOMATIC
allowed_service_categories: frozenset[str] = frozenset()
exposed_custom_rules: frozenset[str] = frozenset()
```

Guardrail:
- keep `auto_enable_service_switches` intact only if still needed for current behavior
- do not repurpose it for the new feature

3. `custom_components/controld_manager/config_flow.py`
Anchors:
- imports around line 29
- `async_step_edit_profile` around line 303
- service category selector around lines 376 to 389
- custom-rule selector around lines 392 to 403
Why:
- surface the new two-choice selector
- inject the rule sentinel as the first option
- validate mutual exclusivity for rule targets
- keep one coherent per-profile save surface

Current anchor snippet:

```python
vol.Required(
    CONF_ALLOWED_SERVICE_CATEGORIES,
    default=sorted(profile_policy.allowed_service_categories),
): selector.SelectSelector(...)
vol.Required(
    CONF_EXPOSED_CUSTOM_RULES,
    default=sorted(profile_policy.exposed_custom_rules),
): selector.SelectSelector(...)
```

Required UI shape:

```python
vol.Required(
    CONF_SERVICE_EXPOSURE_MODE,
    default=profile_policy.service_exposure_mode,
): selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(
                value=SERVICE_EXPOSURE_MANUAL,
                label="Manual",
            ),
            selector.SelectOptionDict(
                value=SERVICE_EXPOSURE_AUTOMATIC,
                label="Automatic",
            ),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
```

Rule sentinel option shape:

```python
selector.SelectOptionDict(
    value=RULE_TARGET_ALL_ENTITIES,
    label="Expose all rules as entities",
)
```

Validation rule:
- if `RULE_TARGET_ALL_ENTITIES` is present and selection length is greater than 1, return a specific, translation-backed form error

4. `custom_components/controld_manager/diagnostics.py`
Anchor: around lines 91 to 97.
Why:
- expose `service_exposure_mode`
- expose whether the sentinel is active
- do not expose expanded derived automatic service IDs

Current anchor snippet:

```python
"allowed_service_categories": sorted(...),
"exposed_custom_rules": sorted(...),
```

5. `custom_components/controld_manager/translations/en.json`
Anchor: around lines 61 to 71.
Why:
- add label and description for the service exposure selector
- add revised description for custom rules including the all-rules sentinel behavior
- add form-error translations for invalid mixed rule selections

Current anchor snippet:

```json
"allowed_service_categories": "Allowed service categories",
"exposed_custom_rules": "Expose custom rules"
```

#### Tests to add or update

1. `tests/components/controld_manager/test_config_flow.py`
Anchors:
- line 233 `test_options_flow_edit_profile_exposes_external_filters_and_hides_auto_enable`
Why:
- extend field-order expectations to include the new service exposure selector directly above allowed service categories
- assert `auto_enable_service_switches` still stays hidden if that remains true

2. `tests/components/controld_manager/test_runtime.py`
Anchors:
- line 1216 `test_options_flow_saves_typed_profile_policy`
Why:
- assert `service_exposure_mode` persists in compact policy storage
- assert all-rules sentinel stores as one compact target value

#### Phase 1 gate

Do not continue until all of the following are true:

- policy round-trip is typed and compact
- config-flow validation rejects mixed all-rules selections
- no copied live item lists are stored in options
- diagnostics remain compact
- new config keys and sentinel values are defined through approved constants rather than ad hoc literals
- every new user-facing string is wired for translation

### Phase 2. Automatic service exposure

#### Files to touch

1. `custom_components/controld_manager/coordinator.py`
Anchor: around lines 188 to 214.
Why:
- widen service detail fetch gating so services are fetched when any included profile is in automatic mode or has manual categories selected
- keep one configuration-sync poller only

Current anchor snippet:

```python
needs_service_catalog = any(
    self._runtime.options.profile_policy(profile_pk).allowed_service_categories
    for profile_pk in included_profile_pks
)
...
include_services=bool(
    self._runtime.options.profile_policy(profile_pk).allowed_service_categories
)
```

Required change concept:

```python
profile_policy = self._runtime.options.profile_policy(profile_pk)
include_services = (
    profile_policy.service_exposure_mode == SERVICE_EXPOSURE_AUTOMATIC
    or bool(profile_policy.allowed_service_categories)
)
```

2. `custom_components/controld_manager/managers/integration_manager.py`
Anchor: around lines 91 to 99 where `services_by_profile` is built.
Why:
- build the union of manual-category services and automatic explicit service rows
- keep manual categories authoritative when categories overlap

Current anchor snippet:

```python
services_by_profile={
    profile_pk: self._normalize_services(
        detail.services,
        service_categories,
        self.runtime.options.profile_policy(profile_pk).allowed_service_categories,
        inventory.service_catalog,
    )
```

Required change concept:
- split service normalization into two explicit inputs:
  - manual category inclusion
  - automatic live-row inclusion
- keep one normalized `services_by_profile` output consumed by entities and services

Implementation note:
- do not make `entity_manager.py` parse raw API payloads
- `integration_manager.py` remains the normalization owner

3. `custom_components/controld_manager/managers/entity_manager.py`
Anchor: `_desired_keys` around lines 197 to 235 and `async_sync_platform` around lines 55 to 73.
Why:
- keep all add and remove cleanup here
- remove stale automatic service entities when policy changes or upstream rows disappear
- preserve category-backed service entities when automatic service rows disappear but category policy still justifies them

Current anchor snippet:

```python
select_keys.update(
    f"profile::{profile_pk}::service::{service_pk}"
    for service_pk in self.runtime.registry.services_by_profile.get(profile_pk, {})
)
```

Required interpretation:
- desired keys remain registry-driven
- the registry itself must already represent the correct union and exclusion rules
- no second cleanup path outside `entity_manager.py`

4. `custom_components/controld_manager/select.py`
Anchors:
- platform setup around line 88
- service builder dispatch around line 114
Why:
- verify no identity split is introduced
- only adjust entity-registry defaults if absolutely necessary and explicitly approved

Guardrail:
- do not add a second service entity class for automatic services

5. `custom_components/controld_manager/translations/en.json`
Why:
- describe `Manual` versus `Automatic`
- explicitly explain that automatic services are added and removed from current profile service rows
- explain manual categories still win when categories overlap

#### Tests to add or update

1. `tests/components/controld_manager/test_phase4.py`
Anchors:
- line 871 `test_phase5_policy_enabled_entities_are_created_and_attached`
- line 1560 area `test_removed_dynamic_entities_are_pruned_across_platforms`
Why:
- use these as the existing lifecycle and prune patterns
- add new tests for automatic service creation and removal

Required new test cases:

- automatic mode exposes explicit service row with `action.status = 0`
- automatic mode exposes explicit service row with `action.status = 1`
- automatic mode excludes rows whose categories are manually selected
- switching profile policy from `automatic` to `manual` removes automatic-only services
- if a service remains justified by `allowed_service_categories`, it survives that transition
- refresh-time upstream removal prunes the automatic service entity

2. `tests/components/controld_manager/test_runtime.py`
Why:
- verify registry shaping separately from entity lifecycle
- assert no duplicated services when one row qualifies through both paths

#### Phase 2 gate

Do not continue until all of the following are true:

- one registry output represents the correct service union
- no copied automatic-service lists are stored
- stale automatic services are removed on refresh and policy transition
- category-backed services survive when still justified

### Phase 3. All-rules sentinel

#### Files to touch

1. `custom_components/controld_manager/models.py`
Anchor: around lines 486 to 500.
Why:
- extend `exposed_rule_identities` and `exposed_rule_group_pks`
- if sentinel present, resolve against all live groups and all live rules
- if sentinel absent, preserve current explicit-target behavior

Current anchor snippet:

```python
def exposed_rule_identities(...):
    resolved: set[str] = set()
    for target in self.exposed_custom_rules:
        if target.startswith("rule:"):
```

Required change concept:

```python
if RULE_TARGET_ALL_ENTITIES in self.exposed_custom_rules:
    return set(rules_by_identity)
```

and similarly for all live rule groups.

2. `custom_components/controld_manager/coordinator.py`
Anchor: around line 212.
Why:
- include rules when explicit selections exist or the sentinel is active

Current anchor snippet:

```python
include_rules=bool(
    self._runtime.options.profile_policy(profile_pk).exposed_custom_rules
)
```

Required change concept:
- use a helper or predicate that distinguishes:
  - no rule exposure
  - explicit targets
  - all-rules sentinel

3. `custom_components/controld_manager/managers/entity_manager.py`
Anchors:
- switch desired rule keys around lines 177 to 191
- select desired rule-group keys around lines 200 to 208
Why:
- desired keys already flow through policy helpers
- preserve this design
- only extend helper semantics, not add a parallel rule-exposure mechanism
- ensure manual-to-sentinel and sentinel-to-manual transitions prune stale entities

4. `custom_components/controld_manager/config_flow.py`
Why:
- sentinel option insertion
- validation
- translation-backed error

#### Tests to add or update

1. `tests/components/controld_manager/test_phase4.py`
Anchors:
- line 907 and nearby rule-group entity cases
- line 984 and nearby prune cases
Why:
- these already prove manual rule exposure and removal behavior
- extend them for all-rules sentinel behavior

Required new test cases:

- sentinel alone exposes all current rule folders and rules
- sentinel plus explicit selections is rejected in the form
- switching from sentinel to explicit targets removes stale entities not covered by explicit targets
- switching from sentinel to empty removes all rule and rule-group entities
- upstream deletion while sentinel remains active prunes rule entities automatically

2. `tests/components/controld_manager/test_runtime.py`
Why:
- prove sentinel helper resolution with compact stored target only

#### Phase 3 gate

Do not continue until all of the following are true:

- all-rules remains opt-in
- all-rules stays one compact stored target
- no parallel rule exposure path is introduced
- entity-manager cleanup handles all policy transitions cleanly

### Phase 4. Docs, architecture, and release surfaces

#### Files to touch

1. `docs/ARCHITECTURE.md`
Primary anchors:
- service exposure contract around lines 236 to 271
- rule exposure clause around line 254
Why:
- extend the service model narrowly
- keep compact-policy principles intact
- document that rules remain opt-in, with one sentinel-based easier opt-in path

Required architecture adjustments:

- service entities are created from:
  - manually selected categories
  - automatic current profile service rows when profile mode is `automatic`
- rule entities are created from:
  - explicitly selected targets
  - or one reserved all-rules sentinel
- no mirrored service or rule catalogs are stored in options

2. `docs/DEVELOPMENT_STANDARDS.md`
No direct changes are required unless the implementation forces a real contract change.
Guardrail:
- if the builder believes standards must change, stop and request approval first.

3. `README.md`
Why:
- explain the new defaults and operator tradeoffs

4. `docs/USER_GUIDE.md`
Why:
- document `Manual` versus `Automatic`
- document `Expose all rules as entities`
- document expected entity add and remove behavior
- document upgrade impact

5. Release notes surface
Why:
- explicitly call out that automatic service exposure is now the default for both migrated and new entries

#### Phase 4 gate

Do not close the initiative until all of the following are true:

- docs describe the intended churn clearly
- architecture remains narrow and compact-policy oriented
- no standards doc was weakened just to accommodate implementation shortcuts
- all applicable `docs/DEVELOPMENT_STANDARDS.md` and Home Assistant platinum-quality expectations have been rechecked against the finished diff

### Final step. Reverse code review

This is the final mandatory step after implementation and executable validation succeed.

Review the finished diff in reverse against:

- `docs/DEVELOPMENT_STANDARDS.md`
- applicable Home Assistant platinum-quality standards
- `CONTROLD_RULE_AND_SERVICE_ENTITY_AUTO_EXPOSURE_IN-PROCESS.md`
- this builder handoff note

The initiative is not complete until this review explicitly confirms all of the following:

- constants follow the repository taxonomy and no new scattered literals were introduced for config keys, defaults, service-mode values, or sentinel identifiers
- all user-facing strings, form errors, selector labels, descriptions, and docs are translation-backed where required
- typing remains explicit and complete across touched code
- coordinator-owned config-entry writes stayed in the coordinator layer
- managers own business logic, registry shaping, and lifecycle reconciliation
- entities, services, and flows did not gain direct protocol or payload-construction logic
- diagnostics remain compact, useful, and redaction-safe
- docs and tests reflect the actual shipped behavior
- cleanup behavior for service and rule entities is fully covered by tests and remains owned by `entity_manager.py`

## Exact touch map

Use this as the complete planned touch inventory unless a stop-and-ask event occurs.

### Production surfaces

- `custom_components/controld_manager/const.py`
- `custom_components/controld_manager/models.py`
- `custom_components/controld_manager/config_flow.py`
- `custom_components/controld_manager/coordinator.py`
- `custom_components/controld_manager/managers/integration_manager.py`
- `custom_components/controld_manager/managers/entity_manager.py`
- `custom_components/controld_manager/diagnostics.py`
- `custom_components/controld_manager/translations/en.json`
- `docs/ARCHITECTURE.md`
- `README.md`
- `docs/USER_GUIDE.md`

### Test surfaces

- `tests/components/controld_manager/test_config_flow.py`
- `tests/components/controld_manager/test_runtime.py`
- `tests/components/controld_manager/test_phase4.py`

### Surfaces that should not change unless blocked

- `custom_components/controld_manager/select.py`
Only adjust if service entity identity or default enabled state truly requires it.

- `custom_components/controld_manager/services.py`
Do not change unless existing service resolution unexpectedly depends on exposure mode.

- `custom_components/controld_manager/api/client.py`
Do not change unless the existing `async_get_profile_detail(... include_services=...)` contract cannot provide the necessary live service rows.

- `docs/DEVELOPMENT_STANDARDS.md`
Do not change unless user approval is obtained.

## Quality gates per phase

### Mandatory checks after Phase 1

- `python -m pytest tests/components/controld_manager/test_config_flow.py -v`
- `python -m pytest tests/components/controld_manager/test_runtime.py -v -k policy`

### Mandatory checks after Phase 2

- `python -m pytest tests/components/controld_manager/test_runtime.py -v -k service`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k service`

### Mandatory checks after Phase 3

- `python -m pytest tests/components/controld_manager/test_runtime.py -v -k rule`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k rule`

### Mandatory checks after Phase 4

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`
- final reverse code review against the standards and plans listed above

## Stop-and-ask conditions

Stop immediately and ask for approval if any of the following becomes necessary:

- a second poller or refresh path
- persistent storage of live service IDs or live rule IDs
- a second service entity class or alternate unique-ID scheme
- a second rule exposure control outside the existing selector
- changes to `services.py` or `api/client.py` beyond narrow compatibility fixes
- changes to `docs/DEVELOPMENT_STANDARDS.md`
- changes to identity or device-attachment rules
- migration behavior that cannot be owned by the coordinator layer

## Builder success definition

The build is successful only if all of the following are true:

- service exposure is compact-policy driven and uses a two-choice selector
- automatic service entities are derived from current upstream rows and not stored as copied lists
- rule all-entities exposure remains opt-in and compact-policy driven
- `entity_manager.py` is the only cleanup and stale-removal owner for these new dynamic entities
- unique IDs and entity types remain stable
- docs, translations, diagnostics, and tests all land together
- all applicable `docs/DEVELOPMENT_STANDARDS.md` and Home Assistant platinum-quality standards are explicitly re-confirmed in the final reverse code review
- no shortcuts weaken the architecture or standards contract
