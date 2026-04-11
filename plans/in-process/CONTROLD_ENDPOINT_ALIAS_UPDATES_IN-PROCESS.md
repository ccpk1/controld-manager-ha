# Endpoint and client update services

## 1. Initiative snapshot

- Goal: add safe Home Assistant write paths for client aliases and the validated endpoint-scoped `/devices/{device_id}` updates.
- Proposed first surface: Home Assistant services only.
- Confirmed client identity source: `/devices` exposes `parent_device.device_id` and `parent_device.client_id`, which match the alias endpoint contract for clients that sit under Control D endpoints.
- Phase 1 decision: treat analytics client data as the authoritative read-after-write source for client aliases, and require separate client-scoped runtime metadata before service implementation.

## 2. Scope and non-goals

### In scope

- Add API-layer support for alias set and alias clear against the analytics host.
- Add API-layer support for endpoint renames against the core `/devices/{device_id}` contract.
- Add API-layer support for endpoint analytics logging changes against the core `/devices/{device_id}` contract.
- Extend normalized runtime models so a safe client alias target can be resolved from current entry-scoped data.
- Extend normalized runtime models so endpoint-scoped updates can reuse the same manager-owned entry targeting substrate without conflating endpoint and client identities.
- Expose alias writes through shared Home Assistant services.
- Expose endpoint rename and endpoint analytics logging writes through shared Home Assistant services.
- Refresh or optimistically update affected endpoint-facing runtime state after successful writes.
- Add API, normalization, and service-integration tests.
- Update user-facing translations and documentation for the new service surface.

### Non-goals

- Do not add a new entity platform just for alias editing in v1.
- Do not mirror every analytics client row as a Home Assistant entity.
- Do not assume `endpoint_pk` or existing entity unique IDs can stand in for `clientId`.
- Do not add a new entity platform just for endpoint renames or analytics logging controls in v1.
- Do not overload client alias selectors with endpoint-scoped write semantics; endpoint rename and endpoint analytics logging services must remain separate even if they share config-entry targeting helpers.

## 3. Open questions or external dependencies

- `clientId` is now verified for clients. `/devices` client rows expose it as `parent_device.client_id` alongside the parent endpoint `device_id` used by the alias endpoint.
- The observed alias endpoint uses the analytics host and bearer token, but public Control D docs do not currently expose this contract. The public API reference also warns that the API is unversioned.
- Request-body behavior must be validated precisely:
  - POST body is a raw JSON string, not an object.
  - DELETE appears to send `null`; confirm whether an empty body also works.
  - Confirm response body and status for success, duplicate writes, and clears.
- Scope is now partitioned:
  - aliasing applies to clients, not endpoints
  - top-level endpoint updates such as endpoint renames or analytics-setting changes use the core `/devices/{device_id}` contract and will be handled as separate service subphases in this same initiative
- Runtime refresh decision:
  - `GET /v2/client?endpointId=<device_id>` is the authoritative read path for client alias visibility
  - `GET /devices` is not required to reflect client aliases for this feature to proceed

## 3a. Proposed user-facing selector contract

Users will not know `deviceId` or `clientId`, so the service surface should expose human-usable selectors and resolve internal client identifiers through manager-owned lookups.

Recommended selector families:

- `endpoint_mac`: preferred stable selector when available
- `endpoint_name`: convenience selector for the current Control D endpoint label shown in `/devices`
- `endpoint_hostname`: convenience selector for the client `host` value shown in analytics client data
- `endpoint_ip`: optional convenience selector with weaker stability guarantees
- `parent_endpoint_name`: optional narrowing selector for clients behind routers or VLAN endpoints such as Firewalla segments

Recommended precedence:

1. `endpoint_mac`
2. `endpoint_name`
3. `endpoint_hostname`
4. `endpoint_ip`

Selector guidance:

