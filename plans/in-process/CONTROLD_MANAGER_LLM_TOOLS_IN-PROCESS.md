# Initiative: Control D Manager LLM / MCP tool surface

## 1. Initiative snapshot

- **Status: Phases 0–3 complete (2026-10-04).** Branch `feature/llm-mcp-tools`. The API foundation, the tool spec, the gated tier shell, all five read tools, and the full control surface (12 reversible controls plus the destructive `delete_rule`) are implemented and validated. Live-verified on the developer test profile. Next: Phase 4 (prompt, docs, release).
- **What it builds:** an integration-owned `llm.API`, registered by this integration, that exposes Control D profiles, endpoints, clients, and analytics to Home Assistant Assist and any MCP client through Home Assistant's `mcp_server`. The surface is tiered, opt-in, read-first, and vendor-aligned in naming and terminology.
- **Why now:** the integration already has the inventory, policy mutations, and analytics plumbing. The missing capability is a **troubleshooting and query surface**. Control D's per-record Activity Log and ranked breakdowns are high-cardinality telemetry that was deliberately kept out of the entity model; on-demand tooling is the correct home for it, not entities.
- **Decisive platform facts (verified):**
  - The dev/test environment runs Home Assistant **2026.11.0.dev0**; `llm.ToolResult`, `llm.ToolAnnotations`, `llm.APIInstance`, and `Tool.integration` are all present.
  - The LLM tool contract requires **Core 2026.10+**; older Core must still load the integration. Registration therefore must be **version-gated and lazily imported**.
  - **There is no admin gate on Control D writes.** Every service registers with plain `hass.services.async_register`. The **tier option is the entire write-control surface**, so tier labels and user-facing disclosure are load-bearing, not cosmetic.
  - **Every API call returns a response body.** The client currently discards it on writes (those methods are typed `-> None`), so this is a return-contract gap to close, not a missing capability. To callers, only `get_catalog` returns data today; the rest are `SupportsResponse.NONE` even though the upstream body exists.
  - **The integration's declared minimum is `hacs.json` (`2026.3`).** Do not add a version field to `manifest.json`; the LLM feature gate is internal to this plan only.
- **Prerequisite work is real:** the read tools need response-returning services and analytics methods that do not exist yet. Phase 0 delivers those before any tool is written.
- **Origin of this plan:** the capability investigation recorded in `docs/ENGINEERING_FINDINGS.md` (Analytics/Activity Log/retention/DNS verdict/write-response findings) and the Firewalla Local MCP precedent, which is the reference implementation pattern.
- **Explicitly not in scope:** shipping our own MCP server, emulating MSP endpoints, changing the entity model to accommodate analytics, hardcoding retention caps, or duplicating business logic in tools.

## 2. Scope and non-goals

**In scope**

1. **API foundation (no LLM):** current-state catalog refresh, write-response capture across every write family, analytics read methods, response-returning read services, a slug-to-label resolver, and a cross-cutting response/error taxonomy.
2. **LLM tool spec first:** `docs/MCP_TOOL_REFERENCE.md` authored as the authoritative spec before tool code, so tools are built to one contract.
3. **Read/troubleshooting tools:** overview, inventory/topology, activity log, domain test, block analytics rankings, policy reads, catalog.
4. **Control tools (opt-in tier):** filter/service/option/rule/default-rule state, profile enable/disable, endpoint rename and analytics logging, client alias set/clear.
5. **A destructive tier (scope to be decided in Phase 3):** initially `delete_rule`, gated behind `confirm: true` and the destructive annotation.
6. **Prompt fragment, contract tests, docs, and disclosure.**

**Non-goals**

- **No MCP server.** Home Assistant's `mcp_server` serves any registered `llm.API`.
- **No entity-model change.** Analytics remain telemetry; tools do not create entities.
- **No business logic in tools.** Tools delegate to services; services delegate to managers.
- **No artificial retention caps.** Retention is surfaced and warned about, never enforced (see Phase 0, D5).
- **No terminology drift.** Tools and prompts use the repository lexicon exactly (see §3).
- **No destructive operations below the Full tier.**
- **No separate search/query API.** Tools query the existing analytics and inventory surfaces.

## 3. Confirmed constraints and external dependencies

### Platform and version gate

- **Version floor for this feature: Core 2026.10.** Do **not** raise the integration's overall floor; gate registration behind a version predicate, keep LLM imports lazy, hide the option when unsupported, and log once rather than raising a repair. The integration's declared minimum stays where it is (`hacs.json` `2026.3`); no version field is added to `manifest.json`.
- **The LLM API module must be `llm_api.py`, never `llm.py`.** `llm.py` is Home Assistant's own auto-imported integration-platform filename and would be imported outside the guard on older Core.
- **Build tool schemas with `vol.Schema`** (`vol.Required`/`vol.Optional`/`vol.In`); never import `probatio`.
- **The version predicate lives in `helpers/llm_support.py`**, not `const.py` (which must stay framework-free because `api/` imports it).

### Safety model

