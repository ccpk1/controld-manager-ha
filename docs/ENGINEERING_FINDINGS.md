# Control D Manager engineering findings

## Purpose

This document records the verified engineering findings that emerged from proof-of-concept work, published payloads, and dashboard-backed API inspection.

It is not a historical log. It is a working guidebook for implementation decisions.

Use this document to answer four questions:

- what is already proven
- what design decisions those findings support
- what still remains uncertain
- which uncertainties actually matter before implementation starts

## How to read this document

- `Settled findings` are strong enough to guide implementation.
- `Working interpretation` means the evidence is strong but not fully closed.
- `Open questions` are the remaining gaps that may affect polish, analytics presentation, or later features.

## Representative samples

The findings below were driven by a small set of concrete examples that are useful to keep in mind when evaluating behavior:

- profiles:
  - `7580 Default Rule`
  - `Chads Devices`
- endpoints:
  - `Chads-Phone`
  - `Chads-iPad`
  - `firewalla`
- one known multi-profile endpoint:
  - `Chads-Phone`
- one known parent-child visibility example:
  - `Chads-iPad` as an explicitly assigned child client
- one known duplicate-name risk:
  - separate upstream endpoints can share the same display name

## Settled findings

### Identity and response normalization

These read-side contracts are stable enough to build against:

- `GET /users` returns `body` directly
- `GET /profiles` returns `body.profiles`
- `GET /devices` returns `body.devices`

Current identity anchors:

- config entry anchor: `users.id`
- secondary account correlation key: `users.PK`
- profile device anchor: profile `PK`
- endpoint entity anchor: `device_id`
- endpoint `PK` should be retained as a secondary correlation field

Implementation consequence:

- the client must normalize envelopes per endpoint rather than assuming one generic `body.<controller>` shape
- entity and device identity should be built from immutable upstream identifiers, never from display names

### Instance, profile, and endpoint model

The current design direction remains correct:

- one Home Assistant config entry per authenticated Control D instance
- one instance system device per Control D instance
- one Home Assistant profile device per Control D profile
- physical endpoints remain endpoint entities, not Home Assistant devices

Implementation consequence:

- this model is now supported by both the Control D API shape and the practical service and diagnostics goals for the integration

### Profiles API is a summary discovery surface

`GET /profiles` is richer than a simple list endpoint.

Observed useful fields include:

- identity and lifecycle:
  - `PK`
  - `user`
  - `org`
  - `name`
  - `updated`
  - `disable`
  - `lock`
- nested summary data:
  - `flt.count`
  - `cflt.count`
  - `ipflt.count`
  - `rule.count`
  - `svc.count`
  - `grp.count`
  - `opt.count`
  - `opt.data[]`
  - `da.do`
  - `da.status`

Settled interpretation:

- `GET /profiles` should be treated as the summary discovery source
- it is good enough for:
  - profile discovery
  - profile device creation
  - option discovery
  - first-pass capability detection
- it is not the right source for every item-level control

Implementation consequence:

- item-level service, filter, and rule controls should still use profile-scoped detail endpoints when those surfaces are selected for entities or services

### Pause and resume are profile-level writes

The upstream write contract is strong enough to support a paired service model.

Observed and verified:

- `PUT /profiles/{profile_id}` supports `disable_ttl`
- `disable_ttl = 0` resumes a disabled profile
- read-side pause state is not perfectly uniform
  - unpaused profiles may expose `disable: null`
  - paused profiles may expose `disable_ttl`

Settled interpretation:

- pause and resume should be implemented as profile-level writes
- the runtime should normalize both `disable` and `disable_ttl` into one internal paused-until field
- paired services remain the correct UX direction:
  - `controld_manager.pause_profile`
  - `controld_manager.resume_profile`

### Devices API is the endpoint inventory source

`GET /devices` should be treated as the authoritative endpoint inventory source.

Observed and verified:

- the API uses `device_id` for endpoint mutation
- real payloads can expose:
  - `profile`
  - `profile2`
  - `parent_device`
- docs also mention:
  - `/devices/users`
  - `/devices/routers`
  - transition-period `last_activity=1`

Settled interpretation:

- endpoint discovery should come from `GET /devices`
- profile membership should be derived from attached profile objects such as `profile` and `profile2`
- `GET /devices` is account- or organization-scoped inventory, not a documented profile-scoped list endpoint

### Multi-profile endpoint attachment is settled for v1

The chosen rule is now supported by published payloads.

Rule:

- attach the endpoint entity to the first attached upstream profile
- keep additional attached profiles as supplemental runtime metadata

Observed proof:

- `Chads-Phone` exposes:
  - `profile = Chads Devices`
  - `profile2 = 7580 Default Rule`

Settled interpretation:

- the endpoint entity belongs under the `Chads Devices` Home Assistant profile device
- `7580 Default Rule` remains metadata only for attachment purposes
- this is a Home Assistant organization rule only, not a Control D policy-precedence rule

### Parent-child visibility must not be inferred

The runtime must distinguish explicit endpoint inventory from latent client relationships.

Observed and verified:

- a child endpoint can expose `parent_device`
- Firewalla-managed child clients are not always visible as standalone endpoints until explicitly assigned

Settled interpretation:

- explicit endpoint inventory is not the same thing as every latent child client relationship
- endpoint discovery for v1 must remain based on explicit published inventory records
- parent-child metadata is useful context, but not a substitute for endpoint discovery

### Duplicate endpoint names are a real problem

Display names are not safe identifiers.

Observed and verified:

- two different Control D endpoints can share the same upstream display name
- at least one of those names may be effectively controlled by another product surface and not be user-editable

Settled interpretation:

- endpoint identity must remain anchored to `device_id`
- endpoint names are presentation only
- Home Assistant-owned `entity_id` disambiguation is sufficient for v1

## Service catalog findings

The service surface is much larger than the currently active service rows on one profile.

Observed and supplied evidence:

- `GET /services/categories` is expected to expose service categories with counts
- `GET /services/categories/all` is expected to expose the full available service catalog
- one sampled service catalog contains roughly 987 service items across categories such as `video`, `vendors`, `finance`, `tools`, and `social`
- profile-scoped service rows do not represent the full catalog size by themselves

Working interpretation:

- services are the true high-cardinality profile surface
- category is the correct first-class options-flow unit for service exposure
- per-profile service policy should store enabled categories, not a mirrored copy of every service item
- service entities created from an enabled category should default to disabled in the entity registry, with any default-enabled override treated as advanced and warned

## Service mutation findings

Service item writes appear to follow the same core action pattern used by rules.

Observed and supplied evidence:

- `GET /services/categories/audio` returns audio service rows with names
- `PUT /profiles/{profile_id}/services/{service_id}` accepts a service action payload
- one supplied example for `amazonmusic` returned:
  - `{"body":{"services":[{"do":0,"status":1}]},"success":true}`

Working interpretation:

- service item mutation uses a profile-scoped `PUT` endpoint per service item
- service action state uses the same core semantics seen elsewhere:
  - `do = 0` means block
  - `do = 1` means allow or bypass-style enablement when supported by the service surface
  - `status = 1` means enabled
  - `status = 0` means disabled