- `endpoint_mac` should be the primary documented selector because it is the most stable user-facing identifier for a physical client.
- `endpoint_name` should be supported because it is what users will usually see in Home Assistant and in the Control D device list, but it is mutable and may become the thing being changed by the alias service.
- `endpoint_hostname` should be supported as a convenience selector, but it is weaker than MAC because DHCP clients can reuse generic hostnames and some hosts are low-signal values.
- `endpoint_ip` should be treated as optional and lower-confidence because DHCP churn makes it less stable; if supported, it should follow the same exact-match and ambiguity rules as hostname selectors.
- `parent_endpoint_name` should be available to disambiguate clients when the same MAC, host, or IP could plausibly appear under different parent endpoints or VLAN segments.

Resolution rules:

- always resolve within one config entry first
- if a selector family resolves to more than one candidate, raise an ambiguity error instead of guessing
- if convenience selectors are used without `parent_endpoint_name`, allow them only when exactly one match exists in the targeted entry scope
- keep advanced internal IDs out of the primary UX, but retain room for a power-user fallback field later if needed for diagnostics

## 4. Phase summary table

| Phase | Outcome | Primary files |
| --- | --- | --- |
| 1 | Validate alias contract, client-only scope, and read-after-write behavior | `custom_components/controld_manager/api/client.py`, `tests/components/controld_manager/test_api.py`, `docs/ARCHITECTURE.md` |
| 2 | Extend runtime models for alias-safe endpoint targeting | `custom_components/controld_manager/models.py`, `custom_components/controld_manager/managers/endpoint_manager.py`, `custom_components/controld_manager/managers/integration_manager.py`, `tests/components/controld_manager/test_runtime.py` |
| 3a | Add service-first client alias mutation path and refresh behavior | `custom_components/controld_manager/services.py`, `custom_components/controld_manager/services.yaml`, `custom_components/controld_manager/const.py`, `custom_components/controld_manager/translations/en.json`, `tests/components/controld_manager/test_phase4.py` |
| 3b | Add service-first endpoint rename path and refresh behavior | `custom_components/controld_manager/api/client.py`, `custom_components/controld_manager/services.py`, `custom_components/controld_manager/services.yaml`, `custom_components/controld_manager/const.py`, `custom_components/controld_manager/translations/en.json`, `tests/components/controld_manager/test_api.py`, `tests/components/controld_manager/test_phase4.py` |
| 3c | Add service-first endpoint analytics logging path and refresh behavior | `custom_components/controld_manager/api/client.py`, `custom_components/controld_manager/services.py`, `custom_components/controld_manager/services.yaml`, `custom_components/controld_manager/const.py`, `custom_components/controld_manager/translations/en.json`, `tests/components/controld_manager/test_api.py`, `tests/components/controld_manager/test_phase4.py` |
| 4 | Document behavior, limits, and operator guidance | `README.md`, `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`, `custom_components/controld_manager/quality_scale.yaml` |

## 5. Per-phase details with checkboxes

### Phase 1. Validate contract and target coverage

- [x] Reproduce the observed browser contract in a controlled test fixture and record the exact request shape for POST and DELETE in `tests/components/controld_manager/test_api.py`.
- [x] Confirm whether the analytics-host alias endpoint should live as a dedicated external-request helper in `custom_components/controld_manager/api/client.py` rather than reusing the core API base URL path helpers.
- [x] Record the now-confirmed client identifier mapping in the implementation notes: `parent_device.device_id` and `parent_device.client_id` from `/devices` map to alias `deviceId` and `clientId`.
- [x] Constrain v1 scope to clients only. Endpoint updates such as endpoint renames or analytics-setting changes use the core `/devices/{device_id}` contract and are not part of the alias feature.
- [x] Confirm whether `/v2/client?endpointId=<device_id>` is sufficient as the read-side refresh source for alias visibility after a write.
- [x] Update `docs/ARCHITECTURE.md` only if this validation proves the runtime must permanently include a second analytics-client identity source.

### Phase 2. Add runtime alias target normalization