- **The tier option is the only write control.** There is no admin gate on Control D. Tiers: Off / Summary only / Read only / Read and control / Full.
- **Writes are reversible except rule deletion.** `create_rule` is additive; its only undo is `delete_rule`. When the configured tier does not include the destructive set, the tool still reports `undo: delete_rule(...)` and states that the configured tier does not permit it, so the user knows to raise the tier. `delete_rule` is the destructive operation because a re-created rule gets a new identity.
- **`create_rule` is not idempotent.** Creating the same rule twice creates two rules; it must never report `already_in_state`.
- **No confirmation channel exists in `llm.Tool`.** `confirm: true` is a guard against an accidental call, not user consent. Confirmation is the client's and the model's responsibility.

### Terminology contract (critical)

The repository lexicon in `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md` is authoritative and **must not be hand-waved**. These are different objects and must never be conflated:

| Term | Meaning | Never |
| --- | --- | --- |
| **Profile** | Control D configuration container holding rules, services, blocklists | never call it an entity/device |
| **Endpoint** | A top-level Control D protected row from `/devices` (router segment, ctrld instance, or individually protected client) | never call it a device or a client |
| **Client** | A client visible under an endpoint (analytics + device relationships); **client aliases are client-scoped** | never call it a device or an endpoint |
| **Device** | Home Assistant device-registry container only | never a Control D endpoint/client |
| **Entity** | Home Assistant platform object only | never a profile/endpoint/policy |

**Scope rules the tools must teach:**

- A **client** seen under an endpoint follows that **endpoint's** profile. This is the ctrld-on-Firewalla case: one endpoint per VLAN, whose clients inherit the endpoint's profile.
- A client that is **explicitly assigned** a profile stops being only a sub-client and appears as **its own endpoint**, protected by its own profile. There is no separate "individually protected" flag on a sub-client; assignment is precisely what makes it an endpoint.
- The runtime already distinguishes the two: `ControlDClientAliasTarget.endpoint_device_id` is set when the client is (or became) an endpoint, while `parent_endpoint_device_id` is set when the client sits under a parent endpoint.

### Analytics and retention (verified)

- **Two surfaces:** per-record Activity Log (33 days) and pre-aggregated Statistics (up to 365 days).
- **Dimensions differ:** destination filters (`dstCountry`, `dstIsp`, `dstAsn`) exist on the Activity Log only; the Statistics API supports source/destination ISP filtering inconsistently and no destination country.
- **Retention is a user setting and these are maximums.** Users may choose shorter retention or disable logging entirely.
- **No controllable time series exists.** Spike detection is window-diffing.
- **Analytics maintenance returns `503` code `50303`.**

### Response handling, truncation, and affordability

Applies to **every** call, not just analytics.

- **All calls return a body; capture it.** The shared request helper already parses the response. Writes discard it today; read services mostly never surface it. Confirm the shape per write family with live probes during Phase 0 (a temporary profile/endpoint in Control D is an acceptable test bed).
- **Truncation must be honest.** When a ranked response returns exactly `limit` rows, that is strong evidence of truncation and must be reported (a `truncated` flag plus the applied limit). Never present a capped result as complete.
- **Filters over caching.** Do not build a caching layer. Troubleshooting is occasional, not high-frequency; some churn is acceptable. Affordability is handled with good filter parameters, sensible defaults, and prompt warnings about cost — not with infrastructure.
- **DNS verdict is a special case of the same principle.** It returns a normal DNS response over HTTP 200 even when the domain is blocked: `RCODE 5` (REFUSED) means *blocked*, not *error*. Treat `RCODE 5` as a successful block verdict, not a failure, and treat an empty `controld.verdict` as "no policy matched", not as an error.

### Prior art to reuse, not reinvent

The Firewalla Local implementation is the reference pattern: `llm_api.py`, guard-loaded tool modules, `llm_tools_common.PROMPT`, the read envelope, the action-result envelope, the MCP reference as spec, and the contract/AST tests.

## 4. Phase summary table

| Phase | Focus | Key deliverables | Depends on |
| --- | --- | --- | --- |
| **0** | API foundation and current-state refresh (no LLM) | Catalog refresh; write-response capture; analytics read methods; slug resolver; response-returning services; failure taxonomy; retention policy | none — **first** |
| **1** | Tool spec + gated foundation | `docs/MCP_TOOL_REFERENCE.md` (spec, authored first); version gate; `llm_api.py` shell; tier option; prompt skeleton; guard/AST tests | 0 |
| **2** | Read / troubleshooting tools | `get_account_overview` ✓, `get_inventory`, `get_activity_log`, `test_domain`, `get_catalog` | 1 || **3** | Control tools + destructive scope | Reversible controls; endpoint-to-profile assignment decision; action-result envelope; destructive tier scope | 2 |
| **4** | Prompt, contract tests, docs, release | Finalized prompt; contract tests; user-guide disclosure; README; quality-scale check; release prep | 3 |

Ordering is deliberate: **retention, catalog currency, and the response/error contract are settled before anything is built on them**; the **spec (Phase 1) precedes all tool code**; **reads ship and are used before any write path exists**.

## 5. Per-phase details

### Phase 0 — API foundation and current-state refresh (no LLM code)

**Goal:** make the API and service layers capable of supporting the tools, and refresh our understanding of the current upstream surface so we build on facts rather than a stale model.