- this strengthens the case for treating service items as switch-like rule surfaces once exposed, even though the catalog-selection problem remains category-driven at the options-flow level

## Rules and groups findings

Rules are individually toggleable even when they belong to folders.

Observed and supplied evidence:

- `GET /profiles/{profile_id}/groups` returns folder-like groups with `PK`, `group`, `action`, and `count`
- `GET /profiles/{profile_id}/rules` returns top-level rules
- `GET /profiles/{profile_id}/rules/all` returns both top-level and grouped rules

Observed group patterns:

- normal organizational folder:
  - `action.status = 1`
  - `action.via = -1`
- forced allow folder:
  - `action.status = 1`
  - `action.do = 1`
- forced block folder:
  - `action.status = 1`
  - `action.do = 0`

Observed rule patterns:

- enabled block rule:
  - `action.do = 0`
  - `action.status = 1`
- enabled allow rule:
  - `action.do = 1`
  - `action.status = 1`
- disabled rule:
  - `action.status = 0`
- expiring rule:
  - `action.ttl = <unix timestamp>`

Settled interpretation:

- toggles are always at the rule level, including rules inside folders
- folders are important for naming and exposure policy, but they do not replace rule-level switch semantics
- rule exposure should store explicitly selected typed rule identities per profile
- later implementation should preserve room for additional action semantics such as expiring rules and folder-imposed allow or block defaults

## Endpoint status findings

The currently proven endpoint activity signal appears to be timestamp-driven.

Observed and supplied evidence:

- endpoint activity is currently represented as a timestamp rather than a definitive boolean online-state field

Working interpretation:

- the first endpoint-status surface should be derived from the activity timestamp if no stronger status field is proven
- endpoint status should use a configurable per-profile activity threshold
- approved threshold bounds:
  - default `15 minutes`
  - minimum `5 minutes`
  - maximum `60 minutes`
- overall polling cadence remains an entry-wide or refresh-group setting, not a per-endpoint setting

## Account and metadata findings

### Account metadata

Observed on `GET /users`:

- `id`
- `PK`
- `last_active`
- `status`
- `stats_endpoint`
- `twofa`
- `sso`
- `safe_countries`

Implementation guidance:

- `stats_endpoint` should be retained as meaningful instance metadata
- `last_active` is useful for diagnostics and possibly instance metadata, but should not be treated as a critical dependency

### Billing metadata

Observed on `GET /billing/products`:

- `name`
- `type`
- `proxy_access`
- `PK`
- `expiry`

Implementation guidance:

- billing product data is available to the runtime
- it should remain metadata-only until a concrete feature depends on it

### Analytics endpoint metadata

Observed on `GET /analytics/endpoints`:

- `PK`
- `title`
- `country_code`

Implementation guidance:

- `stats_endpoint` can be resolved into a user-facing region label
- this is a good candidate for instance metadata and diagnostics enrichment

## Analytics model findings

### High-level analytics model

The analytics system is not one single endpoint. It is a family of count-style endpoints with different scopes and different ranking surfaces.

Observed families include:

- `v2/statistic/count`
- `v2/statistic/count/triggerValue`
- `v2/statistic/count/question`
- `v2/statistic/count/srcCountry`
- `v2/client`

Common traits:

- analytics calls use a region-specific host such as `america.analytics.controld.com`
- response bodies commonly return normalized `startTime` and `endTime`
- the server does not necessarily echo the requested time window exactly

Working interpretation:

- returned time bounds should be treated as authoritative analytics metadata
- host selection is probably related to `stats_endpoint`, but that mapping is not fully closed yet

### Analytics client inventory is enrichment, not discovery

Observed on `v2/client`:

- `body.items` is an object map, not a list
- top-level items expose `lastActivityTime` and `clients`
- nested client records may expose:
  - `alias`
  - `host`
  - `mac`
  - `ip`
  - `vendor`

Settled interpretation:

- `v2/client` is telemetry-side enrichment
- it is not the authoritative source for endpoint discovery
- its identifiers are not yet proven to match `/devices` identifiers directly

Implementation consequence:

- use `/devices` for endpoint lifecycle
- treat `v2/client` as later enrichment or diagnostics until correlation is proven

### Profile-scoped statistics are proven

Profile-level analytics are now strong enough to inform entity planning.

Observed profile-scoped examples:

- `v2/statistic/count?profileId=<profile>`
- `v2/statistic/count/triggerValue?...&profileId=<profile>&trigger=filter`
- `v2/statistic/count/question?...&profileId=<profile>`

Settled interpretation:

- profile-scoped summary analytics are real and useful
- they are strong candidates for analytics sensors or analytics-backed attributes on profile devices

### Ranked breakdown endpoints are telemetry, not inventory

Observed ranked surfaces:

- `trigger=filter`
- `trigger=service`
- domain ranking via `count/question`
- source-country ranking via `count/srcCountry`

Settled interpretation:

- these endpoints describe observed traffic and block behavior
- they do not describe authoritative configuration inventory
- they should not be used to infer available profile filters or services

Implementation consequence:

- ranked analytics surfaces fit diagnostics, capped attributes, or carefully chosen summary sensors
- they are not suitable for one-entity-per-item modeling

### Ranked analytics values need a mapping layer

Observed mappings now include:

- `ads` -> `Ads & Trackers - Strict`
- `ads_small` -> `Ads & Trackers - Relaxed`
- `ads_medium` -> `Ads & Trackers - Balanced`
- `ai_malware` -> `AI Malware`
- `cryptominers` -> `Crypto`
- `typo` -> `Phishing`
- `truthsocial` -> `Truth Social`

Settled interpretation:

- raw ranked values are not always suitable as user-facing labels
- the integration should assume a repository-owned mapping layer is needed if these values are ever surfaced directly

### Direct query values are not yet round-trippable

Observed mismatch:

- ranked breakdown showed `ai_malware = 20`
- direct query with `trigger=filter&triggerValue[]=malware` returned `0`

Settled interpretation:

- direct `triggerValue[]` query inputs do not yet appear safe to derive from guessed UI labels or partial slug knowledge
- ranked output values and direct query input values should be treated as separate contracts until proven otherwise

## Top-card and security-overview derivations

### Endpoint-scoped derivation set

The clearest current derivation sample is the endpoint-scoped `Chads-Phone` set using:

- `endpointId[]=22dda9b8r7q`

### Total, encrypted DNS, and home-country traffic

Observed counts for the endpoint sample:

- total count: `82268`
- `srcCountry=US` count: `82268`
- encrypted protocol count using `doh`, `doq`, `dot`, `doh3`: `82268`

Settled derivations:

- `Home Country Traffic = srcCountry(home_country) / total`
- `Encrypted DNS = encrypted_protocol_total / total`

For the sample endpoint:

- `Home Country Traffic = 82268 / 82268 = 100%`
- `Encrypted DNS = 82268 / 82268 = 100%`

These match the screenshot exactly.

### Blocked and bypassed cards are not sums of visible ranked rows

Observed endpoint-scoped blocked rows:

