# Control D Manager user guide

## Overview

Control D Manager is a Home Assistant custom integration for managing one Control D
account per config entry. It gives you a small account-level surface plus
profile-scoped controls for filters, services, custom rules, and endpoint status
entities.

This guide reflects the current implemented behavior in this repository.

## What the integration does

- connects to the Control D cloud API with an API token
- creates one Home Assistant config entry per authenticated Control D instance
- discovers account profiles and endpoint inventory
- lets you choose which profiles Home Assistant should manage
- exposes profile controls as Home Assistant entities
- provides account-level summary sensors and a manual sync button

## Initial setup

1. Open Home Assistant.
2. Go to Settings > Devices & services.
3. Add the Control D Manager integration.
4. Enter a valid Control D API token.

If authentication succeeds, Home Assistant creates one config entry for that
Control D instance.

## Options flow

After setup, open the integration options. The main menu has two paths:

- Configure a profile
- Integration settings

### Configure a profile

This flow starts with a live profile selector and then opens one profile policy
form for the selected profile.

Each profile can be configured with these controls:

- Enable management in Home Assistant
	Turn this off to exclude the profile from Home Assistant. Profile devices and
	entities for that profile are removed from Home Assistant.
- Expose 3rd-party filters
	Creates disabled-by-default entities for the available community or external
	filter lists on that profile. Even when this stays off, those filters can
	still be targeted through the shared filter service.
- Expose advanced profile options
	Turns on the larger profile option set for that profile. These extra controls
	are added in Home Assistant but stay off by default until you enable the ones
	you want.
- Allowed service categories
	Selects which Control D service categories are created in Home Assistant.
	New entities from these categories are created disabled by default because
	some categories can create a large number of entities.
- Expose custom rules
	Lets you expose selected rule folders or individual custom rules as Home
	Assistant controls.
- Expose endpoint sensors
	Creates endpoint activity entities for devices that belong to that profile.
- Endpoint inactivity threshold (minutes)
	Controls how long an endpoint can remain inactive before its endpoint status
	entity reports inactive.

The endpoint controls are intentionally kept at the bottom of the profile form
so the service-category and custom-rule exposure decisions stay grouped
together.


### Integration settings

This form controls refresh cadence only.

- Configuration sync interval (minutes)
	Controls how often structural account data is refreshed.
- Profile analytics interval (minutes)
	Reserved for higher-level analytics refresh cadence.
- Endpoint analytics interval (minutes)
	Reserved for endpoint telemetry refresh cadence.

## Devices and entities

### Account device

Each config entry creates one Home Assistant device named Account. Account-level
entities are attached to that device.

Current account entities:

- Status
- Profile count
- Endpoint count
- Sync now

### Profile devices

Each managed Control D profile becomes its own Home Assistant device under the
account device.

Current profile surfaces can include:

- a disable switch for the profile
- filter switches
- filter mode selectors where the upstream filter supports multiple levels
- profile option switches and selectors
- service mode selectors for allowed service categories
- custom rule switches and rule folder selectors
- endpoint status entities for endpoints owned by that profile when enabled

## Account entities

### Status

The Status entity is an enum sensor that reports the health of the integration's
refresh path for that Control D account.

Current states:

- Healthy
	The latest refresh succeeded.
- Degraded
	One refresh failed after at least one earlier successful refresh.
- Problem
	Repeated refresh failures are occurring, or the integration has not yet
	established a successful refresh baseline.

The Status sensor is about integration health, not a full upstream Control D
service-health contract.

Current Status attributes may include:

- last refresh attempt
- last successful refresh
- refresh in progress
- last refresh trigger
- consecutive failed refreshes
- last refresh error, when a failure is active
- stats endpoint, when exposed by the Control D account payload
- account status, when exposed by the Control D account payload

### Profile count

Profile count shows how many Control D profiles are currently discovered for the
account.

### Endpoint count

Endpoint count shows the current protected endpoint total.

This total is intentionally broader than the number of standalone endpoint
entities because it includes:

- explicitly discovered endpoints from the Control D devices inventory
- nested router client counts when the same inventory payload exposes them