- [x] **0.1 Catalog refresh (catch up to current Control D).** Pull the live catalogs and diff them against the repository's supported sets:
  - `/filters` (`filters`, `external_filters`, `ip_filters`), `/profiles/options`, `/services/categories/all`, and per-profile `/profiles/{pk}/options`.
  - **Confirmed gap to close:** `block_attacks` ("Block DNS Exfiltration and Data Smuggling") is a live profile option and is **not** in `SUPPORTED_PROFILE_OPTION_*` in `const.py`. Sweep for any other new options/filters/services in the same pass.
  - For each newly discovered option, record its payload family (toggle vs select vs numeric), default, and choices, then update `const.py` sets, translations, catalog output, and tests.
  - Do **not** auto-expose everything; classify each new item as core, advanced, or documented-only.
  - **Done:** live diff showed 20 filters, 12 external filters, 1 IP filter, 14 profile options, 12 service categories, 1009 services. The **only** genuinely new option was `block_attacks` (toggle), now added to `ADVANCED_PROFILE_OPTION_TOGGLES` (D1: experimental, so advanced). `ecs_subnet` remains deliberately excluded. Option entity names come from the catalog `title`, so no translation change was required.
- [x] **0.2 Write-response capture across all write families (return contract change).** Every API call returns a body; write methods discard it (`-> None`). Change client write methods to **return** the parsed body, propagate through managers, and decide what the service layer exposes. Do **not** assume one shape across families: probe each family — device (`PUT /devices/{device_id}`), profile/filter/service/option/rule mutations, and client-alias writes (which go to the analytics host). A temporary profile and endpoint in Control D is an acceptable test bed for capturing write responses. This underpins the Phase 3 action result.
  - **Done:** all 14 write methods now return the normalized `body` mapping (`dict[str, Any] | None`) via `_optional_body_mapping`; services keep their current response mode for now (D2).
- [x] **0.3 Analytics + verdict read methods.** Add client methods for the Activity Log, ranked domains (`count/question`), cause breakdown (`count/triggerValue`), source country (`count/srcCountry`), and the **DNS verdict** endpoint. Follow the existing external-request helper and response normalizer, and apply the `RCODE 5` = blocked rule (see §3 Response handling).
  - **Done:** `async_get_activity_log` (returns `ControlDActivityLogPage`), `async_get_ranked_domains`, `async_get_trigger_breakdown`, `async_get_source_countries`, and `async_get_dns_verdict` (returns `ControlDDnsVerdict`, `RCODE 5` = blocked). Verified live against the dev instance.
- [x] **0.4 Slug-to-label resolver.** Build one resolver that maps a ranked `triggerValue`/`verdictMatch` slug across config filters, external filters, IP filters, profile options, and services, with a small repository-owned alias map for documented variants (`ads_small`, `ads_medium`, `ads_all`). Return both the raw slug and the resolved label; surface unmapped values as raw.
  - **Done:** `utils/analytics_labels.py` (`build_analytics_label_map`, `resolve_ranked_rows`). Rows carry `value`, `label`, and `label_resolved`; unknown slugs are never invented. The alias map holds only documented variants absent from every catalog (`ads_small`, `ads_medium`).
- [~] **0.5 Response-returning read services — deferred to Phase 2.** Each read service lands with the tool that consumes it, so the response shape and truncation behaviour are validated by a real caller instead of shipping untested.
- [x] **0.6 Cross-cutting failure taxonomy (holistic).** Define one response/error contract applied to **every** call, not just analytics: auth failure, transport/timeout, response-shape violation, maintenance (`503`/`50303`), rate limiting, and the empty-vs-expired-vs-disabled ambiguity. Map to integration exceptions with translation keys; ensure the service layer raises actionable errors.
  - **Done:** `ControlDApiMaintenanceError` and `ControlDApiRateLimitError` added, plus a `retryable` property on the base; `_async_request_url` maps `429` and `503` explicitly.
- [x] **0.7 Retention policy (documentation, not caps).** Do **not** enforce retention windows in code. Investigate whether the user's retention settings are readable from any API surface; if they are, surface them. If not, emit a documentation-driven warning when a query window exceeds the *possible* maximum, phrased as "may be unavailable depending on your Control D retention setting".
  - **Done (D4):** retention is **not readable** — `/users/settings` and `/users/retention` alias the `/users` payload and expose no retention field. Conclusion: warn and document only; no code enforcement.
- [x] **0.8 Truncation and affordability contract.** Standardize how a capped result signals truncation (`applied_limit` plus `truncated` when returned rows equal the limit) so no caller can mistake a capped result for a complete one. Document the cost of each read surface (for example, the Activity Log is roughly 47 KB per 100 records) and require scope plus limit on high-cardinality reads. Do **not** add a caching layer.
  - **Done:** `utils/truncation.py` (`build_limit_meta` for ranked reads, `build_page_meta` for paged reads). No caching layer.

**Decisions (Phase 0):**