- filters:
  - `ads = 8561`
  - `ads_small = 825`
  - `ads_medium = 272`
  - `ai_malware = 20`
  - `cryptominers = 15`
- services:
  - `truthsocial = 3`

Visible subtotal:

- filters subtotal = `9693`
- filters plus visible services = `9696`

Screenshot values:

- blocked: `10K (12.1%)`
- bypassed: `72.3K (87.9%)`
- redirected: `0`
- total: `82.2K`

Working interpretation:

- the visible ranked rows are top-N slices, not the full blocked total
- the blocked card must be derived from a fuller blocked-total query or a larger underlying result set
- the integration must not compute blocked totals by summing visible ranked rows

### Benign Blocks is now understandable

Supplied product definition:

- `Benign Blocks` = share of blocks attributable to non-security filters
- excluded from the benign numerator: Malware and Phishing

For the endpoint sample, visible rows produce:

- benign visible subtotal:
  - `ads + ads_small + ads_medium + cryptominers`
  - `8561 + 825 + 272 + 15 = 9673`
- visible security subtotal:
  - `ai_malware = 20`
- visible filter total:
  - `9673 + 20 = 9693`
- visible benign share:
  - `9673 / 9693 = 99.79%`

Working interpretation:

- `Benign Blocks 100%` is plausibly a rounded result, not evidence of zero security-category blocks
- the metric is category-sensitive, not simply `blocked / total`

This is strong enough for design guidance, but not fully closed because phishing was absent from the sampled endpoint-ranked rows.

## Build-start blocker split

The remaining open questions are not equally important.

Previously identified blockers for starting runtime implementation:

- final attached-profile sibling normalization beyond `profile` and `profile2`
- final refresh-group split and options-flow boundaries
- first entity slice decision across instance, profile, and endpoint surfaces
- final paused-profile read normalization contract

Current non-blockers for starting scaffolding:

- exact blocked-card total derivation
- complete analytics label mapping coverage
- broader dashboard-scoped analytics interpretation details
- billing-product presentation choices

Implementation consequence:

- runtime scaffolding can start once the blocker list above is frozen
- deeper analytics refinement can continue in parallel without holding up the first build

Closeout status:

- the blocker list above is now frozen in the active plan
- Phase 2 can be treated as complete for implementation sequencing
- the remaining analytics-heavy questions should be tracked as deferred follow-up work rather than as runtime-foundation blockers

## Implementation guidance from these findings

### What should be treated as inventory

- account identity and metadata from `/users`
- profile inventory and summary capability data from `/profiles`
- endpoint inventory and membership data from `/devices`

### What should be treated as telemetry

- ranked filter, service, domain, and source-country analytics
- client telemetry from `v2/client`
- top-card and security-overview analytics derived from count endpoints

### What should not be inferred

- child endpoints that are not present in explicit inventory
- endpoint totals from visible ranked rows alone
- direct query slugs from guessed UI labels
- multi-profile policy behavior from the first attached profile alone

### What is safe to decide now

- endpoint identity must use `device_id`
- duplicate names require explicit display disambiguation
- paired profile pause and resume services are the right first service direction
- polling should be split into refresh groups with bounded options
- analytics surfaces must distinguish scope explicitly:
  - instance-level or broader dashboard scope
  - profile scope
  - endpoint scope
- analytics ranking surfaces are better suited to capped attributes, diagnostics, or carefully selected summary sensors than to one-entity-per-row models

## Open questions that still matter

These are the remaining gaps that are worth resolving before or during implementation. They are narrower than the original investigation scope.

- how should the runtime normalize attached-profile sibling fields beyond the current `profile` and `profile2` cases
- how should the first implementation refresh groups be named and bounded
- how exactly should parent-child endpoint metadata surface in v1
- how does the analytics host selection map from `stats_endpoint`
- how do `v2/client` identifiers correlate, if at all, to `/devices` identifiers
- how do `action` values map across blocked, bypassed, and redirected views
- what exact query backs the full blocked-card total
- what exact denominator does `Benign Blocks` use when phishing or other security categories are present outside the visible ranked rows
- how should country scoping and protocol scoping be treated in the default analytics model
- which analytics surfaces belong in the first entity slice versus diagnostics only
- which endpoint-scoped analytics, if any, belong in the first entity slice versus a later follow-on pass
- should billing product metadata remain diagnostics-only or surface on the instance system device
- can later filter and service pause semantics share the same target-resolution family as profile pause and resume

## Targeted follow-up captures

These are the most useful remaining captures, in descending order of value:

1. One blocked or bypassed sample that proves the exact blocked-card or bypassed-card total query.
2. One sample where phishing is non-zero so `Benign Blocks` can be validated against both excluded security categories.
3. One sample that correlates a `/devices` endpoint to a `v2/client` analytics item.
4. One sample that shows whether organization scenarios expose `profile3` or another attached-profile variant.
5. One sample that confirms how bypassed and redirected views map through the analytics endpoints.

## Purpose

This document records engineering-focused proof-of-concept findings that help narrow implementation options before they are promoted into the durable architecture contract.

It should capture concrete observations, practical constraints, and next actions rather than abstract design theory.

## Current example set

The current working example includes:

- profiles `7580 Default Rule` and `Chads Devices`
- endpoints `Chads-iPad`, `Chads-Phone`, and `firewalla`
- one known multi-profile endpoint: `Chads-Phone`
- one known naming-risk case: a separate endpoint also named `Chads-Phone` exists in Control D terms because of the Firewalla client model, and the upstream name is not always user-editable

## Observed dashboard state

From the supplied dashboard screenshots:

- profile `7580 Default Rule` shows `2 Endpoints`
- profile `Chads Devices` shows `2 Endpoints`
- endpoint `firewalla` appears attached to `7580 Default Rule`
- endpoint `Chads-iPad` appears attached to `Chads Devices`
- endpoint `Chads-Phone` appears attached to both `Chads Devices` and `7580 Default Rule`

Immediate consequence:

- the updated ownership decision produces a concrete answer for this case
- `Chads-Phone` should attach to the first attached upstream profile only
- in the supplied payload, that means `Chads Devices` remains the owning Home Assistant profile device and `7580 Default Rule` remains supplemental membership metadata

## Cross-check against known live API behavior

Earlier authenticated API inspection established:

- `GET /profiles` returns `body.profiles`
- `GET /devices` returns `body.devices`
- published `GET /devices` payloads can expose more than one attached profile per endpoint
- the supplied published API sample includes `profile2` on the multi-profile endpoint `Chads-Phone`
- live `GET /profiles` did not expose an endpoint-count field in the inspected sample

Engineering consequence:

- the published API does expose multi-profile membership for the currently observed two-profile case
- the updated profile-1 ownership rule is implementable directly from published API data for the currently observed payload shape

## Profiles API findings

The supplied `GET /profiles` payload adds an important second layer to the planning picture: Control D exposes a compact profile-summary inventory that is rich enough for discovery and options planning even before detailed per-profile reads are loaded.

### Observed profile summary shape

Each profile row includes:

