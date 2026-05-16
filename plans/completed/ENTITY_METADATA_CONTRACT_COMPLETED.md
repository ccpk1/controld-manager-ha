# Entity metadata contract

Status: Completed and archived after implementation, documentation updates, and full validation for version 1.3.0.

Implemented:

- shared metadata contract added across entity surfaces
- metadata vocabulary centralized in `const.py`
- shared attribute assembly centralized in `entity.py`
- platform metadata declarations updated across button, binary sensor, sensor, select, and switch entities
- translation labels added for the new metadata attributes
- focused metadata assertions added to `tests/components/controld_manager/test_phase4.py`
- integration version bumped to `1.3.0`

Validation completed:

- `python -m pytest tests/components/controld_manager/test_phase4.py -k 'metadata_contract or option_entities_expose_raw_purpose_attributes' -v`
- `python -m ruff check .`
- `python -m mypy custom_components/controld_manager`
- `python -m pytest tests/ -v`

## Initiative snapshot

Add a shared entity metadata contract across the Control D Manager integration so every entity exposes:

- `integration`
- `profile_name`
- existing `purpose`
- `item_type`
- `taxonomy_path`
- `item_name`

The implementation should keep this logic centered in the shared entity base, avoid fake taxonomy for non-control entities, preserve existing rule-specific attributes, and align `item_type` values with existing Control D terms where possible.

## Scope and non-goals

In scope:

- define exact attribute keys and controlled value vocabulary
- add shared attribute assembly in `custom_components/controld_manager/entity.py`
- update concrete entity classes only where dynamic metadata cannot be inferred by the base
- add translated state-attribute labels where Home Assistant attribute translation applies
- extend existing entity-state tests to cover the new contract

Non-goals:

- renaming entities or changing unique IDs
- changing service payload contracts
- inventing taxonomy for account status, analytics, summary, or action surfaces
- changing current rule-specific attributes such as `group`, `action`, `comment`, `rule_identity`, `expires_at`, or `expired`

## Open questions or external dependencies

Resolved in implementation:

1. `item_name` is present across the current entity set, using entity labels by default and explicit constants where a fixed metadata label is clearer.
2. Grouped rules use dynamic group names in `taxonomy_path`, while root rules use the explicit `Domain` taxonomy segment.
3. New state-attribute labels were added to `translations/en.json`.

## Phase summary table

| Phase | Goal | Likely files |
| --- | --- | --- |
| 1 | Define the attribute contract and constants | `custom_components/controld_manager/const.py` |
| 2 | Centralize shared metadata assembly in the entity base | `custom_components/controld_manager/entity.py` |
| 3 | Fill in per-platform metadata where needed and add attribute label translations | `custom_components/controld_manager/button.py`, `custom_components/controld_manager/binary_sensor.py`, `custom_components/controld_manager/sensor.py`, `custom_components/controld_manager/select.py`, `custom_components/controld_manager/switch.py`, `custom_components/controld_manager/translations/en.json` |
| 4 | Expand entity-state coverage for the metadata contract | `tests/components/controld_manager/test_phase4.py` |

## Per-phase details with checkboxes

### Phase 1: Define the contract in constants

- [x] Add attribute-key constants in `custom_components/controld_manager/const.py`:
  `ATTR_INTEGRATION`, `ATTR_PROFILE_NAME`, `ATTR_ITEM_TYPE`, `ATTR_TAXONOMY_PATH`, `ATTR_ITEM_NAME`.
- [x] Reuse `DOMAIN` as the `integration` attribute value instead of introducing a second integration-name literal.
- [x] Add controlled item-type value constants in `custom_components/controld_manager/const.py` to avoid repeated raw literals across platforms and tests:
  `ITEM_TYPE_ACTION`, `ITEM_TYPE_STATUS`, `ITEM_TYPE_SUMMARY_METRIC`, `ITEM_TYPE_ANALYTICS_METRIC`, `ITEM_TYPE_FILTER`, `ITEM_TYPE_FILTER_MODE`, `ITEM_TYPE_SERVICE`, `ITEM_TYPE_DEFAULT_RULE`, `ITEM_TYPE_RULE_GROUP`, `ITEM_TYPE_RULE`, `ITEM_TYPE_OPTION`, `ITEM_TYPE_PROFILE_PAUSE`.