- **D1 — Catalog classification. RESOLVED.** `block_attacks` is **advanced** (experimental), added to `ADVANCED_PROFILE_OPTION_TOGGLES`. No other new catalog items were found; `ecs_subnet` remains excluded.
- **D2 — Write-response propagation depth.** Should services return the write body, or should managers use it internally and emit one standardized action result? *Recommendation:* managers own the raw body; the service/tool layer emits **one** standardized action-result envelope (Phase 3) so the shape is uniform. **Pressure test:** write responses differ by family (device vs profile vs client-alias), so a uniform envelope must be built from per-family probes rather than assuming one upstream shape; returning raw bodies from services would also leak controller-specific wrapping into callers.
- **D3 — Failure taxonomy surface.** One envelope for all calls vs per-call typing. *Recommendation:* one envelope with a stable `error.kind` plus a human message; services raise; tools translate. **Pressure test:** the Activity Log's empty-result ambiguity is not an error and must be represented as a distinct informational state, not a failure; `RCODE 5` on the DNS verdict is a *successful block*, not a failure.
- **D4 — Retention readability. RESOLVED.** No API surface exposes retention settings (`/users/settings` and `/users/retention` alias `/users`). Retention is documented and warned about only; never enforced in code.

### Phase 1 — Tool spec and gated foundation

**Goal:** define the surface as a spec, then stand up the registration shell with no tools, provably safe on older Core.

- [x] **1.1 Author `docs/MCP_TOOL_REFERENCE.md` first (the spec).** This is the authoritative surface record and the target all tools build to. Include: conventions (envelopes, units, naming, annotations, tiers, terminology), the grouped tool catalog, and the per-tool template. Authored **before** tool code so tools match the spec rather than the spec trailing the code.
  - **Done:** spec authored with conventions (terminology, naming, tiers, both envelopes, annotations, the two analytics surfaces, truncation, cost), the grouped tool catalog with Phase 2/3 tools marked *(planned)*, the per-tool template, and the schema gotchas.
- [x] **1.2 Version constant + predicate.** Add `MIN_LLM_TOOLS_HA_VERSION: Final = (2026, 10)` (pure tuple) to `const.py` and `llm_tools_supported()` to `helpers/llm_support.py`.
  - **Done:** plus `CONF_LLM_TOOL_MODE`, the five `LLM_TOOL_MODE_*` values, `LLM_TOOL_MODES`, and `DEFAULT_LLM_TOOL_MODE` (`summary_only`).
- [x] **1.3 `llm_api.py` (never `llm.py`, and never a package `llm/`).** Create the API class only. Register inside the guard in `async_setup_entry`, unregister via `entry.async_on_unload`, and re-register on tier-option change (reload). A directory named `llm/` is as hazardous as a file named `llm.py`: its `__init__.py` is discovered as Home Assistant's own `llm` platform and imported outside the guard.
  - **Done:** `ControlDManagerAPI` registers an owned API with id `controld_manager-<entry_id>` and a title-disambiguated name; `_async_setup_llm_api` in `__init__.py` lazily imports both `llm_support` and `llm_api` inside the guard and registers via `entry.async_on_unload`.
- [x] **1.4 Tier option.** Add the mode selector to the options flow, hidden when unsupported, defaulting to the least-disclosing useful tier.
  - **Done:** added to the `integration_settings` step (conditionally present only when supported), backed by `selector.llm_tool_mode` translations; a tier change schedules an entry reload so registration is rebuilt.
- [x] **1.5 Prompt skeleton.** Create `llm_tools_common.py` with `PROMPT` and `format_tool_name`; wire as `api_prompt`.
  - **Done:** `PROMPT` covers terminology, both envelopes, the two analytics surfaces and retention caveat, slug/label rules, truncation, no-guessing, injection caution, and tier language; wired as `api_prompt`.
- [x] **1.6 Guard and AST tests.** Unit-test the predicate; test registration wiring with the predicate mocked both ways; static-test that no unconditionally loaded module imports `probatio` or `helpers.llm` at module level. Reuse the Firewalla guard-module list as the starting enumeration.
  - **Done:** `tests/components/controld_manager/test_llm_support.py` — predicate boundaries, AST no-eager-import, registration on/off, prompt served, unload, name disambiguation, and options normalization (15 tests).
- [x] **1.7 Record the new layer in `docs/ARCHITECTURE.md`.** The tool modules are a new layer with no stated boundary today. State it: tool modules live at the integration root, are guard-loaded with `llm_api.py`, and **call services only** — never the API client or managers directly.
  - **Done:** new "LLM tool layer" section added with the file roles and the guard, naming, services-only, lexicon, and tier rules.

**Decisions (Phase 1):**

- **D5 — Tier set and default. IMPLEMENTED.** Five tiers (Off / Summary only / Read only / Read and control / Full), default **Summary only**. The Summary tier sends the account overview: region, status, profile/endpoint/client counts, the analytics action counts, and one row per profile (name, endpoint count, paused, blocked/bypassed/redirected). **Profiles are not treated as private** — they are user-assigned labels already exposed as Home Assistant device names. All counts come from the shared `ControlDRegistry` accessors, so the tool cannot disagree with the entities.
- **D6 — API identity and multi-entry naming.** *Recommendation:* id `controld_manager-<entry_id>` (stable) and a display name disambiguated across entries. **Pressure test:** Home Assistant merges tool names by API name when several APIs are selected, so identical entry titles must be disambiguated.
- **D7 — Mounting.** Single owned API vs an `llm.py` platform hook. *Recommendation:* **owned API**, matching Firewalla. **Pressure test:** the `llm.py` platform filename is auto-imported by Core and is a load-time hazard; the owned API is not discovered and can be guard-loaded.