- stable identity and lifecycle fields:
  - `PK`
  - `user`
  - `org`
  - `name`
  - `updated`
  - `disable`
  - `lock`
- a nested `profile` summary object containing:
  - `flt.count`
  - `cflt.count`
  - `ipflt.count`
  - `rule.count`
  - `svc.count`
  - `grp.count`
  - `opt.count`
  - `opt.data[]` with option `PK` and `value`
  - `da.do`
  - `da.status`

Additional observed nuance:

- paused and unpaused profiles do not currently read back with one perfectly uniform field shape
- unpaused profiles may expose `disable: null`
- a paused profile in the supplied sample exposed `disable_ttl: 1775067384`

### Engineering consequence

- `GET /profiles` is not just a name list; it is a useful profile-summary inventory
- the payload is rich enough to drive profile discovery, profile device creation, and first-pass planning for what kinds of controls a profile can support
- `opt.data` is especially important because it already exposes concrete option keys and current values without requiring a second request for every profile just to discover candidate profile-option controls
- the category counts are strong candidates for options-flow discovery and later entity-selection UX because they tell us whether a profile currently has filters, services, custom rules, or options worth drilling into
- pause-state normalization cannot assume one fixed read key; the runtime should normalize both `disable` and `disable_ttl` variants into one internal paused-until representation

### Profile summary versus detailed profile reads

The profile list payload appears to be best treated as a summary layer, not the full source of truth for all switchable controls.

Why:

- counts tell us how much exists, not necessarily the exact item-level state needed to create one switch per service or one switch per filter
- `opt.data` exposes item-level option state directly, but `svc.count`, `flt.count`, and `rule.count` remain summary numbers only in the list payload

Current recommendation:

- use `GET /profiles` as the summary discovery source
- use profile-scoped detail endpoints such as “list all services by profile” and equivalent filter or rule list endpoints as the detailed source when the user chooses to expose item-level controls
- do not fetch every possible per-profile detail endpoint eagerly during the base inventory refresh unless the entity model proves that cost is justified

## Account and metadata findings

The newly supplied account-adjacent endpoints add useful metadata beyond basic identity.

### `GET /users`

Confirmed account fields now include:

- stable instance anchors: `id`, `PK`
- activity and posture data: `last_active`, `status`, `stats_endpoint`, `twofa`
- auth/provider metadata: `sso`
- geo-related metadata: `safe_countries`

Engineering consequence:

- `stats_endpoint` is a meaningful runtime field, not just incidental account metadata
- `last_active` may be useful for diagnostics or instance-level metadata, but should not be treated as a critical entity dependency without proving long-term stability

### `GET /billing/products`

Observed product fields include:

- `name`
- `type`
- `proxy_access`
- `PK`
- `expiry`

Engineering consequence:

- billing products may be useful as instance-system-device metadata or diagnostics context
- the current sample shows a `trial` product, which may eventually matter for repairs, warnings, or capability gating if product tiers affect available features
- this should remain metadata-only until the repository proves a concrete user-facing behavior depends on it

### `GET /analytics/endpoints`

Observed fields include:

- endpoint `PK`
- `title`
- `country_code`

Engineering consequence:

- `stats_endpoint` from `GET /users` can now be resolved into a readable analytics region title through a published API call
- this is a good candidate for instance metadata display, diagnostics enrichment, or future options flow choices if analytics-region behavior ever becomes configurable

### Immediate planning consequence

- profile-level switch planning should distinguish between:
  - summary-driven controls that can be derived directly from `GET /profiles`
  - detail-driven controls that require a second per-profile endpoint
- this split is likely the right foundation for user-selectable switch creation, because it avoids treating all profile surfaces as equally cheap to discover and maintain

## Devices API documentation findings

The current `GET /devices` documentation adds several useful details, but it still does not document a profile-selected device listing contract.

### What the docs now clarify

- `GET /devices` is documented as listing all endpoints associated with an account or organization
- the docs explicitly mention type-specific variants:
  - append `/users` to retrieve only user-type devices
  - append `/routers` to retrieve only router-type devices
- the docs mention an optional `last_activity=1` query parameter if `last_activity` and `clients` are still needed during the transition period
- the response schema documents a required singular nested `profile` object for each device
- the supplied published API payload shows that real responses may also include `profile2`

### What the docs do not clarify

- there is no documented query parameter or documented path variant that says “list devices for a selected profile”
- there is no documented statement that `GET /devices` can be scoped by profile membership
- there is no documented profile endpoint-count field in the current inspected profile list payload shape

### Engineering consequence

- the current docs strengthen the idea that `GET /devices` is an account- or organization-scoped inventory endpoint, not a documented profile-scoped inventory endpoint
- the schema examples appear incomplete relative to the observed published payload because real responses may include `profile2`
- the account-scoped device inventory is sufficient to derive profile membership counts even without a separate profile-scoped list endpoint
- the `/users` and `/routers` variants may still be useful later for category-specific refresh groups or diagnostics, but they do not solve the current profile-membership problem
- the `last_activity=1` transition note matters for entity planning because endpoint telemetry surfaces should not depend on fields the upstream API is actively removing without a fallback strategy

## Multi-profile attachment findings

### What is now clear

- the chosen attachment rule is operationally precise:
  - attach the endpoint entity to the first attached upstream profile
  - keep additional attached profiles as normalized membership metadata
- this rule is a presentation and organization rule only
- it must not be interpreted as policy precedence, because Control D evaluates multi-profile endpoints through merged rule classes rather than through a true primary-profile-wins model

### What data the runtime still needs

To execute the updated rule honestly, the runtime needs:

- the first attached upstream profile for ownership
- the full set of additional attached profiles for metadata and future behavior

The supplied published API sample proves both requirements for the currently observed two-profile case:

- owning attachment is exposed through `profile`
- additional membership is exposed through `profile2`

### Practical paths forward

Path 1: documented API path

- treat `GET /devices` as the authoritative published inventory source and normalize all discovered attached-profile fields from that payload
- this is now the primary path

Path 2: dashboard-backed discovery path

- inspect the browser network traffic used by the Control D dashboard profile and endpoint pages
- if the dashboard uses a different read endpoint or a richer payload, determine whether it is stable enough to rely on
- this may clarify whether the missing data is merely undocumented rather than unavailable

Path 3: fallback runtime policy path

- if upstream read data remains incomplete, do not silently guess multi-profile membership from partial payloads
- instead, either defer true multi-profile attachment or introduce an explicit override mechanism later

Current recommendation:

- treat Path 1 as proven for the current two-profile case and move multi-profile attachment out of the blocked category
- keep Path 2 only as a follow-up if later examples expose additional attachment fields such as `profile3` for organization scenarios

## Multi-profile sample findings

The supplied `GET /devices` sample provides a working published-API proof for the current multi-profile model.

Observed endpoint records:

- `Chads-iPad` has `profile = Chads Devices`
- `Chads-Phone` has `profile = Chads Devices` and `profile2 = 7580 Default Rule`
- `firewalla` has `profile = 7580 Default Rule`
- `kaden-spyphone` has `profile = Kids Profile`
- `Paytons-Phone` has `profile = Paytons Phone`

