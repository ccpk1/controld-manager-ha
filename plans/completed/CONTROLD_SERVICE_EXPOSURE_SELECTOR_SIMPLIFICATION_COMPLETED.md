# Service exposure selector simplification

Status: Completed and archived after full repository validation.

## 1. Initiative snapshot

- Goal: replace the current service exposure contract with one simpler selector-driven model that matches the agreed user experience.
- New contract:
  - `automatic` means active services exist and are enabled
  - manual category selections mean selected-category services exist and are disabled by default
  - if a service becomes ineligible, remove it
  - if it becomes eligible again, apply the current selector default
  - if a service transitions into `automatic`, automatic wins and the entity becomes enabled
- Primary simplification: remove the separate stored automatic or manual mode field and make the existing service-category selector the single source of truth by allowing it to hold one reserved automatic sentinel.
- Migration decision confirmed for rollout:
  - if a profile currently has no stored service categories, migrate it to the `automatic` sentinel
  - if a profile already has one or more stored categories, keep those selections unchanged

## 2. Scope and non-goals

### In scope

- Replace the separate `service_exposure_mode` plus `allowed_service_categories` contract with one service exposure selector field in profile policy.
- Reuse the existing `allowed_service_categories` policy field as the single stored selector surface instead of introducing a second persisted service-selection key.
- Add one explicit automatic sentinel to the selector and validate that it cannot be combined with category values.
- Keep empty selection as an intentional `no services exposed` state after migration.
- Back out the layered `automatic + additive categories` runtime behavior from normalization, reconciliation, diagnostics, translations, docs, and tests.
- Back out service-select re-enable and re-disable heuristics that were introduced to preserve inferred intent across policy transitions.
- Remove active use of the obsolete `service_exposure_mode` contract and any legacy `auto_enable_service_switches` behavior that no longer fits the simplified model.
- Preserve the completed all-rules sentinel work for custom rules.
- Preserve stable service unique IDs and existing service mutation services.
- Update migration behavior so empty legacy category state is written back as `automatic` while existing non-empty category selections are preserved.
- Make registry-entry deletion part of the service lifecycle contract when a service becomes ineligible so recreated services truly return with fresh defaults.
- Update docs, release notes, diagnostics, and tests to reflect the simpler contract.

### Non-goals

- Do not add per-service provenance, override persistence, or any service-level intent store.
- Do not support mixing the automatic sentinel with manual categories.
- Do not restore the old additive model where automatic live rows and manual categories are combined in one profile state.
- Do not change service unique IDs or introduce a second service entity class.
- Do not change the rule all-entities sentinel contract implemented in the completed initiative.
- Do not broaden the Home Assistant service layer; service writes must still work for non-exposed services through existing manager logic.
- Do not introduce a brand-new service exposure config key if the existing category-selection field can carry the sentinel cleanly.

## 3. Open questions or external dependencies

- Product tradeoff accepted: if a service later qualifies under `automatic`, it should be enabled even if it had previously been disabled under manual-category behavior.
- Entity lifecycle decision remains strict: when a service no longer matches the current selector contract, its entity registry entry should be removed so a later return is treated as fresh creation.
- The plan assumes one selector field can safely represent all intended user states:
  - `automatic` sentinel only
  - one or more manual categories
  - empty selection
- Additional contract decisions locked after review:
  - entering `automatic` is the only continuous-eligibility transition that should force an existing service back to enabled
  - moving from `automatic` to manual categories does not force-disable a service that remains continuously eligible; manual default-disabled behavior applies on creation or recreation, not as a blanket reset of all still-eligible entities
  - deleting the registry entry on ineligibility is what makes later recreation follow the current selector default cleanly
- Open-changes audit against the completed implementation and current worktree:
  - keep:
    - rule all-entities sentinel work in `models.py`, `config_flow.py`, translations, docs, and tests
    - version and dependency updates in `manifest.json` and `pyproject.toml`
    - endpoint alias completed-plan archival work
  - back out or rewrite:
    - `service_exposure_mode` storage and UI in `models.py`, `config_flow.py`, translations, diagnostics, and tests
    - layered automatic-plus-categories wording in `README.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`, and `docs/RELEASE_NOTES_1.2.0_DRAFT.md`
    - registry-heuristic service reconciliation in `custom_components/controld_manager/managers/entity_manager.py`
    - automatic-layer normalization assumptions in `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/integration_manager.py`, and `custom_components/controld_manager/select.py`
    - legacy `auto_enable_service_switches` behavior where it still affects service default enablement or migration outcomes
    - obsolete service-mode lifecycle tests added in `tests/components/controld_manager/test_phase4.py` and `tests/components/controld_manager/test_runtime.py`
    - tracked local test output artifacts such as `result.txt`, `test_output.txt`, and `test_results.log`

