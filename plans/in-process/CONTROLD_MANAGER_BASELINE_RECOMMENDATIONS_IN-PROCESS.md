# Control D Manager baseline recommendations

## Initiative snapshot

The architecture and standards baseline is now locked around one Home Assistant config entry per authenticated Control D instance, one Home Assistant device per profile, and endpoint entities attached to profile devices.

This plan now focuses on the remaining work required to validate the Control D API contract and build the runtime in a sequence that preserves those decisions.

The target direction solves four concrete problems:

- users should enter one API credential set once per Control D instance
- multiple Control D instances must coexist cleanly in one Home Assistant deployment
- one integration service surface should be able to target any supported Control D entity, device, profile, or the entire instance without duplicate entry setup
- the implementation must avoid Home Assistant device-registry bloat by modeling physical clients as endpoint entities instead of Home Assistant devices

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

## Open questions or external dependencies

- What should the instance system device be called in the Home Assistant UI, and does Control D expose enough account metadata to support that name cleanly?
- How should the first implementation treat multi-profile endpoints, given that Control D supports multiple enforced profiles on one endpoint?
- If multi-profile endpoints are included later, what endpoint state can be represented honestly when rule evaluation is merged across profiles rather than owned by one primary profile?
- Which exact profile-level and endpoint-level entities deliver the best initial value without creating noisy registry sprawl?
- What mutation rate limits, write consistency guarantees, and rollback behavior apply when one service targets multiple profiles or the whole instance?
- Does the API support bulk operations natively, or will the integration need manager-level fan-out across multiple profile targets?
- How is a disabled profile represented in refreshed profile and endpoint payloads after `disable_ttl` is written?

## Phase summary table

| Phase | Status | Goal | Primary files | Exit outcome |
| --- | --- | --- | --- | --- |
| 1 | Complete | Lock the lexicon, hierarchy, and manager architecture | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `docs/QUALITY_REFERENCE.md`, `README.md` | Durable docs agree on the instance-centric model and minimum manager set |
| 2 | Next | Validate instance identity, API topology, and polling design | `custom_components/controld_manager/api/`, `custom_components/controld_manager/models.py`, tests, supporting notes if needed | Verified instance anchor, normalized read contract, profile-endpoint topology, and split-polling contract |
| 3 | Pending | Build the entry-scoped runtime and lifecycle managers | `custom_components/controld_manager/__init__.py`, `custom_components/controld_manager/coordinator.py`, `custom_components/controld_manager/managers/`, `custom_components/controld_manager/entity.py` | One config entry owns one runtime with manager-backed device and entity lifecycle control |
| 4 | Pending | Add conservative entities, shared services, and later add-on evaluation | platform files, `services.yaml`, translations, tests, optional supporting notes | Stable profile devices, endpoint entities, shared service targeting, and documented late-phase add-on decisions |

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
- [ ] Benchmark Control D polling needs against integrations such as NextDNS and confirm whether the recommended split design should be implemented as separate coordinators, separate refresh groups, or another bulk-fetch pattern.
- [ ] Lock the initial entity inventory for the instance system device, profile devices, and endpoint entities before platform code begins so device-registry growth stays intentional.
- [ ] Confirm the refreshed-read contract for `controld_manager.pause_profile`, including how disabled profiles appear after `disable_ttl` writes and the safest duration-to-timestamp service schema.
- [x] Capture the current API uncertainties and verified public-doc findings in a supporting note because they materially affect implementation sequencing.
- [ ] Confirm how multi-profile endpoints are represented on live reads, since the inspected `GET /devices` payload exposed only a single nested `profile` object.
- [ ] Confirm how multi-profile endpoints are represented on live reads, since the inspected `GET /devices` payload exposed only a single nested `profile` object even though the product docs define merged multi-profile behavior.

### Phase 3: Build the entry-scoped runtime and lifecycle managers

- [ ] Implement the async API client under `custom_components/controld_manager/api/` so one authenticated session can enumerate the full instance inventory without duplicating credentials per profile.
- [ ] Rework `custom_components/controld_manager/config_flow.py` so the user authenticates once, the flow validates the instance, and duplicate prevention is based on the immutable instance identifier.
- [ ] Replace the current placeholder runtime shape with an entry-scoped runtime contract in `custom_components/controld_manager/coordinator.py` and `custom_components/controld_manager/models.py` that supports split polling, indexed registries, and manager attachment.
- [ ] Add `custom_components/controld_manager/managers/` implementations for the required minimum manager set, with clearly separated responsibilities for shared lifecycle, device lifecycle, entity lifecycle, profile logic, and endpoint logic.
- [ ] Update `custom_components/controld_manager/__init__.py` and `custom_components/controld_manager/diagnostics.py` so setup, unload, reload, and diagnostics all reflect one entry with many managed profiles and one stored credential set.
- [ ] Add boundary tests that prove config-entry writes remain coordinator-owned, manager responsibilities do not overlap, and runtime state stays entry-scoped.

### Phase 4: Add conservative entities, shared services, and later add-on evaluation

- [ ] Build the shared entity base in `custom_components/controld_manager/entity.py` so unique IDs, translation placeholders, purpose metadata, availability, and device attachment logic are centralized.
- [ ] Add the smallest useful entity set first: instance analytics sensors, profile-level switch entities, and endpoint telemetry entities with at least a last-active attribute when the API supports it.
- [ ] Implement roaming-endpoint reconciliation so the entity manager updates an endpoint entity's parent profile device during refresh when profile membership changes.
- [ ] Register shared services only after manager write paths exist, including a first-pass `controld_manager.pause_profile` service and a target-resolution path that supports `entity_id`, `device_id`, and `config_entry_id` safely.
- [ ] Evaluate the Pi-hole compatibility option and the later tamper-oriented features only after the core runtime is stable, and capture either a concrete follow-on plan or an explicit deferral note.
- [ ] Reassess `custom_components/controld_manager/quality_scale.yaml` only after the runtime, entity lifecycle, and service contracts exist in working code.

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
- `docs/QUALITY_REFERENCE.md`