Result against the chosen attachment rule:

- `Chads-Phone` is multi-profile
- `profile` is `Chads Devices`
- `profile2` is `7580 Default Rule`
- `Chads Devices` becomes the owning Home Assistant profile device for the endpoint entity
- `7580 Default Rule` remains attached metadata only for v1 ownership purposes

Engineering consequence:

- for the currently observed two-profile case, the repository no longer needs another data source to implement the chosen attachment rule
- the runtime should normalize attached-profile fields generically, for example any top-level device keys matching `profile`, `profile2`, `profile3`, and future siblings if they appear
- the runtime should always treat the first attached upstream profile as the owning Home Assistant device attachment unless a later architecture decision explicitly changes that rule

## Parent-child endpoint findings

The supplied sample also exposes a `parent_device` object on `Chads-iPad` with:


Engineering consequence:


### Firewalla child-client visibility constraint

One important behavior refinement is now known:

- Firewalla device clients are technically associated with the Firewalla-managed profile context such as `7580 Default Rule`
- those child clients do not appear as independently listed profile members in the same way until one of those clients is explicitly assigned to a profile
- `Chads-iPad` is an example of a child client that becomes visible as its own endpoint once explicitly assigned

Engineering consequence:

- profile membership visible in `GET /devices` is not the same thing as every latent client relationship implied by a parent resolver
- the runtime must treat parent-child endpoint metadata as a separate concern from explicit profile assignment visibility
- endpoint discovery rules for v1 should remain based on explicit published inventory records, not on inferred child clients hidden behind a parent endpoint

## Analytics client inventory findings

The supplied regional analytics payload at `https://america.analytics.controld.com/v2/client` adds an important telemetry-side view that is different from the account inventory returned by `GET /devices`.

### Observed analytics payload shape

- the response envelope is `{"success": true, "body": {"items": {...}}}`
- `body.items` is an object map keyed by analytics item identifiers rather than a list
- each top-level item currently exposes at least:
  - `lastActivityTime`
  - `clients`
- some top-level items have an empty `clients` map
- populated `clients` maps are keyed by separate client identifiers and the observed child records may include:
  - `lastActivityTime`
  - `alias`
  - `host`
  - `mac`
  - `ip`
  - `os`
  - `vendor`

### Engineering consequence

- this payload appears to expose network-observed client telemetry behind at least some parent analytics items even when those child clients are not necessarily represented as standalone Control D endpoints in `GET /devices`
- this strongly reinforces the existing rule that explicit endpoint inventory and analytics-side client telemetry are different surfaces and must not be merged casually
- the integration should treat `GET /devices` as the authoritative discovery source for endpoint entities and treat the analytics client payload as enrichment only until key correlation and lifecycle semantics are proven
- the payload is still valuable because it provides a concrete upstream source for last-activity-style client telemetry and for validating the Firewalla-style child-client visibility constraint

### New uncertainty narrowed by this sample

- analytics reads appear to use a region-specific host, which may be related to the account `stats_endpoint`, but that host-selection contract is not yet proven
- the top-level analytics item identifiers are not yet proven to be the same identifiers used by `GET /devices`
- the child client records are not yet proven to map 1:1 to standalone Control D endpoints, so they should not drive v1 entity creation

## Profile analytics count findings

The supplied regional analytics query for `v2/statistic/count/triggerValue` adds the first concrete profile-scoped analytics-count contract.

### Observed analytics count request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count/triggerValue`
- observed query parameters:
  - `action=0`
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
  - `profileId=<profile PK>`
  - `sortOrder=desc`
  - `trigger=filter`

### Observed analytics count response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized time bounds:
  - `startTime`
  - `endTime`
- `body.counts` is a descending list of `{value, count}` rows
- the observed rows use internal filter identifiers rather than friendly dashboard labels:
  - `ads`
  - `ads_small`
  - `ads_medium`
  - `ai_malware`
  - `cryptominers`

### Cross-check against the supplied dashboard screenshot

The returned counts align with the shown blocked-filter dashboard rows:

- `ads` -> `Ads & Trackers - Strict` -> `8561`
- `ads_small` -> `Ads & Trackers - Relaxed` -> `810`
- `ads_medium` -> `Ads & Trackers - Balanced` -> `272`
- `ai_malware` -> `AI Malware` -> `20`
- `cryptominers` -> `Crypto` -> `15`

Engineering consequence:

- this is strong evidence that `action=0` on this endpoint corresponds to the blocked view shown in the dashboard, but that mapping should still be treated as observed rather than fully documented until another action value is captured
- profile-scoped filter analytics are now proven to be available without walking every filter detail endpoint first
- the API returns stable-looking internal value slugs, while the dashboard renders friendlier labels; that means a user-facing entity model would need a translation or lookup layer rather than exposing raw slugs directly
- the server does not echo the requested time range exactly, because the supplied sample returned normalized `startTime` and `endTime` values different from the raw query inputs
- this endpoint is a strong candidate for profile analytics sensors or diagnostic attributes, but not for one-entity-per-filter by default because the returned set is top-count style analytics data rather than a full authoritative profile configuration inventory

### Broader blocked-tab sample without `profileId`

A later sample hit the same endpoint shape without `profileId`:

- path: `/v2/statistic/count/triggerValue`
- query included:
  - `action=0`
  - `trigger=filter`
  - `sortOrder=desc`
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
- query omitted `profileId`

Returned rows included:

- `ads_small` -> `25879`
- `ads` -> `8778`
- `ads_medium` -> `1862`
- `typo` -> `1786`
- `ai_malware` -> `101`
- `cryptominers` -> `16`

Cross-check against the supplied blocked-panel screenshot:

- `ads_small` -> `Ads & Trackers - Relaxed` -> `25879`
- `ads` -> `Ads & Trackers - Strict` -> `8778`
- `ads_medium` -> `Ads & Trackers - Balanced` -> `1862`
- `typo` -> `Phishing` -> `1786`
- `ai_malware` -> `AI Malware` -> `101`
- `cryptominers` -> `Crypto` -> `16`

Additional engineering consequence:

- `triggerValue` is not only profile-scoped; it can also back a broader blocked-tab surface without `profileId`
- the internal slug mapping is now stronger because `typo` aligns with the user-facing `Phishing` label in the dashboard
- the integration should separate profile-scoped statistics from broader dashboard-scoped breakdowns instead of assuming one scope for all `triggerValue` calls

## Service analytics findings

The supplied regional analytics query for `v2/statistic/count/triggerValue` with `trigger=service` adds the services-panel breakdown contract.

### Observed service analytics request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count/triggerValue`
- observed query parameters:
  - `action=0`
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
  - `sortOrder=desc`
  - `trigger=service`
- the supplied sample omitted `profileId`

### Observed service analytics response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized:
  - `startTime`
  - `endTime`
- `body.counts` is a descending list of `{value, count}` rows
- the supplied sample returned:
  - `truthsocial` -> `5`

### Cross-check against the supplied blocked-panel screenshot

The returned row aligns directly with the shown services panel:

- `truthsocial` -> `Truth Social` -> `5`