- [x] Centralize the shared metadata vocabulary in `custom_components/controld_manager/const.py`, including controlled taxonomy labels and fixed metadata labels.

### Phase 2: Centralize metadata in the shared entity base

- [x] Extend `custom_components/controld_manager/entity.py` so `ControlDManagerEntity.extra_state_attributes` always starts from one shared metadata dict instead of only returning `purpose`.
- [x] Add protected hooks or properties in the base for metadata derivation, keeping platform overrides narrow. Recommended hooks:
  `_item_type`, `_item_name`, `_taxonomy_path()`, `_profile_name()`.
- [x] Make the base set `integration=DOMAIN` for every entity.
- [x] Make the base set `profile_name` for instance, profile, and endpoint entities using the implemented account/profile ownership contract.
- [x] Keep the merge order safe so subclass-specific attributes extend the shared metadata instead of replacing it, especially in `binary_sensor.py`, `sensor.py`, `select.py`, and `switch.py`.

### Phase 3: Add per-class metadata declarations and translations

- [x] Update platform classes to declare `item_type` and, where needed, dynamic `item_name` and `taxonomy_path` sources instead of rebuilding whole attribute dicts.
- [x] Keep non-control entities honest:
  instance and profile status sensors use `item_type=status`, summary counts use `item_type=summary_metric`, analytics sensors use `item_type=analytics_metric`, and the sync button uses `item_type=action`, all with `taxonomy_path=[]`.
- [x] Keep control entities structured:
  filter, filter mode, service, default rule, rule group, rule, option, and profile pause each get the requested control-oriented metadata without duplicating the leaf type inside `taxonomy_path`.
- [x] Update `custom_components/controld_manager/translations/en.json` so the new state attribute keys have translated display labels alongside existing `purpose` handling.
- [x] Do not alter user-facing entity names unless a metadata helper requires a small refactor; the feature is attribute-only.

### Phase 4: Cover the contract with existing entity-state tests

- [x] Extend `tests/components/controld_manager/test_phase4.py` to assert shared metadata on representative entity categories, including account, endpoint, service, default rule, rule, and option surfaces.
- [x] Update current raw-purpose assertions to also verify `integration`, `profile_name`, `item_type`, `taxonomy_path`, and `item_name` without weakening existing rule-specific attribute checks.
- [x] Add a grouped-rule assertion that proves `taxonomy_path` contains only the hierarchy above the rule leaf, not the `rule` type itself.
- [x] Add instance-surface assertions proving account-scoped metadata uses the expected empty taxonomy path.

## Recommended attribute contract

### Exact attribute keys

- `integration`
- `profile_name`
- `purpose`
- `item_type`
- `taxonomy_path`
- `item_name`

### Which keys should be constants

Add constants for all six attribute keys in `custom_components/controld_manager/const.py`:

- `ATTR_INTEGRATION = "integration"`
- `ATTR_PROFILE_NAME = "profile_name"`
- `ATTR_PURPOSE = "purpose"` already exists
- `ATTR_ITEM_TYPE = "item_type"`
- `ATTR_TAXONOMY_PATH = "taxonomy_path"`
- `ATTR_ITEM_NAME = "item_name"`

Add constants for controlled `item_type` values in `custom_components/controld_manager/const.py` because they will be reused by multiple platforms and by tests.

### Shape and semantics

- `integration: str`
  Always `DOMAIN`, which resolves to `"controld_manager"`.
- `profile_name: str | None`
  Profile display name for profile entities, owning profile display name for endpoint entities, `None` for instance entities.
- `purpose: str | None`
  Existing raw translation key behavior stays unchanged.
- `item_type: str`
  Controlled value from the item-type constants.
- `taxonomy_path: list[str]`
  Ordered list of Control D container terms above the leaf item. Use `[]` when there is no honest hierarchy.
- `item_name: str | None`
  Leaf label for the thing the entity represents. Prefer normalized row labels for dynamic controls and compact stable literals for status or metric surfaces.

### Contract rules

- Keep all six keys present on every entity for a predictable automation contract.
- `taxonomy_path` should never repeat the semantic leaf already represented by `item_type`.
- Non-control entities should not synthesize path segments such as `"account"`, `"profile"`, or `"analytics"` unless the repository already models them as real Control D hierarchy.
- Rule-specific attributes remain additive and unchanged.

## File and surface plan

### Shared metadata foundation

- `custom_components/controld_manager/const.py`
  Add the new attribute keys and the controlled `item_type` constants.