### Phase 2 — Read / troubleshooting tools

**Goal:** ship the high-value, zero-write-risk surface. Delivered in slices; the overview landed first so the Summary-tier content could be reviewed before the rest builds on it.

- [x] **2.1 `get_account_overview` (was `get_system_overview`).** The orientation tool. Renamed from `get_system_overview` because Control D has no "system" object and the integration already models account state.
  - **Done:** `get_account_overview` service (`SupportsResponse.ONLY`) + `async_build_account_overview_response` in the integration manager + the `GetAccountOverviewTool`, registered in every enabled tier.
  - **Single logic path:** `ControlDRegistry` now exposes `profile_count`, `endpoint_count`, `discovered_endpoint_count`, and `router_client_count`; the account and profile entities were repointed at those accessors, so the tool cannot diverge from a sensor. `endpoint_count` is the protected count (`discovered + router clients`).
  - **Content:** account block (region, status, the four counts, analytics window) plus **always-included** `profiles[]` rows (name, endpoint count, paused, blocked/bypassed/redirected). Profiles are not treated as private — they are user-assigned labels already exposed as device names. The `include_profile_details` flag was dropped; per-profile content is standard.
- [ ] **2.2 `get_inventory` (topology).** Profiles with their endpoints, each endpoint's **owning profile**, **attached profiles (multi-profile)**, **associated client count**, and **parent-device** relationship; plus client records under an endpoint where available. Each record states its scope explicitly with an `is_endpoint` / `is_client_under_endpoint` field (derived from `endpoint_device_id` vs `parent_endpoint_device_id`) so the endpoint/client distinction is machine-visible, not inferred. This is the read the alias and assignment workflows resolve against.
- [x] **2.3 `get_activity_log`.** The general per-record troubleshooting surface, with vendor-aligned filters. **Default to a short window across all profiles**, then let the caller narrow. A larger bulk log export is explicitly out of scope.
  - **Done:** relative `window` (15m/1h/6h/24h/7d/30d, default 1h) via `utils/time_window.py`; filters for scope, action, trigger, network, DNS, and search; honest `has_more` paging with no total. Live-verified the **`no_log=1` claim (D16): three diagnostic lookups produced zero new activity records**, so `test_domain` does not pollute the log.
- [x] **2.4 `test_domain`.** The DNS verdict lookup for one endpoint and one domain. **Done:** reports `is_blocked` (REFUSED is a block, not an error), the deciding profile, and the matched cause with the vendor `verdictSource` translated to the trigger vocabulary (`bl`→filter, `rules`→custom, `svc`→service, `default`→default).
- [x] **2.5 Block analytics reads — DROPPED (D9 refinement).** `get_block_summary`, `get_top_blocked_domains`, and `get_block_breakdown` are **not** built. Aggregate counts already come from `get_account_overview`, per-record cause comes from `get_activity_log`, and the ranked endpoints take almost no filters (`profileId`/`endpointId[]`/`action`/`limit`), so a truncated ranking cannot be drilled into — it returns a slice, not an answer. The now-unused ranked client reads (`async_get_ranked_domains`, `async_get_trigger_breakdown`, `async_get_source_countries`) and `utils/analytics_labels.py` were removed with them.
- [x] **2.6 Policy reads — DROPPED; `get_catalog` already covers this.** Verified against `async_build_catalog_response`: the `filters` catalog returns `enabled`, `supports_modes`, and `current_mode`; `services` returns `current_mode`; `rules` returns `action`, `enabled`, `comment`, and `group`; `profile_options` returns `current_value`. So a separate `get_policy` tool would be a re-skin of catalog. The one genuine gap was the default rule, which is added as a `default_rule` catalog type instead.
- [x] **2.7 `get_catalog` exposure.** Wrap the existing response-returning catalog service. Require a catalog type and a profile scope, and add a `limit` so a large catalog cannot flood the model's context; report truncation honestly.
  - **Done:** a `get_catalog` tool covering `filters`, `services`, `rules`, `profile_options`, and the **new `default_rule` type** (the one gap that justified a policy tool). `limit` defaults to 50 with `applied_limit`/`truncated` reported. `CATALOG_TYPES` moved to `const.py` so the guard-loaded tool layer can import it.
- [x] **2.8 Bounded defaults everywhere.** Every high-cardinality read requires a scope and a `limit`. Truncation must be reported honestly: for paged surfaces (the Activity Log), report that more pages exist rather than implying a total. Never present a capped result as complete.

**Decisions (Phase 2):**