Engineering consequence:

- `triggerValue` is now proven to support at least two ranked breakdown classes: `filter` and `service`
- the service breakdown appears to use internal slugs that can still require friendly-name mapping for user-facing presentation
- this endpoint family is better modeled as analytics breakdown telemetry than as authoritative service configuration state
- because the sample omitted `profileId`, the current evidence again points to at least one broader blocked-tab scope beyond per-profile statistics

## Profile analytics total findings

The supplied regional analytics query for `v2/statistic/count` adds the matching profile-level total counter for the same dashboard statistics surface.

### Observed analytics total request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count`
- observed query parameters:
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
  - `profileId=<profile PK>`
  - `srcCountry[]=US`

### Observed analytics total response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized:
  - `startTime`
  - `endTime`
- `body.count` exposes one aggregate integer total
- the supplied sample returned `count = 78033`

### Cross-check against the supplied statistics screenshot

The returned total aligns with the dashboard `Total` card:

- API `78033`
- dashboard `78K`

Combined with the earlier trigger-value sample and screenshot:

- blocked breakdown sum is `8561 + 810 + 272 + 20 + 15 = 9678`
- dashboard blocked card shows `9.7K`
- dashboard total card shows `78K`
- dashboard redirected card shows `0`

Engineering consequence:

- `v2/statistic/count` appears to be the aggregate total companion to the more detailed `v2/statistic/count/triggerValue` endpoint
- this makes a conservative summary analytics model much more realistic: a profile can likely expose total activity plus a small number of breakdown attributes or secondary sensors without requiring full dashboard scraping
- `srcCountry[]` is now proven as part of the request contract for at least one dashboard summary view, so country scoping may be a first-class analytics filter rather than incidental UI state
- the server again normalizes the requested time window, which reinforces that Home Assistant should treat the returned period as authoritative metadata for any surfaced analytics state
- the screenshot now gives a stronger observed mapping between the dashboard cards and the analytics endpoints, but bypassed and redirected still need direct API samples before those cards can be modeled confidently

## Profile analytics domain findings

The supplied regional analytics query for `v2/statistic/count/question` adds a third profile-scoped summary surface: ranked queried domains for the statistics panel.

### Observed analytics domain request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count/question`
- observed query parameters:
  - `action[]=0`
  - `limit=500`
  - `sortOrder=desc`
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
  - `profileId=<profile PK>`

### Observed analytics domain response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized:
  - `startTime`
  - `endTime`
- `body.counts` is a descending list of `{value, count}` rows
- the observed `value` fields are raw queried domains such as:
  - `firebaselogging-pa.googleapis.com`
  - `app-measurement.com`
  - `app-analytics-services.com`
  - `dit.whatsapp.net`
  - `p.controld.com`

### Cross-check against the supplied domains screenshot

The top rows align directly with the shown statistics panel:

- `firebaselogging-pa.googleapis.com` -> `1371`
- `app-measurement.com` -> `1339`
- `app-analytics-services.com` -> `1179`
- `dit.whatsapp.net` -> `266`
- `p.controld.com` -> `245`

Engineering consequence:

- this endpoint appears to back the dashboard domain-ranking panel for the same statistics view as the earlier total and blocked-breakdown calls
- `action[]=0` again looks like the blocked-side filter for this surface, which strengthens the observed blocked mapping but still does not fully document the action contract
- unlike `triggerValue`, this endpoint already returns user-facing domain values and therefore does not appear to require a slug-to-label translation layer
- `limit=500` suggests the dashboard can request a large ranked result set, which argues against one-entity-per-domain and in favor of either capped attributes, diagnostics, or on-demand service responses if this surface is exposed at all
- because the values are raw domains rather than configuration objects, this endpoint is clearly telemetry and should not influence entity discovery or policy inventory

## Protocol-scoped analytics total findings

The supplied regional analytics query for `v2/statistic/count` without a `profileId` adds a different analytics shape from the earlier profile statistics samples.

### Observed protocol-scoped request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count`
- observed query parameters:
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`
  - `protocol[]=doh`
  - `protocol[]=doq`
  - `protocol[]=dot`
  - `protocol[]=doh3`
- no `profileId` is present in the supplied sample

### Observed protocol-scoped response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized:
  - `startTime`
  - `endTime`
- `body.count` exposes one aggregate integer total
- the supplied sample returned `count = 549007`

### Engineering consequence

- this does not look like the same contract as the earlier profile-level total card call because the request is scoped by transport protocols and omits `profileId`
- the follow-up `v2/statistic/count/srcCountry` sample now proves that the earlier `549007` count maps to the `Sources` panel rather than to a hidden helper path
- the protocol list suggests the dashboard may aggregate only encrypted DNS transport traffic for at least part of the source-country visualization
- this is therefore no longer purely speculative internal math; it is a visible analytics surface, but one that appears broader than a single profile statistics card
- the integration should still avoid surfacing this as a default first-wave sensor until scope, filtering defaults, and its relationship to profile versus instance context are proven

## Source-country analytics findings

The supplied regional analytics query for `v2/statistic/count/srcCountry` closes the loop on the earlier `549007` source count.

### Observed source-country request shape

- host: `https://america.analytics.controld.com`
- path: `/v2/statistic/count/srcCountry`
- observed query parameters:
  - `sortOrder=desc`
  - `startTime=<ISO timestamp>`
  - `endTime=<ISO timestamp>`

### Observed source-country response shape

- the response envelope is `{"success": true, "body": {...}}`
- `body` includes normalized:
  - `startTime`
  - `endTime`
- `body.counts` is a descending list of `{value, count}` rows
- the supplied sample returned:
  - `US` -> `549007`

### Cross-check against the supplied sources screenshot

The returned source-country row aligns directly with the shown `Sources` panel:

- `US` -> `549007`

Engineering consequence:

- the earlier protocol-filtered aggregate count is now much more likely part of the source-country analytics surface rather than an invisible helper query
- `v2/statistic/count/srcCountry` appears to be a geo-ranking endpoint analogous to the earlier domain-ranking endpoint, but with country codes instead of domain names
- because this is ranked telemetry rather than stable configuration state, it fits better as diagnostics, capped attributes, or a later analytics sensor set than as one entity per country
- the omission of `profileId` in the supplied sample keeps one important scope question open: this may be account- or dashboard-scope analytics rather than profile-scope analytics

## Endpoint-scoped statistics derivation findings

The supplied `Chads-Phone` sample set is the clearest analytics derivation set so far because the screenshot and the requests align around one explicit endpoint selector:

- `endpointId[]=22dda9b8r7q`

### Observed endpoint-level totals

The following calls all returned the same aggregate total:

- `v2/statistic/count?endpointId[]=22dda9b8r7q` -> `82268`
- `v2/statistic/count?endpointId[]=22dda9b8r7q&srcCountry[]=US` -> `82268`
- `v2/statistic/count?endpointId[]=22dda9b8r7q&protocol[]=doh&protocol[]=doq&protocol[]=dot&protocol[]=doh3` -> `82268`
- `v2/statistic/count/srcCountry?...&endpointId[]=22dda9b8r7q` -> `US = 82268`