- `custom_components/controld_manager/entity.py`
  Make the shared base the single owner of common metadata assembly and profile-name derivation.

### Platform-specific metadata declarations

- `custom_components/controld_manager/button.py`
  Declare the action-surface metadata for `ControlDManagerSyncButton`.
- `custom_components/controld_manager/binary_sensor.py`
  Declare endpoint status metadata and let subclass-specific endpoint attributes continue to merge on top.
- `custom_components/controld_manager/sensor.py`
  Declare status, summary metric, and analytics metric metadata for instance and profile sensors.
- `custom_components/controld_manager/select.py`
  Declare control metadata for filter mode, service, default rule, rule group, and option selects.
- `custom_components/controld_manager/switch.py`
  Declare control metadata for profile pause, filter, rule, and option switches.

### Translation and tests

- `custom_components/controld_manager/translations/en.json`
  Add attribute display labels for the new keys.
- `tests/components/controld_manager/test_phase4.py`
  Extend the current entity-state assertions with the new metadata contract.

Minimum likely file set:

- `custom_components/controld_manager/const.py`
- `custom_components/controld_manager/entity.py`
- `custom_components/controld_manager/button.py`
- `custom_components/controld_manager/binary_sensor.py`
- `custom_components/controld_manager/sensor.py`
- `custom_components/controld_manager/select.py`
- `custom_components/controld_manager/switch.py`
- `custom_components/controld_manager/translations/en.json`
- `tests/components/controld_manager/test_phase4.py`

## Per-entity-class mapping table

| File | Entity class | item_type | taxonomy_path shape | item_name source |
| --- | --- | --- | --- | --- |
| `button.py` | `ControlDManagerSyncButton` | `action` | `[]` | static literal such as `"sync"` or `"sync_now"`; prefer entity key over display text |
| `binary_sensor.py` | `ControlDManagerEndpointStatusBinarySensor` | `status` | `[]` | endpoint display name fallback to endpoint device ID |
| `sensor.py` | `ControlDManagerStatusSensor` | `status` | `[]` | static literal `"status"` |
| `sensor.py` | `ControlDManagerProfileStatusSensor` | `status` | `[]` | static literal `"status"` |
| `sensor.py` | `ControlDManagerProfileCountSensor` | `summary_metric` | `[]` | static literal `"profile_count"` |
| `sensor.py` | `ControlDManagerEndpointCountSensor` | `summary_metric` | `[]` | static literal `"endpoint_count"` |
| `sensor.py` | `ControlDManagerProfileEndpointCountSensor` | `summary_metric` | `[]` | static literal `"endpoint_count"` |
| `sensor.py` | `ControlDManagerAccountAnalyticsSensor` | `analytics_metric` | `[]` | abstract base only; no direct entity state |
| `sensor.py` | `ControlDManagerTotalQueriesSensor` | `analytics_metric` | `[]` | static literal `"total_queries"` |
| `sensor.py` | `ControlDManagerBlockedQueriesSensor` | `analytics_metric` | `[]` | static literal `"blocked_queries"` |
| `sensor.py` | `ControlDManagerBypassedQueriesSensor` | `analytics_metric` | `[]` | static literal `"bypassed_queries"` |
| `sensor.py` | `ControlDManagerRedirectedQueriesSensor` | `analytics_metric` | `[]` | static literal `"redirected_queries"` |
| `sensor.py` | `ControlDManagerBlockedQueriesRatioSensor` | `analytics_metric` | `[]` | static literal `"blocked_queries_ratio"` |
| `sensor.py` | `ControlDManagerProfileAnalyticsSensor` | `analytics_metric` | `[]` | abstract base only; no direct entity state |
| `sensor.py` | `ControlDManagerProfileTotalQueriesSensor` | `analytics_metric` | `[]` | static literal `"total_queries"` |
| `sensor.py` | `ControlDManagerProfileBlockedQueriesSensor` | `analytics_metric` | `[]` | static literal `"blocked_queries"` |
| `sensor.py` | `ControlDManagerProfileBlockedQueriesRatioSensor` | `analytics_metric` | `[]` | static literal `"blocked_queries_ratio"` |
| `sensor.py` | `ControlDManagerProfileBypassedQueriesSensor` | `analytics_metric` | `[]` | static literal `"bypassed_queries"` |
| `sensor.py` | `ControlDManagerProfileRedirectedQueriesSensor` | `analytics_metric` | `[]` | static literal `"redirected_queries"` |
| `select.py` | `ControlDManagerProfileFilterModeSelect` | `filter_mode` | `[`"filters"`]` | `filter_row.name` fallback to `filter_pk` |
| `select.py` | `ControlDManagerProfileServiceModeSelect` | `service` | `[`"services"`, `<category_name>`]` | `service_row.name` fallback to `service_pk` |
| `select.py` | `ControlDManagerProfileDefaultRuleSelect` | `default_rule` | `[`"options"`]` | static literal `"default_rule"` |
| `select.py` | `ControlDManagerProfileRuleGroupSelect` | `rule_group` | `[`"rules"`]` | `group_row.name` fallback to `group_pk` |
| `select.py` | `ControlDManagerProfileOptionSelect` | `option` | `[`"options"`]` | `option_row.title` fallback to `option_pk` |
| `switch.py` | `ControlDManagerProfilePausedSwitch` | `profile_pause` | `[]` | static literal `"profile_pause"` |
| `switch.py` | `ControlDManagerProfileFilterSwitch` | `filter` | `[`"filters"`]` | `filter_row.name` fallback to `filter_pk` |
| `switch.py` | `ControlDManagerProfileRuleSwitch` | `rule` | `[`"rules"`]` for root rules, `[`"rules"`, `<group_name>`]` for grouped rules | `rule_row.rule_pk` fallback to stored `rule_identity` |
| `switch.py` | `ControlDManagerProfileOptionSwitch` | `option` | `[`"options"`]` | `option_row.title` fallback to `option_pk` |