- **D8 — Tool naming must be source-agnostic and lexicon-correct.** *Recommendation:* name tools for **what they return, not where the data came from**. Use `get_inventory` / endpoint-oriented names, **not** `list_analytics_clients`. **Pressure test:** `v2/client` items are keyed by `device_id` and are enrichment over `/devices`, so an "analytics clients" tool would misname endpoint data and confuse the endpoint/client distinction. *Needed from:* owner.
- **D9 — Cause attribution pattern. RESOLVED.** No separate cause tool. Per-record cause lives in `get_activity_log` (each record carries `trigger` + `triggerValue`), aggregate counts live in `get_account_overview`, and the ranked breakdown tools are **dropped**: they carry almost no filters, so a capped ranking cannot be drilled into. `triggerValue` supports only `filter` and `service` on the ranked path but the activity log supports `custom`, `grule`, and `rebind` too — so the activity log is strictly the better surface.
- **D10 — Client terms in the inventory.** *Recommendation:* state plainly that a client under an endpoint follows that endpoint's profile, and that an explicitly assigned client **is** its own endpoint; expose `is_endpoint` / `is_client_under_endpoint` so the model never has to infer it. **Pressure test:** the earlier "unless individually protected" phrasing implies a flag on a sub-client that does not exist — assignment is what makes a client an endpoint — so the corrected wording is required to prevent a wrong answer.
- **D16 — `test_domain` credential and `no_log`.** *Recommendation:* use the stored API token (it works) rather than relying on the endpoint's observed anonymous access, and feature-flag nothing. Verify with two live tests during build that `no_log=1` suppresses Activity Log records; if it does not, drop the claim instead of asserting it.
- **D17 — Activity Log default scope.** *Recommendation:* short default window (for example one hour) across **all** profiles, with caller-supplied narrowing, sorting, and filtering. **Pressure test:** an account-wide long window is both large and more disclosing than needed for a first look; a short window across all profiles still surfaces "something is happening" and lets the caller drill in.
- **D19 — Catalog and policy bounding.** *Recommendation:* required scope plus a cap, with honest truncation on both `get_catalog` and `get_policy`. **Pressure test:** a `limit` that silently drops detail is worse than no limit if the caller believes the result is complete — the truncation signal is what makes bounding safe.

### Phase 3 — Control tools and destructive scope

**Goal:** add opt-in writes with a uniform, honest action result.

- [x] **3.1 Reversible control tools (Phase 3a).** `set_filter_state`, `set_service_state`, `set_option_state`, `set_rule_state`, `set_default_rule_state`, `enable_profile`, `disable_profile`, and `create_rule` — delegating to the existing services. Endpoint/client tools (`rename_endpoint`, `set_endpoint_analytics_logging`, `set_client_alias`, `clear_client_alias`) move to Phase 3b as a separate family.
- [x] **3.2 `create_rule` as a control tool (included).** Included, additive, and declared **non-idempotent**: creating the same rule twice creates two rules, so it never reports `already_in_state`. Its `undo` names `delete_rule`, and the description states that the undo is unavailable when the tier excludes destructive actions.
- [x] **3.3 Action-result envelope.** **Built from real per-family write responses, not assumption.** Live idempotent probes showed every write family returns a body, but in incompatible shapes: a filter write returns a map of every filter, a service/rule write a list, an option write a list, a default-rule write an object, and a rule delete an empty body. Wrapping that would expose a different shape per tool, so the envelope is **synthesized** (`utils/action_result.py`) and the response is used only as success confirmation. `target` comes from the caller's resolved input, because a rule write does not echo which rule it changed.
- [x] **3.4 Destructive tier.** `delete_rule` registers only in the Full tier with the destructive annotation, declares no undo, and its description tells the model to prefer disabling the rule.

**Decisions (Phase 3):**

**Decisions (Phase 3):**

- **D11 — Destructive scope for the first release.** *Recommendation:* ship the **tier** but keep the destructive tool set to **`delete_rule` only**. **Pressure test:** `create_rule` is additive (control, not destructive); nothing else in the current API is irreversibly destructive from a tool perspective, so a broad first-release destructive set would be invented rather than needed. `delete_rule` is destructive because a re-created rule gets a new identity. *Needed from:* owner — do we ship `delete_rule` now or defer the whole destructive tier to a follow-up?
- **D12 — Endpoint-to-profile assignment.** *Recommendation:* **defer to a follow-up**, or ship read-only first. Reassigning an endpoint's profile changes which whole policy applies to a segment of devices — the highest blast radius in the integration. **Pressure test:** it needs firm multi-profile normalization (profile/profile2/precedence) and a clear confirmation story before a model may call it; the assignment tool must not be conflated with client alias mutation.
- **D13 — Bulk actions.** *Recommendation:* exclude bulk operations from the first release entirely; there are no bulk upstream mutations today beyond per-profile disable.
- **D14 — `create_rule` in the first release.** *Recommendation:* **include it**, as a control-tier, non-idempotent tool. **Pressure test:** it requires a real rule schema (hostname, group, mode, expiration) and applies a live policy change, but it is additive and its blast radius is bounded by the target profile; the non-idempotency and cross-tier undo are handled by the envelope, not by hiding the tool.
- **D15 — `undo` for a non-idempotent create.** *Recommendation:* the envelope always names `undo: delete_rule(...)`, and the tool reports the tier limitation when the destructive set is not enabled; session-scoped tracking of created rule ids is a later refinement. **Pressure test:** without the created rule id returned from the service, an undo can only reference the rule by its resolved identity; this is why Phase 0 fixes the write return contract first.

### Phase 4 — Prompt, contract tests, docs, disclosure, release