Cross-check against the screenshot:

- dashboard total card: `82.2K`
- dashboard source country row: `United States 82268`
- security overview shows `Encrypted DNS 100%`
- security overview shows `Home Country Traffic 100%`

Engineering consequence:

- endpoint-scoped analytics are now clearly supported through repeated `endpointId[]` query parameters
- for this endpoint, the total count, U.S. source-country count, and encrypted-protocol count are all identical
- this strongly suggests these two security-overview metrics are derived as simple ratios against the same total:
  - `Home Country Traffic = srcCountry(home_country) / total = 82268 / 82268 = 100%`
  - `Encrypted DNS = encrypted_protocol_total / total = 82268 / 82268 = 100%`
- this is the strongest evidence yet that at least some top-of-page percentages are derived from ordinary count endpoints rather than a separate hidden summary API

### Observed endpoint-level blocked breakdowns

The endpoint-scoped blocked breakdown calls returned:

- filters:
  - `ads` -> `8561`
  - `ads_small` -> `825`
  - `ads_medium` -> `272`
  - `ai_malware` -> `20`
  - `cryptominers` -> `15`
- services:
  - `truthsocial` -> `3`

Cross-check against the screenshot:

- filters panel rows match exactly
- services panel row `Truth Social 3` matches exactly

Visible blocked-subpanel sum:

- filter rows sum to `8561 + 825 + 272 + 20 + 15 = 9693`
- adding the visible service row gives `9696`

### Comparison to the blocked and bypassed cards

The screenshot shows:

- blocked: `10K (12.1%)`
- bypassed: `72.3K (87.9%)`
- redirected: `0`
- total: `82.2K`

Derived observations:

- `9696 / 82268 = 11.79%`, which is close to but not equal to the shown `12.1%`
- if the displayed blocked percentage is rounded from an underlying total, the blocked card implies roughly `9950` blocked requests
- that leaves roughly `250` blocked requests not accounted for by the visible first-page filter and service rows
- `82268 - 9950 = 72318`, which aligns closely with the displayed bypassed `72.3K (87.9%)`

Engineering consequence:

- the top cards are probably derived from a fuller blocked-total calculation than the visible first-page lists alone
- the visible ranked rows should be treated as partial top-N breakdowns, not as the authoritative full blocked total
- the integration should not compute blocked totals by summing visible ranked analytics rows

### Benign Blocks definition and derivation

The supplied product definition closes one of the remaining security-overview questions:

- `Benign Blocks` = share of blocks attributable to non-security filters
- explicitly excluded from the benign numerator: `Malware` and `Phishing`

Current interpretation:

- the numerator is blocked traffic attributable to non-security filter categories
- the security categories excluded from the benign numerator are at least:
  - malware-style categories such as `ai_malware`
  - phishing-style categories, which earlier mapping work ties to the slug `typo`

For the `Chads-Phone` endpoint sample:

- visible non-security filter rows are:
  - `ads` -> `8561`
  - `ads_small` -> `825`
  - `ads_medium` -> `272`
  - `cryptominers` -> `15`
- visible security filter rows are:
  - `ai_malware` -> `20`
  - phishing/`typo` is not present in the endpoint-scoped ranked rows

Visible benign-filter subtotal:

- `8561 + 825 + 272 + 15 = 9673`

If the denominator is the visible filter-block total from the same ranked set:

- total visible filter blocks = `9673 + 20 = 9693`
- benign share = `9673 / 9693 = 99.79%`

Engineering consequence:

- this explains why the dashboard can legitimately show `Benign Blocks 100%` even when a small malware count is present: the value is plausibly rounded from approximately `99.8%`
- `Benign Blocks` now looks like a derived percentage from ranked filter-block categories rather than a separate opaque summary API
- this also means the metric is category-sensitive, not simply `blocked / total`
- for implementation planning, `Benign Blocks` belongs in the same derived-analytics family as `Encrypted DNS` and `Home Country Traffic`, but it depends on confirmed category mapping for security versus non-security filters

### Trigger-value semantics refinement

One endpoint-scoped test also returned:

- `v2/statistic/count?...&endpointId[]=22dda9b8r7q&trigger=filter&triggerValue[]=malware` -> `0`

Engineering consequence:

- direct `triggerValue[]` query inputs do not necessarily use the same labels that appear in the ranked breakdown output or the UI
- `malware` is not equivalent to the ranked `ai_malware` value in the observed contract
- the repository should not assume it can round-trip human-friendly labels or guessed slugs back into filter analytics queries without verification

## Dashboard-backed API discovery findings

Updated interpretation:

- because Control D states that the dashboard is API-based, dashboard network inspection is now a legitimate capability-discovery method for published API usage rather than an ad hoc workaround
- this should be used to discover additional supported API calls and payloads that the public reference pages may not surface clearly enough

Engineering consequence:

- dashboard/API capability discovery should now be treated as a normal research path for planning
- the repository should prefer published or dashboard-backed API behavior over inference when deciding what surfaces can support entities, services, or options

## Duplicate-name findings

The example set introduces a separate and important constraint: endpoint display names are not reliable identifiers and may not be unique even within one Control D instance.

The risk is not hypothetical:

- two distinct Control D endpoints can share the same upstream display name
- at least one of those names may be effectively managed by another Control D or Firewalla-controlled surface and may not be user-editable

Engineering consequence:

- the integration must treat endpoint names as presentation only
- endpoint identity must remain anchored to `device_id`
- profile device attachment must not depend on endpoint names

Why this matters:

- the duplicate-name problem is separate from the multi-profile problem
- even if multi-profile attachment is solved, duplicate names still remain a presentation concern

Current contract:

- endpoint entities should start with the endpoint name followed by the capability label
- the integration does not need to add its own duplicate-name fallback suffixes
- Home Assistant may disambiguate duplicate final `entity_id` values with `_2` or similar when required

## Pause and resume findings

Firewalla Local remains the best current reference for service ergonomics, not for upstream semantics.

Reusable pattern:

- paired pause and resume services
- explicit target field
- explicit timing validation
- translation-ready errors for incompatible input combinations

Current recommendation:

- keep `controld_manager.pause_profile` and `controld_manager.resume_profile` as the first concrete pair
- do not force filters, services, or other policy objects into that same service family until Control D confirms they share a coherent upstream pause contract
- treat sub-resource pause support as a later capability review, not as a requirement for the first profile pause implementation

Additional consequence from the latest sample:

- the read path for paused profiles now appears proven enough to plan normalization work: the runtime should accept either `disable` or `disable_ttl` and convert both into a single typed paused-until field

## Polling and options findings

Firewalla Local is also the right current reference for options-flow structure.

Reusable pattern:

- top-level options menu
- focused submenu for general system settings
- bounded numeric polling controls
- translation-backed step descriptions and menu labels

Current recommendation:

- build refresh groups as runtime-defined poll categories rather than hard-coding exactly two coordinators forever
- keep initial categories conservative, for example:
  - analytics summary
  - endpoint inventory and membership
  - profile configuration and policy state