Current Endpoint count attributes:

- discovered endpoint count
- router client count

### Sync now

Sync now runs an immediate refresh of the account inventory and profile detail
data currently used by the integration.

Use this when you have made recent changes in Control D and do not want to wait
for the next scheduled refresh.

## Profile controls

Different Control D features appear in Home Assistant in different ways. This
is intentional so each type of control stays simple to use.

### Disable switch

Each managed profile exposes a Disable switch. Turning it on disables the
profile for the configured duration. Turning it off enables the profile again.

### Filter switches and mode selectors

Filters are exposed as switches. Filters with multiple upstream levels also get
a selector entity for the active mode. Filter mode selectors follow the same
default entity-registry visibility as their companion filter switch.

In practice:

- simple filters appear as on or off switches
- filters with levels appear as a switch plus a mode selector
- 3rd-party filters stay hidden by default unless you enable Expose 3rd-party
	filters for that profile

### Service mode selectors

Service mode selectors are only created for the service categories you allow in
the profile options.

Current options are `Off`, `Blocked`, `Bypassed`, and `Redirected`.

Services use selectors instead of switches because they usually represent an
action choice, not just on or off.

### Profile options

Profile options can appear as either switches or selectors.

- options that are naturally on or off appear as switches
- options that let you choose between several behaviors appear as selectors
- a small core set is created automatically for managed profiles
- extra profile options only appear when you turn on Expose advanced profile
	options for that profile

### Custom rules and rule folders

Custom rules are only created for the rule folders or individual rules you
choose in the profile options.

- a rule folder appears as a selector because you choose a folder-wide action
- an individual rule appears as a switch because you are simply turning that
	rule on or off
- you can expose both a folder and individual rules inside that folder when you
	want both kinds of control

### Endpoint status entities

When enabled for a profile, endpoint status entities are created for that
profile's endpoints. These entities are compact activity surfaces derived from
last activity time.

## Services

The integration currently registers these Home Assistant services:

- `controld_manager.disable_profile`
- `controld_manager.enable_profile`
- `controld_manager.set_filter_state`
- `controld_manager.set_rule_state`
- `controld_manager.set_service_state`
- `controld_manager.get_catalog`

### Enable and disable profile services

`controld_manager.disable_profile` and `controld_manager.enable_profile` share
the same targeting rules.

- both services require you to select at least one profile
- use `profile_id` to select one or more profile devices directly
- use `profile_name` to select one or more managed profile names
- if both `profile_id` and `profile_name` are provided, `profile_id` wins
- if more than one Control D integration is loaded, you can add
	`config_entry_id` or `config_entry_name` to disambiguate the owning entry
- if both `config_entry_id` and `config_entry_name` are provided,
	`config_entry_id` wins

These services do not accept generic entity targets, and the Account device is
not a valid profile target.

Manual examples:

- disable two profiles by name for one hour:
	`profile_name: ["Primary", "Kids"]`
	`minutes: 60`
- enable one profile by device-based profile selection:
	`profile_id: ["7b6d4e8a2c0141e8b6d0f9a3c2e4d1f0"]`

### Filter state service

`controld_manager.set_filter_state` now uses the same profile-targeting rules as
the enable and disable profile services.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- select filters with `filter_id` or `filter_name`
- `filter_id` wins if both filter selectors are provided
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

This service does not accept generic entity targets, and it continues to work
for 3rd-party filters even when their entities are not exposed in Home
Assistant.

Manual examples:

- disable two filters by raw IDs for two profiles:
	`profile_name: ["Primary", "Kids"]`
	`filter_id: ["ads", "x-community"]`
	`enabled: false`
- enable one filter by user-facing name:
	`profile_id: ["7b6d4e8a2c0141e8b6d0f9a3c2e4d1f0"]`
	`filter_name: ["Ads & Trackers"]`
	`enabled: true`

### Rule state service

`controld_manager.set_rule_state` updates one or more selected custom rules in
the selected profiles.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- select rules with `rule_identity`
- `rule_identity` accepts full stable identities such as `root|example.com` or
	`group:1|example2.com`