- [ ] **4.1 Finalize the prompt fragment** derived from the spec. Keep it concise: units/envelopes, the two analytics surfaces and retention caveat, terminology, tier meaning, injection caution, prefer-these-tools, and confirmation guidance. Include one short **"why is this blocked" playbook** — `test_domain` → (if blocked) `get_activity_log` for that domain → `get_block_breakdown` → `get_policy` → control — as either a prompt paragraph or a `test_domain` description line.
- [ ] **4.2 Contract tests.** Name prefix, `title`, `description`, `integration = DOMAIN`, all four annotations, per-parameter descriptions, the read vs action-result envelopes, and strict JSON-serializability of both. Add a **pragmatic** error-path set (missing required arg, unknown arg, invalid enum, and one upstream failure) rather than exhaustive per-tool coverage.
- [ ] **4.3 User-guide disclosure.** The tier ladder, what each tier sends, the retention caveat, the Core 2026.10 requirement, and the no-admin-gate consequence.
- [ ] **4.4 README footnote** for the Core requirement.
- [ ] **4.5 Quality-scale check.** Confirm no rule regresses; document any new comment needed.
- [ ] **4.6 Release checklist** and docs-link updates.

## 6. Validation strategy

- **Static:** `ruff check`, `ruff format`, `mypy custom_components/controld_manager`.
- **Tests:** `pytest tests/ -v`; new unit tests for the resolver, failure taxonomy, retention warning, version predicate, registration wiring, and the AST no-eager-import test.
- **Contract tests:** assert the spec's requirements against every registered tool; assert both envelopes are `json.dumps`-serializable.
- **Live validation:** pull every read tool against the dev instance through the authenticated REST API, as was done for Firewalla; record payload sizes and correct any defaults.
- **Older-Core simulation:** predicate unit tests at below/at/above the boundary, mocked-helper wiring tests, and the AST import test — the actual failure modes, without needing an old Core install.
- **Writes:** exercise each idempotent control tool and confirm a re-call reports `already_in_state`; exercise `create_rule` as non-idempotent (two calls create two rules) and confirm `undo` references `delete_rule`; confirm the tool reports the tier limitation when the destructive set is not enabled.

## 7. Decision register (quick review)

| ID | Phase | Decision | Recommendation | Owner input |
| --- | --- | --- | --- | --- |
| D1 | 0 | Catalog classification of new options | **Resolved:** `block_attacks` = advanced; no other new items | Done |
| D2 | 0 | Write-response propagation depth | **Resolved:** envelope synthesized from real per-family responses; the response is success confirmation only | Done |
| D3 | 0 | Failure taxonomy surface | One envelope + `error.kind`; empty and `RCODE 5` are not errors | No |
| D4 | 0 | Retention readability | **Resolved:** not readable; warn and document only | Done |
| D5 | 1 | Tier set and default | Five tiers; default Summary only; **implemented, content pending sign-off** | Yes |
| D6 | 1 | API identity / multi-entry naming | Stable id; disambiguated display name | No |
| D7 | 1 | Mounting mechanism | Owned API, not `llm.py` and not a `llm/` package | No |
| D8 | 2 | Tool naming | Source-agnostic, lexicon-correct (`get_inventory`) | Yes |
| D9 | 2 | Cause attribution pattern | **Resolved:** activity log for detail, overview for counts; ranked tools dropped | Done |
| D10 | 2 | Client terms in the inventory | Endpoint profile; assigned client **is** its own endpoint; expose `is_endpoint` | Yes |
| D11 | 3 | Destructive scope, first release | Tier yes; tools = `delete_rule` only | Yes |
| D12 | 3 | Endpoint-to-profile assignment | **Deferred:** still out of scope; widest blast radius | No |
| D13 | 3 | Bulk actions | Exclude from first release | No |
| D14 | 3 | `create_rule` in first release | Include; control tier, non-idempotent | Yes |
| D15 | 3 | `undo` for non-idempotent create | Always name `delete_rule`; report tier limit; session-scoped ids later | No |
| D16 | 2 | `test_domain` credential and `no_log` | **Resolved:** `no_log=1` verified to suppress records (3 lookups, 0 records) | Done |
| D17 | 2 | Activity Log default scope | Short window, all profiles, caller narrows | Yes |
| D18 | 0 | Analytics caching / rate limiting | **Rejected** — use filters, limits, and prompt warnings; do not build a cache | No |
| D19 | 2 | Catalog/policy bounding | Required scope + cap + honest truncation | No |

## 8. References

- `docs/ENGINEERING_FINDINGS.md` — Activity Log, retention, client correlation, DNS verdict, and write-response findings.
- **Control D published API docs** — https://docs.controld.com/reference/get-started. Every page has a `.md` twin (for example `https://docs.controld.com/reference/get_devices.md`), and there is a machine-readable index at **https://docs.controld.com/llms.txt**. Prefer these over scraping the HTML.
- `docs/ARCHITECTURE.md` — official lexicon, identity model, roaming endpoint behavior.
- `docs/DEVELOPMENT_STANDARDS.md` — lexicon standards, layer boundaries, mutation standards.
- `docs/QUALITY_REFERENCE.md` — quality-scale context.
- `docs/MCP_TOOL_REFERENCE.md` — the tool spec.
- Firewalla Local MCP precedent — `firewalla-local-ha`: `llm_api.py`, `llm_tools_common.py`, `llm_tools_read.py`, `llm_tools_control.py`, `docs/MCP_TOOL_REFERENCE.md`, `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_COMPLETED.md`.