Notes:

- `ControlDManagerAccountAnalyticsSensor` and `ControlDManagerProfileAnalyticsSensor` are abstract bases; the contract should be implemented once there so subclasses inherit it.
- Do not encode `"filter"`, `"service"`, `"rule"`, `"option"`, `"default_rule"`, or `"profile_pause"` into `taxonomy_path`; those belong only in `item_type`.
- For root custom rules, avoid fake path segments such as `"domain"` unless the repository later models that as a first-class Control D hierarchy.

## Key design risks or ambiguities to resolve before coding

1. `item_name` stability versus readability: dynamic labels such as filter names, service names, option titles, and rule group names are the most useful for automation introspection, but they are not immutable identifiers. The recommendation is to keep them descriptive and rely on unique IDs for stability.
2. Grouped-rule taxonomy content: using `group_name` in `taxonomy_path` is honest hierarchy, but renames will change the attribute payload. If that is considered too volatile, the alternative is `[`"rules"`]` only, at the cost of losing useful structure.
3. Translation duplication cost: `translations/en.json` likely needs repeated `state_attributes` blocks per entity translation key, as already happens for `purpose`. This is tedious but consistent with the current repository pattern.
4. Endpoint owner churn: `profile_name` for endpoint entities must tolerate roaming endpoints and transient `None` ownership without breaking availability or device attachment behavior.
5. Base-class API shape: a hook-based metadata design is the safest way to avoid duplicated platform logic, but it should stay small enough that `entity.py` does not become a second orchestration layer.

## Validation strategy

Recommended implementation-time sequence:

1. Update `tests/components/controld_manager/test_phase4.py` first or alongside the base-entity change for one representative entity in each category.
2. Run the focused entity test module:
   `python -m pytest tests/components/controld_manager/test_phase4.py -v`
3. If the attribute translation file changes, rerun the same focused test module to catch translation-backed state rendering regressions.
4. Run integration typing and lint gates:
   `python -m mypy custom_components/controld_manager`
   `python -m ruff check .`
5. Run the full integration test suite before merge:
   `python -m pytest tests/ -v`

## Final validation status

Completed successfully.

- Focused metadata tests passed
- Ruff passed
- MyPy passed
- Full test suite passed: `216 passed`

## References

- `AGENTS.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`
- `custom_components/controld_manager/const.py`
- `custom_components/controld_manager/entity.py`
- `custom_components/controld_manager/button.py`
- `custom_components/controld_manager/binary_sensor.py`
- `custom_components/controld_manager/sensor.py`
- `custom_components/controld_manager/select.py`
- `custom_components/controld_manager/switch.py`
- `custom_components/controld_manager/translations/en.json`
- `tests/components/controld_manager/test_phase4.py`