- `rule_identity` also accepts a bare hostname such as `example.com` when that
	hostname is unique within the targeted profile scope
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

Supported mutation fields:

- `enabled` toggles the selected rules on or off
- `mode` changes the rule action to `block`, `bypass`, or `redirect`
- `comment` attempts to replace the upstream rule comment
- `cancel_expiration` clears the current expiration
- `expiration_duration` sets a relative expiration
- `expire_at` sets an absolute expiration in the Home Assistant local timezone

Precedence rules:

- `cancel_expiration` overrides both `expiration_duration` and `expire_at`
- `expire_at` overrides `expiration_duration` when both are provided

Current backend limitation:

- rule comment updates are not persisting reliably in Control D today
- the browser UI shows the same behavior: a comment can appear to update until
	the page refreshes, then the previous value returns
- the Home Assistant service exposes the field because it matches the observed
	write contract, but comment changes should be treated as backend-limited for
	now

Current entity behavior for expired rules:

- a rule with an expiration in the past is exposed as `off`
- rule entities expose `expired: true` and `expires_at` attributes when an
	expiration exists
- rules without an expiration do not include those attributes

Manual examples:

- disable one rule by full identity:
	`profile_name: ["Primary"]`
	`rule_identity: ["group:1|example2.com"]`
	`enabled: false`
- expire one rule in 30 minutes:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
	`expiration_duration: "00:30:00"`
- cancel an existing expiration:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
	`cancel_expiration: true`

### Service mode service

`controld_manager.set_service_state` updates one or more Control D services in
the selected profiles.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- select services with `service_id` or `service_name`
- `service_id` wins if both service selectors are provided
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

This service does not require service entities to be exposed. It can resolve
live service data even when the matching category is not currently enabled for
entities.

Manual examples:

- block one service by raw ID:
	`profile_name: ["Primary"]`
	`service_id: ["amazonmusic"]`
	`mode: "Blocked"`
- redirect one service by user-facing name:
	`profile_name: ["Primary"]`
	`service_name: ["Amazon Music"]`
	`mode: "Redirected"`

### Catalog service

`controld_manager.get_catalog` is a read-only response service that returns a
copyable catalog for one of these Control D data families:

- `filters`
- `services`
- `rules`
- `profile_options`

Targeting rules:

- `catalog_type` is required
- `profile_id` and `profile_name` are optional
- if both profile selectors are provided, `profile_id` wins
- leave both profile selectors empty to return all managed profiles in the
	selected config entry scope
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

The service response includes:

- `profiles` for the selected scope
- typed `items` for the requested catalog family
- a plain-text `text` block that is easy to copy into service calls or notes

Manual example:

- return the available service catalog for one managed profile:
	`catalog_type: services`
	`profile_name: ["Primary"]`

## Runtime behavior

The integration keeps normalized runtime data in memory inside the config
entry's runtime state.

That runtime data is refreshed on poll and reused by entities, managers, and
service handlers while Home Assistant is running. It is not intended to be
persistent state across Home Assistant restarts.

## Current limitations

- endpoint discovery still treats the Control D devices inventory as the
	authoritative source for endpoint entities
- nested router clients contribute to the account endpoint total, but they are
	not created as standalone endpoint entities
- profile analytics and endpoint analytics refresh intervals are configured, but
	the integration still centers current runtime behavior on the configuration
	inventory refresh path

## Troubleshooting

- If Status reports Degraded or Problem, check the last refresh error attribute.
- If a profile should disappear from Home Assistant, verify that Enable
	management in Home Assistant is turned off for that profile.
- If expected service controls are missing, verify that the relevant service
	categories are enabled for that profile.
- If expected 3rd-party filter entities are missing, verify that Expose
	3rd-party filters is turned on for that profile.
- If expected custom rule controls are missing, verify that the specific rules
	or rule folders are exposed for that profile.
- If expected profile options are missing, verify that the profile is managed
	in Home Assistant and that Expose advanced profile options is turned on when
	you expect the larger option set.