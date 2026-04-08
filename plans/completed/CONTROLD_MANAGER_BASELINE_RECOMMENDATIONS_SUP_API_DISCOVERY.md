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
- the account payload also includes `last_active`, `stats_endpoint`, `sso`, and `safe_countries`
- `GET /profiles` lists all profiles associated with the account
- profile-modification calls use the profile primary key, documented as `PK`
- Control D response conventions state that successful responses return `success: true` and place returned objects under `body.<controller_name>`
- every unique upstream object uses a primary-key field named `PK`
- public docs describe a profile as a reusable policy container enforced on one or more endpoints
- supplied profile payloads show that each list row includes profile summary counts for filters, custom filters, IP filters, rules, services, groups, options, and `da` status fields
- supplied profile payloads also show `opt.data` entries with concrete option `PK` and `value` pairs in the list response
- `GET /billing/products` returns product metadata including `name`, `type`, `proxy_access`, `PK`, and `expiry`
- `GET /analytics/endpoints` returns analytics region mappings including `PK`, `title`, and `country_code`

Planning impact:

- the config-entry unique ID should anchor on `GET /users` `body.id`, with `body.PK` retained as a secondary join key because profile and device payloads reference the short account PK through their `user` field
- the profile identifier used for Home Assistant profile devices should come from the API `PK`
- the API client should normalize the Control D response envelope early so manager and entity code does not depend on controller-specific wrapper names
- one authenticated account can expose multiple profiles, which supports the accepted instance-centric config-entry model
- `GET /profiles` should be treated as the summary discovery source for profile-backed surfaces
- user-selectable switch creation for services, filters, and similar per-item controls should assume a second profile-scoped detail fetch rather than assuming the list response alone contains full item state
- `stats_endpoint` can be resolved into a user-facing analytics region title through a published API call rather than left as a raw key
- billing product metadata should be treated as available instance metadata until the repository decides whether it remains diagnostics-only or becomes user-facing

### Endpoint or device access

- public product docs use the term `Endpoint`
- API reference uses `/devices` and `device_id` for the same concept
- `GET /devices` lists all endpoints associated with an account or organization
- the docs mention `/devices/users` and `/devices/routers` as type-specific list variants
- the docs mention a transition-period `last_activity=1` query parameter for fields that are being removed from the default response
- `PUT /devices/{device_id}` modifies an endpoint
- device modification supports `profile_id` for the primary enforced profile
- device modification supports `profile_id2` for a second enforced profile, and the public docs state up to two profiles for personal use and up to three for organization contexts with a global profile
- live device payloads include both `PK` and `device_id`, and in the inspected account they matched for every endpoint
- live device payloads expose a single nested `profile` object with `PK`, `updated`, and `name`
- the supplied published payload also shows `profile2` on a multi-profile endpoint and `parent_device` on a child endpoint
- a supplied analytics payload from `https://america.analytics.controld.com/v2/client` returns `{"success": true, "body": {"items": {...}}}` where `body.items` is an object map keyed by analytics item identifiers
- each analytics item exposes `lastActivityTime` and a nested `clients` map; observed child client records may include `alias`, `host`, `mac`, `ip`, `os`, and `vendor`

Planning impact:

- internal integration naming should continue to use `endpoint` while the API client maps that concept to Control D `device` endpoints
- endpoint entity unique IDs should anchor on `device_id`, with `PK` retained as an alias for diagnostics and defensive comparisons
- roaming-endpoint reconciliation must be based on refreshed endpoint-to-profile assignments from the device list
- the currently documented `GET /devices` contract still reads as an account- or organization-scoped inventory endpoint rather than as a documented profile-scoped list endpoint
- multi-profile membership can be derived from published device payloads for the currently observed two-profile case by normalizing `profile`, `profile2`, and future sibling fields when present
- the owning Home Assistant profile device for a multi-profile endpoint should come from the first attached upstream profile field exposed by the published payload
- analytics-side client telemetry should be treated as a separate enrichment surface rather than as the authoritative endpoint inventory until its identifiers are correlated to `GET /devices`
- the presence of nested analytics clients reinforces that Firewalla-style child clients may be observable in telemetry before or without appearing as standalone endpoint inventory records