- [x] Extend `custom_components/controld_manager/models.py` with a typed alias-target model that can carry `device_id`, `client_id`, current display label, source kind, owning profile, and optional analytics identity hints.
- [x] Update `custom_components/controld_manager/managers/endpoint_manager.py` to preserve enough client detail for alias-safe resolution instead of reducing nested client metadata to counts only.
- [x] Keep existing endpoint entity identity anchored to `device_id`; do not repurpose entity unique IDs to include alias mutable data.
- [x] Add a manager-owned lookup method for resolving exactly one alias target from entry-scoped runtime data, with explicit failure modes for missing or ambiguous targets across the supported selector families: MAC, endpoint name, hostname, IP, and optional parent endpoint name.
- [x] Update `custom_components/controld_manager/managers/integration_manager.py` only as needed to include alias-target metadata in the normalized registry without making entities or services parse raw payloads.
- [x] Add normalization tests in `tests/components/controld_manager/test_runtime.py` that prove the runtime can distinguish endpoint `device_id`, parent endpoint `device_id`, `endpoint_pk`, and `client_id`, with explicit coverage for client cases.

### Phase 3a. Expose service-first client alias writes

- [x] Add new service constants and translation keys in `custom_components/controld_manager/const.py` for setting and clearing endpoint aliases.
- [x] Implement service schemas and handlers in `custom_components/controld_manager/services.py` that target the owning config entry first, then resolve one or more alias targets through manager-owned lookups.
- [x] Design the service schema around user-facing selectors, not internal IDs. The first pass should support `endpoint_mac`, `endpoint_name`, and `endpoint_hostname`, with `endpoint_ip` included only if the read path preserves it reliably enough for exact-match lookups.
- [x] Prefer two explicit services in v1, likely `set_endpoint_alias` and `clear_endpoint_alias`, rather than one overloaded mutation with nullable input.
- [x] Add service descriptions and selectors in `custom_components/controld_manager/services.yaml` with targeting guidance that reflects the validated identifier source.
- [x] Add translated service descriptions and error messages in `custom_components/controld_manager/translations/en.json` for missing targets, ambiguous targets, and upstream write failures.
- [x] After a successful write, trigger an immediate refresh; add optimistic in-memory alias updates only if the validated read path reflects the alias on the next normal refresh.
- [x] Add service-integration tests in `tests/components/controld_manager/test_phase4.py` for success, clear, ambiguous target rejection, multi-entry scoping, and API-failure mapping.

### Phase 3b. Expose service-first endpoint rename writes

- [x] Add API-layer support in `custom_components/controld_manager/api/client.py` for `PUT /devices/{device_id}` endpoint rename writes using the validated `{"name": "..."}` contract.
- [x] Add a manager-owned endpoint rename mutation path that targets endpoint-scoped runtime rows only and does not reuse the client alias target model.
- [x] Add dedicated service constants, schemas, and handlers in `custom_components/controld_manager/services.py` and `custom_components/controld_manager/const.py` for endpoint rename writes.
- [x] Reuse config-entry targeting helpers, but keep endpoint rename selectors and error messages separate from client alias selectors so endpoint and client semantics stay explicit.
- [x] Define the user-facing selector contract for endpoint rename around endpoint-scoped identifiers only, with explicit ambiguity behavior for mutable endpoint names.
- [x] Add service descriptions in `custom_components/controld_manager/services.yaml` and matching translated strings in `custom_components/controld_manager/translations/en.json` following the existing services pattern.
- [x] After a successful rename, trigger an immediate refresh and keep endpoint unique IDs anchored to immutable `device_id` values.
- [x] Add API and service-integration tests in `tests/components/controld_manager/test_api.py` and `tests/components/controld_manager/test_phase4.py` for success, ambiguity rejection, multi-entry scoping, and upstream write-failure mapping.

### Phase 3c. Expose service-first endpoint analytics logging writes