- give each refresh group its own default, minimum, and maximum interval constants
- expose those intervals through a menu-based options flow only after the group boundaries are stable enough to name clearly
- the menu structure should follow Firewalla Local closely: top-level init menu, one live profile selector, one focused per-profile edit form, and one integration-settings form
- profile inclusion should default to enabled for all discovered profiles and remain user-editable later through the options flow

## Decision-ready findings

These findings are strong enough to convert several planning topics from theory into action.

### Ready to treat as decisions

- endpoint identity must be based on `device_id`, not endpoint name
- duplicate endpoint names are a real runtime concern, but Home Assistant-owned `entity_id` disambiguation is sufficient for v1
- paired profile pause and resume services are the correct first service direction
- polling should be group-based and options-backed with bounded intervals
- `GET /profiles` should be treated as the summary discovery source for profile-backed surfaces, while per-profile list endpoints should be treated as detail sources for item-level switch creation
- paused-profile reads should be normalized from either `disable` or `disable_ttl` into one internal paused-until field
- user-facing profile entities should align to Control D terminology, including `Disable` for the profile-wide off surface
- filters with both enabled state and mode should be modeled as two entities: a switch for enablement and a select for mode
- high-cardinality profile surfaces should use a hierarchical naming pattern that includes type, category when available, and item name
- endpoint scope should begin with one opt-in status-oriented entity whose additional details are carried by attributes rather than many separate endpoint sensors
- profile-specific exposure policy is the right storage model for profile management state, endpoint-sensor toggles, service-category exposure, per-profile service auto-enable behavior, exposed custom-rule targets, and endpoint inactivity thresholds
- filters are a manageable fixed surface and should be auto-created instead of being managed item by item in entry options
- services are the true high-cardinality surface and should be exposed by per-profile category policy rather than by full item catalogs in entry options
- category-created service entities should default to disabled, with any default-enabled override treated as an advanced warned option
- all discovered profiles should be included by default when the config entry is created
- the options flow should allow any profile to be excluded later without removing the config entry
- `stats_endpoint` should be treated as resolvable instance metadata because `GET /analytics/endpoints` exposes its title mapping
- analytics client telemetry should be treated as a separate enrichment surface, not as the authoritative source for endpoint discovery
- profile analytics count endpoints are a viable summary telemetry source, but they return internal slugs and server-normalized time ranges that should be modeled deliberately
- profile analytics total endpoints are a viable companion summary source and strengthen the case for profile-level analytics sensors over diagnostics-only treatment
- profile analytics domain-ranking endpoints are a viable telemetry surface, but their high-cardinality output argues for capped attributes or diagnostics rather than standalone entities
- protocol-scoped aggregate analytics may exist as dashboard helper calculations and should remain out of the initial entity model until their scope and UI meaning are proven
- source-country analytics are now proven as a visible dashboard surface, but their scope and default filters still need to be understood before they belong in the initial entity model
- `triggerValue` supports multiple ranked breakdown surfaces, including filters and services, and those surfaces can appear both with and without `profileId`
- endpoint-scoped analytics are now proven strongly enough to support derivation of at least `Encrypted DNS` and `Home Country Traffic` directly from count ratios
- `Benign Blocks` is now likely derivable from blocked filter-category composition rather than requiring a separate dedicated summary endpoint

### Not yet ready to treat as closed decisions

- how to generalize the normalizer beyond the currently observed `profile` and `profile2` shape for possible organization cases
- how parent-child endpoint visibility should influence discovery and presentation when Firewalla child clients are not independently listed until explicitly assigned
- how the analytics `/v2/client` item identifiers correlate to `/devices` identifiers and whether analytics host selection is derived directly from `stats_endpoint`
- how `action` values map to dashboard views such as blocked, bypassed, and redirected for `v2/statistic/count/triggerValue`
- whether the internal analytics `value` slugs have a stable published mapping to the dashboard labels or need repository-owned translation logic
- how `srcCountry[]` affects totals and whether the dashboard always scopes statistics by one or more country filters
- whether `v2/statistic/count/question` uses the same action semantics as the filter breakdown endpoint and whether other parameters such as country filters are applied for the domains panel
- what scope `v2/statistic/count` uses when `profileId` is omitted and `protocol[]` filters are present, and whether that count feeds a visible dashboard tile, a percentage calculation, or an internal helper path
- how `v2/statistic/count/srcCountry` relates to the earlier protocol-filtered aggregate request and whether protocol filters are part of the default sources-panel contract or a surrounding dashboard filter state
- what the scope rules are for `triggerValue` when `profileId` is omitted and whether those broader blocked-tab panels are instance-scoped, account-scoped, or controlled by another hidden selector
- what exact count endpoint backs the blocked card total, since visible top-N filter and service rows undercount the displayed blocked-card value for the endpoint sample
- whether the `Benign Blocks` denominator uses all blocked filter categories or another filtered subset beyond the currently visible ranked rows
- which exact profile-backed controls should be summary-driven versus detail-driven in the first entity slice
- whether billing product metadata should remain diagnostics-only or also surface on the instance system device
- whether filter and service pause semantics can share the same target-resolution family as profile pause and resume
- what immutable typed identity format is best for persisted grouped-rule selections

## Next proof-of-concept actions

1. Capture one authenticated sample where a profile is actively paused so `GET /profiles` can be checked for the populated `disable` representation.
2. Confirm whether organization scenarios expose `profile3` or another attachment-field variation on `GET /devices`.
3. Decide whether parent-child endpoint relationships should surface only as attributes in v1 or also influence later display organization.
4. Formalize the typed persisted identity contract for selected rules and grouped rules.
5. Verify how grouped-rule display labels should combine folder semantics, folder names, and rule targets while keeping entity names concise.
6. Correlate one `v2/client` analytics item to a known `GET /devices` endpoint so the repository can decide whether analytics client telemetry is attachable to endpoint entities or should remain diagnostics-only.
7. Capture matching `v2/statistic/count/triggerValue` samples for blocked, bypassed, and redirected views so the repository can lock the `action` mapping and decide whether these counts become sensors, attributes, or diagnostics only.
8. Capture the dashboard requests for the `Total`, `Bypassed`, and `Redirected` cards so the repository can determine whether `v2/statistic/count` and related endpoints need additional parameters such as `srcCountry[]` or action filters to match the visible summary cards exactly.
9. Capture the dashboard requests for the domains panel in blocked, bypassed, and redirected views so the repository can decide whether `v2/statistic/count/question` belongs in diagnostics, capped sensor attributes, or a later on-demand surface.
10. Capture companion requests around `v2/statistic/count/srcCountry` and the earlier protocol-filtered `v2/statistic/count` call so the repository can determine whether protocol filters are part of the visible sources-panel contract and whether the surface is instance-scoped or profile-scoped.
11. Capture matching blocked-tab samples for `trigger=filter` and `trigger=service` both with and without `profileId` so the repository can lock the scope rules for ranked analytics breakdowns.
12. Capture the direct blocked-card total query and one endpoint or profile sample where phishing is non-zero so the repository can confirm the exact `Benign Blocks` denominator and the full security-category mapping.