### Analytics host behavior

- the supplied analytics client sample uses a region-specific host: `https://america.analytics.controld.com/v2/client`
- a supplied analytics count sample also uses the regional analytics host at `https://america.analytics.controld.com/v2/statistic/count/triggerValue`
- a supplied analytics total sample also uses the regional analytics host at `https://america.analytics.controld.com/v2/statistic/count`
- a supplied analytics domain-ranking sample also uses the regional analytics host at `https://america.analytics.controld.com/v2/statistic/count/question`
- a supplied protocol-scoped aggregate sample also uses the regional analytics host at `https://america.analytics.controld.com/v2/statistic/count`
- a supplied source-country ranking sample also uses the regional analytics host at `https://america.analytics.controld.com/v2/statistic/count/srcCountry`
- the supplied count sample includes `profileId`, `trigger=filter`, `action=0`, `sortOrder=desc`, and requested `startTime` and `endTime` query parameters
- later `triggerValue` samples also show the same endpoint family used without `profileId`, including one `trigger=filter` sample and one `trigger=service` sample
- the supplied total sample includes `profileId`, requested `startTime` and `endTime`, and `srcCountry[]=US`
- the supplied domain-ranking sample includes `profileId`, `action[]=0`, `limit=500`, `sortOrder=desc`, and requested `startTime` and `endTime`
- the supplied protocol-scoped aggregate sample includes requested `startTime` and `endTime` plus repeated `protocol[]` filters for `doh`, `doq`, `dot`, and `doh3`, and omits `profileId`
- the supplied source-country ranking sample includes `sortOrder=desc`, requested `startTime` and `endTime`, and omits `profileId`
- the response body includes server-returned `startTime`, `endTime`, and a `counts` list of `{value, count}` rows
- the total sample response body includes server-returned `startTime`, `endTime`, and one aggregate `count`
- the protocol-scoped aggregate sample also returns one aggregate `count`
- the source-country ranking sample returns a `counts` list of `{value, count}` rows
- the observed `value` fields are internal slugs such as `ads`, `ads_small`, `ads_medium`, `ai_malware`, and `cryptominers`
- later observed filter values also include `typo`, which aligns with the dashboard label `Phishing`
- an observed service-ranking sample returns `truthsocial`, which aligns with the dashboard label `Truth Social`
- the observed domain-ranking `value` fields are raw queried domains rather than internal slugs

Planning impact:

- analytics calls should not be hardcoded to one hostname until the repository verifies how the correct analytics host is selected
- `stats_endpoint` from `GET /users` is now a strong candidate for analytics host or region selection input, but that mapping is not yet proven
- profile-scoped analytics summary reads are now proven, which makes analytics sensors a stronger Phase 4 candidate for profile devices or instance summaries
- ranked analytics breakdown reads are not uniformly profile-scoped, so the integration must distinguish profile-device analytics from broader blocked-tab analytics surfaces
- the analytics count endpoint appears to normalize the requested time window, so the runtime should not assume the echoed period will exactly match the submitted query bounds
- raw analytics values should not be shown directly as user-facing labels unless the repository proves that the slugs are stable and readable enough or obtains a reliable mapping source
- the aggregate `count` endpoint appears to pair with dashboard-style total cards and is a stronger fit for a dedicated summary sensor than the more granular trigger-value breakdown rows
- `srcCountry[]` is now part of the observed analytics request contract and may need to be treated as a required dashboard-state input rather than an optional filter
- the domain-ranking endpoint is high-cardinality telemetry and is a poor fit for standalone entities; it is better suited to diagnostics, capped attributes, or a later on-demand surface
- aggregate analytics calls are not all profile-scoped; some may be protocol-scoped helper calculations, so the integration should distinguish profile-visible summary sensors from broader analytics helper queries
- aggregate analytics calls are not all profile-scoped; some feed broader analytics views such as source-country rankings, so the integration should distinguish profile-visible summary sensors from broader dashboard analytics surfaces

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
- the supplied published payload exposes `profile2` on a real multi-profile endpoint