## 4. Phase summary table

| Phase | Outcome | Primary files |
| --- | --- | --- |
| 1 | Replace the stored service contract and migration path by reusing the category selector with an automatic sentinel, while backing out obsolete mode fields | `custom_components/controld_manager/const.py`, `custom_components/controld_manager/models.py`, `custom_components/controld_manager/config_flow.py`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/diagnostics.py`, `tests/components/controld_manager/test_config_flow.py`, `tests/components/controld_manager/test_runtime.py` |
| 2 | Simplify runtime service shaping and remove registry-heuristic reconciliation tied to the old layered model | `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/integration_manager.py`, `custom_components/controld_manager/managers/entity_manager.py`, `custom_components/controld_manager/select.py`, `tests/components/controld_manager/test_phase4.py`, `tests/components/controld_manager/test_runtime.py` |
| 3 | Rewrite docs and release surfaces to the new contract and back out outdated guidance from the completed 1.2 design | `README.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`, `docs/RELEASE_NOTES_1.2.0_DRAFT.md`, `custom_components/controld_manager/translations/en.json` |
| 4 | Clean the worktree, remove obsolete artifacts and tests, and validate the simplified contract against current open changes | `tests/components/controld_manager/test_phase4.py`, `tests/components/controld_manager/test_runtime.py`, `tests/components/controld_manager/test_config_flow.py`, workspace root test-output artifacts |

## 5. Per-phase details with checkboxes

### Phase 1. Replace the stored selector contract and migration path

- [x] Reuse `CONF_ALLOWED_SERVICE_CATEGORIES` in `custom_components/controld_manager/const.py` as the single stored selector surface and retire `CONF_SERVICE_EXPOSURE_MODE` from the active contract.
- [x] Add one explicit automatic sentinel constant in `custom_components/controld_manager/const.py` that is reserved for the existing category selector and cannot collide with category identifiers.
- [x] Update `ControlDProfilePolicy` in `custom_components/controld_manager/models.py` so profile policy round-trips the existing selector field compactly and no longer treats `service_exposure_mode` as the authoritative stored setting.
- [x] Decide and implement the cleanup posture for `CONF_AUTO_ENABLE_SERVICE_SWITCHES` in `custom_components/controld_manager/models.py` and migration logic: either remove it from active profile policy entirely or preserve it only as ignored legacy input during migration.
- [x] Update `custom_components/controld_manager/config_flow.py` so the per-profile form uses the existing service-category selector surface with the automatic sentinel injected as a mutually exclusive option rather than a separate mode dropdown.
- [x] Add validation in `custom_components/controld_manager/config_flow.py` that rejects any selection containing both the automatic sentinel and one or more manual categories.
- [x] Update coordinator-owned migration behavior in `custom_components/controld_manager/coordinator.py` so empty legacy category selections are written back as the automatic sentinel, while existing non-empty category selections remain unchanged.
- [x] Update `custom_components/controld_manager/diagnostics.py` so diagnostics expose the new single selector field rather than the previous mode-plus-categories contract.
- [x] Rewrite focused config-flow and runtime tests in `tests/components/controld_manager/test_config_flow.py` and `tests/components/controld_manager/test_runtime.py` to verify:
  - empty legacy categories migrate to automatic
  - existing non-empty categories are preserved
  - mixed automatic sentinel plus categories is rejected
  - new profiles default to automatic

### Phase 2. Simplify runtime service shaping and entity lifecycle

- [x] Update `custom_components/controld_manager/coordinator.py` so service detail fetch decisions derive only from the new selector state rather than the old layered mode logic.
- [x] Rewrite service normalization in `custom_components/controld_manager/managers/integration_manager.py` so it supports only these states per profile:
  - automatic sentinel selected
  - manual categories selected
  - empty selection
- [x] Remove additive automatic-plus-categories shaping from `custom_components/controld_manager/managers/integration_manager.py`; automatic and manual category exposure must be mutually exclusive after validation.
- [x] Simplify `custom_components/controld_manager/managers/entity_manager.py` so it only creates currently eligible services, removes ineligible services, deletes stale registry entries for ineligible services, and applies the agreed automatic-wins behavior when a service becomes eligible under automatic.
- [x] Back out `_async_reconcile_service_selects`, `_should_enable_service_select`, and related integration-disabled or re-enable heuristics in `custom_components/controld_manager/managers/entity_manager.py` if they no longer apply under the new contract.
- [x] Update `custom_components/controld_manager/select.py` only as needed so initial enabled-by-default behavior follows the current selector contract without preserving the old layered-source assumptions.
- [x] Replace obsolete lifecycle tests in `tests/components/controld_manager/test_phase4.py` and `tests/components/controld_manager/test_runtime.py` with cases for:
  - automatic creates active services enabled
  - manual categories create services disabled by default
  - a manual-category service enabled by the user stays enabled across normal refresh while it remains eligible
  - an automatic service disabled by the user stays disabled across normal refresh while it remains eligible
  - switching from manual categories to automatic enables a newly automatic active service
  - switching from automatic to manual categories does not force-disable a still-eligible service unless it becomes ineligible and is recreated later
  - switching away from a qualifying state removes the service entity
  - a removed service that later reappears returns in the current selector default state because the old registry entry was deleted

### Phase 3. Rewrite docs and release guidance to the simplified contract

- [x] Update `README.md` so service exposure is described as one selector with automatic or manual-category choices rather than layered automatic rows plus additive categories.
- [x] Update `docs/ARCHITECTURE.md` so the service model explains one selector-driven contract, the migration rule, and the accepted product tradeoff that automatic is authoritative when a service becomes active.
- [x] Update `docs/USER_GUIDE.md` so the options-flow experience and service entity behavior match the new contract exactly.
- [x] Rewrite `custom_components/controld_manager/translations/en.json` strings that currently describe `service_exposure_mode`, additive categories, or layered overlap rules.
- [x] Update wording so users understand that `Automatic` is now one option inside the service selector, not a separate control.
- [x] Rewrite `docs/RELEASE_NOTES_1.2.0_DRAFT.md` so upgrade guidance matches the new migration rule and no longer claims additive category layering.
- [x] Keep the all-rules sentinel documentation intact, but remove any coupling between that rule work and the obsolete service-layered design.

### Phase 4. Clean open changes and validate against the current worktree

- [x] Compare the finished change set against the archived implementation plan in `plans/completed/CONTROLD_RULE_AND_SERVICE_ENTITY_AUTO_EXPOSURE_COMPLETED.md` and explicitly back out the service-only portions that no longer apply under the simplified contract.
- [x] Leave the archived completed plan in place as historical record, but ensure current code, docs, and tests no longer implement or claim the obsolete layered automatic-plus-categories behavior.
- [x] Remove tracked local test-output artifacts from the worktree if they are not intentionally part of the repository.
- [x] Remove obsolete service-mode lifecycle tests and any temporary debugging assertions that only existed to support the abandoned registry-heuristic path.
- [x] Confirm that service mutation services still resolve live service targets correctly even when the selector is empty or set to manual categories that do not expose the mutated service as an entity.
- [x] Reconcile diagnostics assertions and release text with the new single-selector model before final validation.
- [x] End with a reverse review of the resulting diff against `docs/DEVELOPMENT_STANDARDS.md`, the archived completed plan, and the current open changes so the repository does not ship mixed contracts.

## 6. Validation strategy

1. Validate migration, selector mutual-exclusion rules, and legacy-field cleanup before changing dynamic entity lifecycle behavior.
2. Validate runtime service shaping separately from entity creation and removal so the simplified contract is proven at the registry level first.
3. Validate end-to-end service lifecycle behavior after rollback of the obsolete reconciliation logic, including registry-entry deletion and recreation defaults.
4. Validate docs, translations, diagnostics, and release notes only after the runtime contract is stable.
5. End with a reverse code review against the new plan, `docs/DEVELOPMENT_STANDARDS.md`, and the list of currently open changes.

Focused validation targets after implementation:

- `python -m pytest tests/components/controld_manager/test_config_flow.py -v`
- `python -m pytest tests/components/controld_manager/test_runtime.py -v`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k service`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k 'service or catalog'`
- `python -m ruff check .`
- `python -m mypy custom_components/controld_manager`

## 7. References

- Archived implementation plan to compare and selectively back out: `plans/completed/CONTROLD_RULE_AND_SERVICE_ENTITY_AUTO_EXPOSURE_COMPLETED.md`
- Current options-flow implementation surface: `custom_components/controld_manager/config_flow.py`
- Current profile policy model: `custom_components/controld_manager/models.py`
- Current migration and fetch gating: `custom_components/controld_manager/coordinator.py`
- Current service normalization and lifecycle code: `custom_components/controld_manager/managers/integration_manager.py`, `custom_components/controld_manager/managers/entity_manager.py`, `custom_components/controld_manager/select.py`
- Current service-related tests carrying old-contract behavior: `tests/components/controld_manager/test_config_flow.py`, `tests/components/controld_manager/test_runtime.py`, `tests/components/controld_manager/test_phase4.py`
- Current user-facing service-contract docs that need rewrite: `README.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`, `docs/RELEASE_NOTES_1.2.0_DRAFT.md`