## 9. Follow-up: published-docs reconciliation (not part of this initiative's code)

Control D now publishes a full API reference. A structured pass comparing the
published contract against `docs/ENGINEERING_FINDINGS.md` and the client is worth
doing, but it is research, not part of the tool build. Scope it as its own
task; do **not** bulk-write the vendor docs into the findings document.

**Items directly relevant to this initiative:**

1. **`clients` and `last_activity` are being removed from `GET /devices`.** The
   published note says both fields are slated for removal, temporarily available
   with `?last_activity=1`. **Status: already handled** — `async_get_devices`
   already requests `/devices?last_activity=1`. This is the minimum the user
   asked for and it is in place. The remaining risk is that a future removal
   breaks `associated_client_count`, which the endpoint client count depends on;
   the owner is raising this with Control D directly. Track it here so the
   failure mode is understood before it happens.
2. **Response conventions confirmed.** Success is `{body: {controllerName: []},
   success: true}` and failure is `{body: [], success: false, error: {message,
   code}}`, with **the first three digits of `error.code` matching the HTTP
   status**. The Phase 0.6 taxonomy can parse `error.message`/`error.code`
   instead of inferring from status alone.
3. **Profiles Restrictions is a separate API family**
   (`/profiles/restrictions`, `/profiles/{id}/restrictions/{name}`) and is
   **not** the same as Profile Options. `safesearch` appears in the restrictions
   catalog. Decision: keep reading and controlling `safesearch` as a profile
   option (it is presented on the options page), and treat the restrictions
   catalog as a separate future surface.
4. **`profile2` is live-only.** The published device schema documents `profile`
   but not `profile2`, so the findings doc should label `profile2` as
   live-observed rather than documented.
5. **Retention / analytics levels.** `/analytics/levels` is the authoritative
   No / Some / Full enum for `set_endpoint_analytics_logging`; "Some" stores
   **counts only, no queries**. Block counts can therefore be legitimately
   partial or absent by design, which the read tools should state.

**Items for the separate pass (not needed here):** `/access` (Known IPs),
`/devices/types`, `POST`/`DELETE /devices`, `/proxies`, `/organizations/*`,
`/billing/payments`, the SIEM log-field reference, and CSV export.

### Published API families not yet reviewed

Profiles, Filters, Services, Rules, Options, Access, Proxies, Organizations,
Billing, and the SIEM/log-field reference were only partially reviewed. The
follow-up pass should reconcile each against the client before any new tool is
built on it.


## 9. Builder handoff

Build in phase order; do not start Phase 1 before Phase 0's capture contract is settled, and do not start tool code before the Phase 1 spec exists.

**Phase 0 entry points**

1. `custom_components/controld_manager/api/client.py` — return the parsed body from write methods (currently `-> None`); add the Activity Log, ranked-domain, cause-breakdown, source-country, and DNS-verdict reads.
2. `custom_components/controld_manager/managers/integration_manager.py` — own the new read payloads and the catalog refresh; add the slug resolver.
3. `custom_components/controld_manager/services.py` — add `SupportsResponse.ONLY` read services (the pattern already exists for `get_catalog` at the bottom of `async_setup_services`).
4. `custom_components/controld_manager/const.py` — extend the supported option sets from the catalog refresh (`block_attacks` and any other new items).
5. `custom_components/controld_manager/translations/en.json` — regenerate translations for any new service or option strings.

**Phase 1–4 entry points**

1. `custom_components/controld_manager/const.py` — `llm_tools_supported()` and the tier constants (the predicate lives here, not in a single-function module, because both `__init__.py` and `config_flow.py` use it).
2. `custom_components/controld_manager/llm_api.py` — the API shell and tier-based tool selection (new; not `llm.py`).
3. `custom_components/controld_manager/llm_tools_common.py`, `llm_tools_read.py`, `llm_tools_control.py` — the tools (new).
4. `docs/MCP_TOOL_REFERENCE.md` — the spec (new; authored first).
5. `custom_components/controld_manager/__init__.py` — guarded registration and unload.
6. `custom_components/controld_manager/config_flow.py` — the tier option.
7. `custom_components/controld_manager/services.py` — `SupportsResponse.ONLY` read services (the pattern exists for `get_catalog` and `get_account_overview`).
8. `custom_components/controld_manager/managers/integration_manager.py` — read payload builders.
9. Tests under `tests/components/controld_manager/` — guard, AST, resolver, contract, and error-path suites.

**Rules the builder must hold**

- Tools call services only — never the client or managers.
- `vol.Schema` everywhere in tool schemas; never `probatio`.
- All four MCP annotations on every tool, including the non-idempotent class for `create_rule`.
- Both envelopes strictly JSON-serializable.
- Terminology from §3 is not negotiable; flag any place the upstream term conflicts with the repository lexicon rather than adapting silently.