Planning impact:

- endpoint attachment and state derivation must not assume one enforced profile is authoritative for runtime behavior just because the write API names a primary and secondary profile field
- entity purpose and attachment rules must stay unambiguous even when the runtime uses the first attached upstream profile as the Home Assistant ownership rule

Open interpretation risk:

- the docs clearly define cross-category precedence, but they do not fully specify how conflicts are resolved within the same rule class when multiple enforced profiles both match
- until a live multi-profile sample is available, the integration should avoid presenting synthesized per-endpoint policy state that implies more certainty than the upstream read model provides

## Unverified or unresolved items

### Instance identity anchor

Live inspection exposed two candidate account identifiers on `GET /users`: `id` and `PK`.

`id` is UUID-shaped and separate from user-facing identity fields. `PK` is still important because profile and device payloads reference it through their `user` field.

Required next step:

- implement the config-entry identity contract as `users.id` primary plus `users.PK` secondary unless a later authenticated write or reauth flow proves that assumption wrong

### Disable semantics

- `PUT /profiles/{profile_id}` supports `disable_ttl`
- the reference describes `disable_ttl` as disabling a profile until the specified Unix timestamp
- `disable_ttl = 0` removes a previous deactivation
- live `GET /profiles` payloads expose a top-level `disable` field rather than `disable_ttl`
- unpaused profiles in the inspected account exposed `disable: null`
- a paused profile in the supplied sample exposed `disable_ttl` directly in the list payload

Planning impact:

- `controld_manager.disable_profile` can target the profile resource directly rather than treating profile disable as an unresolved endpoint-side workaround
- the first implementation should treat disable as a profile disable-until write, with service duration translated into an absolute Unix timestamp
- enable semantics can be modeled by writing `disable_ttl = 0`
- the runtime should normalize both `disable` and `disable_ttl` into one internal paused-until representation

Required next step:

- verify whether paused-profile reads always use `disable_ttl` or whether additional variants appear in other account states
- confirm whether disabling one profile on a multi-profile endpoint produces any additional endpoint-side status changes worth surfacing

### Entity inventory boundaries

The public docs confirm profiles, endpoints, services, filters, and analytics as product concepts, but they do not determine which subset makes the best first Home Assistant entity surface.

Required next step:

- lock the first entity slice using the now-confirmed split between summary discovery from `GET /profiles` and detailed item state from per-profile list endpoints such as services, filters, and rules
- decide whether analytics-client child telemetry attaches to endpoint entities, diagnostics, or both once `/v2/client` identifiers are correlated to `GET /devices`
- decide whether profile analytics count results from `/v2/statistic/count/triggerValue` belong on profile devices as sensors, on existing analytics entities as attributes, or in diagnostics only

### Device-to-profile read contract

The currently observed `GET /devices` payload shape does not return `profile_id` or `profile_id2` as raw scalar fields. Instead, endpoints expose attached profiles through nested objects such as `profile` and `profile2`.

Required next step:

- treat attached profile sibling fields such as `profile` and `profile2` as the current published read-side source of enforced-profile membership
- treat `profile` as the owning Home Assistant attachment source and keep additional sibling fields such as `profile2` and possible `profile3` values as supplemental membership metadata

### Analytics client correlation

- the supplied `/v2/client` payload proves that analytics exposes parent items with nested child clients and per-client last-activity metadata
- it does not yet prove whether the top-level analytics item keys or nested client keys match `device_id`, endpoint `PK`, or another identifier family used elsewhere in the API

Required next step:

- capture one correlation between a known `GET /devices` endpoint and a `/v2/client` analytics item before using this payload for entity attachment instead of diagnostics-only enrichment

### Analytics count semantics