- [x] Add API-layer support in `custom_components/controld_manager/api/client.py` for `PUT /devices/{device_id}` analytics logging writes using the validated `{"stats": 0|1|2}` contract.
- [x] Add a manager-owned endpoint analytics logging mutation path that maps user-facing values to the proven Control D semantics `None`, `Some`, and `Full`.
- [x] Add dedicated service constants, schemas, and handlers in `custom_components/controld_manager/services.py` and `custom_components/controld_manager/const.py` for endpoint analytics logging writes.
- [x] Keep endpoint analytics logging selectors endpoint-scoped and separate from client alias selectors even if they share config-entry targeting helpers.
- [x] Add service descriptions in `custom_components/controld_manager/services.yaml` and matching translated strings in `custom_components/controld_manager/translations/en.json` following the existing services pattern.
- [x] After a successful logging update, trigger an immediate refresh and document the validated `stats` value mapping exactly as `0 = none`, `1 = some`, and `2 = full`.
- [x] Add API and service-integration tests in `tests/components/controld_manager/test_api.py` and `tests/components/controld_manager/test_phase4.py` for success, invalid mode rejection, multi-entry scoping, and upstream write-failure mapping.

### Phase 4. Document behavior and rollout limits

- [x] Update `README.md` to list endpoint aliasing under the service layer, not as a new entity feature.
- [x] Update `docs/USER_GUIDE.md` with practical examples, targeting rules, and current limitations around nested clients versus top-level endpoints.
- [x] Update `docs/ARCHITECTURE.md` to explain why aliasing is service-first and how alias-target identity differs from endpoint entity identity.
- [x] Review `custom_components/controld_manager/quality_scale.yaml`; do not mark new behavior as complete unless the service path, translations, and tests are actually implemented.

## 6. Validation strategy

1. Verify contract shape in API unit tests before any service or manager work.
2. Verify normalized alias-target resolution in runtime tests, especially the identifier split between endpoint `device_id`, parent endpoint `device_id`, `endpoint_pk`, and `client_id`.
3. Verify service behavior end to end with Home Assistant service calls, entry scoping, translated validation errors, and refresh triggering.
4. Verify user-facing docs and translations only after the request contract and read-after-write behavior are confirmed.

Focused validation targets after implementation:

- `python -m pytest tests/components/controld_manager/test_api.py -v`
- `python -m pytest tests/components/controld_manager/test_runtime.py -v`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k alias`
- `python -m pytest tests/components/controld_manager/test_phase4.py -v -k endpoint`
- `python -m ruff check .`
- `python -m mypy custom_components/controld_manager`

## 7. References

- Observed browser contract supplied with this initiative:
  - `POST https://america.analytics.controld.com/client/alias?deviceId=<deviceId>&clientId=<clientId>`
  - `DELETE https://america.analytics.controld.com/client/alias?deviceId=<deviceId>&clientId=<clientId>`
  - Authorization uses the existing analytics bearer token.
- Additional identity evidence supplied with this initiative:
  - `/devices` client rows include `parent_device.device_id` and `parent_device.client_id`
  - `/v2/client?endpointId=<device_id>` scopes analytics clients to one parent endpoint such as `Firewalla-VLAN60`
  - endpoint renames and endpoint analytics-setting changes use `PUT /devices/{device_id}` and are a separate mutation family from client aliases
- Validated endpoint write payloads now tracked in this initiative:
  - endpoint rename: `PUT /devices/{device_id}` with `{"name": "New label"}`
  - endpoint analytics logging: `PUT /devices/{device_id}` with `{"stats": 0|1|2}`
- Existing API-layer analytics host handling: `custom_components/controld_manager/api/client.py`.
- Existing endpoint normalization: `custom_components/controld_manager/managers/endpoint_manager.py`.
- Existing endpoint runtime models: `custom_components/controld_manager/models.py`.
- Existing global service architecture: `custom_components/controld_manager/services.py` and `custom_components/controld_manager/services.yaml`.
- Existing endpoint and browser-contract tests: `tests/components/controld_manager/test_api.py`, `tests/components/controld_manager/test_runtime.py`, and `tests/components/controld_manager/test_phase4.py`.