- the supplied `v2/statistic/count/triggerValue` payload proves that analytics can return profile-scoped aggregate counts for `trigger=filter`
- later `v2/statistic/count/triggerValue` payloads prove that the same endpoint family can return broader blocked-tab breakdowns without `profileId`
- the matching dashboard screenshot strongly suggests that `action=0` corresponds to the blocked tab for this endpoint
- the payload returns internal value slugs instead of friendly dashboard labels
- the payload echoes normalized `startTime` and `endTime` values that differ from the raw query inputs
- `triggerValue` is now observed with at least two trigger classes: `filter` and `service`
- `typo -> Phishing` and `truthsocial -> Truth Social` strengthen the case that a repository-owned label-mapping layer may be required for user-facing analytics breakdowns
- the supplied `v2/statistic/count` payload proves that analytics also exposes a profile-scoped aggregate total counter
- the returned total `78033` aligns with the dashboard `78K` total card for the same profile and time range
- the supplied `v2/statistic/count/question` payload proves that analytics also exposes ranked domain counts for the statistics panel
- the returned top domain rows align with the supplied dashboard domains list
- the supplied protocol-filtered `v2/statistic/count` payload proves that the same aggregate endpoint is also used without `profileId` and with repeated `protocol[]` filters, returning a much larger total `549007`
- the supplied `v2/statistic/count/srcCountry` payload proves that analytics also exposes ranked source-country counts and that `US -> 549007` matches the supplied dashboard sources panel
- the supplied endpoint-scoped `v2/statistic/count` and `v2/statistic/count/srcCountry` payloads prove that endpoint analytics can be queried with `endpointId[]` and that, for the sampled endpoint, `total = US source-country total = encrypted-protocol total = 82268`
- the supplied endpoint-scoped `v2/statistic/count/triggerValue` payloads prove that visible blocked filter rows plus visible service rows sum to `9696`, which is slightly below the blocked-card total implied by the screenshot percentages
- an endpoint-scoped `v2/statistic/count` query with `trigger=filter&triggerValue[]=malware` returned `0`, despite the ranked breakdown showing `ai_malware = 20`
- a supplied product definition states that `Benign Blocks` is the share of blocks attributable to non-security filters, explicitly excluding Malware and Phishing
- using that definition on the endpoint sample, the visible benign-filter share is `9673 / 9693 = 99.79%`, which plausibly explains the displayed `Benign Blocks 100%` after rounding

Required next step:

- capture additional samples for other `action` values such as bypassed and redirected so the repository can lock the action mapping and decide how much label translation must be repository-owned
- determine the scope rules for `triggerValue` with and without `profileId` before treating any ranked breakdown as a profile-device sensor by default
- determine whether `srcCountry[]` is required to match the dashboard total-card semantics or whether it reflects a separate UI filter state that the integration should not model by default
- determine whether the domains panel uses the same action mapping as the filter breakdown endpoint and whether the integration should expose only a capped top-N view if this surface is user-facing
- determine how the protocol-filtered aggregate request relates to `count/srcCountry`, including whether protocol filters are part of the default sources-panel query or a separate dashboard filter state
- determine the exact query that yields the blocked-card total and the `Benign Blocks` percentage, because visible top-N rows are not sufficient to reconstruct those values exactly
- determine whether `Benign Blocks` uses all blocked filter categories or only the visible ranked set when phishing or other security filters are present beyond the current sample
- treat ranked analytics values and direct `triggerValue[]` query inputs as separate contracts until slugs such as `ai_malware` versus `malware` are proven equivalent or mapped officially

## Planning consequences

- keep the instance-centric config-entry model
- keep profile devices and endpoint entities as the accepted Home Assistant hierarchy
- treat `users.id`, `profile PK`, and `device_id` as the current best primary upstream identifiers
- retain `users.PK` and endpoint `PK` as secondary correlation fields
- treat `disable_profile` and `enable_profile` as viable for implementation once service input and post-write refresh behavior are locked
- normalize all attached profile sibling fields during refresh while using the first attached profile as the owning Home Assistant device attachment