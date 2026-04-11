# Control D Manager user guide

## Overview

Control D Manager is a Home Assistant custom integration for managing one Control D
account per config entry. It gives you a small account-level surface plus
profile-scoped controls for filters, services, custom rules, and endpoint status
entities.

## What the integration does

- connects to the Control D cloud API with an API token
- creates one Home Assistant config entry per authenticated Control D instance
- discovers account profiles and endpoint inventory
- lets you choose which profiles Home Assistant should manage
- exposes profile controls as Home Assistant entities
- provides account-level summary sensors and a manual sync button

## Installation

You can install Control D Manager through HACS or by copying the integration
into your Home Assistant configuration directory manually.

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=controld-manager-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open HACS -> Integrations -> Custom repositories.
3. Add `https://github.com/ccpk1/controld-manager-ha` as an Integration repository.
4. Search for `Control D Manager`, install it, and restart Home Assistant.

### Manual installation

1. Download this repository.
2. Copy `custom_components/controld_manager` into your Home Assistant
	`custom_components/` directory.
3. Restart Home Assistant.

### Before you add the integration

Before starting the config flow, sign in to your Control D account at
`controld.com` and create an API key with write access. The integration uses a
write-capable key because it supports profile enable or disable, filter
changes, service changes, option changes, and rule changes in addition to
read-only inventory and analytics.

## Initial setup

1. Open Home Assistant.
2. Go to Settings > Devices & services.
3. Add the Control D Manager integration.
4. Enter a valid write-capable Control D API token.

If authentication succeeds, Home Assistant creates one config entry for that
Control D instance.

## Credential updates and repair

If your Control D API token is rotated, revoked, or expires, the integration
raises a Home Assistant reauthentication request.

Use these entry actions when needed:

- Reconfigure
	Revalidates the existing config entry against the same Control D instance.
- Reauthenticate
	Repairs the stored API token in place after Home Assistant detects an auth
	failure during refresh.

Both paths verify that the submitted token still belongs to the same immutable
Control D instance before the entry is updated.

## Removal

If you want to stop using the integration, remove the Home Assistant config
entry first.

### Remove the config entry

1. Open Home Assistant.
2. Go to Settings > Devices & services.
3. Open the `Control D Manager` integration entry.
4. Choose Delete.

Removing the config entry unloads the runtime, removes the entities that belong
to that entry, and detaches the Home Assistant devices created for the account
and managed profiles.

### Remove the installed files

After removing the config entry, remove the integration files using the same
method you used to install it.

- HACS:
	Open HACS, locate `Control D Manager`, and uninstall the repository.
- Manual install:
	Delete `custom_components/controld_manager` from your Home Assistant
	configuration directory.

Restart Home Assistant after removing the files.

## Options flow

After setup, open the integration options. The main menu has two paths:

- Configure a profile
- Integration settings

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
This form controls the active refresh cadence.

- Configuration sync interval (minutes)
	Controls how often the integration refreshes the
	Control D inventory and configuration data. The allowed range is 5 to 60
	minutes.

The integration uses one polling path for inventory, profile detail, endpoint
activity, and analytics refresh. Separate polling controls are not exposed.

## Diagnostics and availability

Home Assistant diagnostics for a Control D config entry include redacted entry
data plus a runtime summary of refresh intervals, sync status, registry counts,
and per-profile policy scope.

When the refresh path fails repeatedly, the integration records one unavailable
transition and one recovery transition instead of logging the same outage on
every poll. The Account Status entity still reflects the live health of the
refresh path.

## Devices and entities

### Account device

Each config entry creates one Home Assistant device named Account. Account-level
entities are attached to that device.

Account surfaces:

- Status
- Profile count
- Endpoint count
- Total queries
- Blocked queries
- Blocked queries ratio
- Bypassed queries
- Redirected queries

Each managed profile device also exposes the same five analytics sensors for
that profile, using the same rolling last day reporting window as the Control D
statistics page.

- Sync now

### Profile devices

Each managed Control D profile becomes its own Home Assistant device under the
account device.

Profile surfaces can include:

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

States:

- Healthy
	The latest refresh succeeded.
- Degraded
	One refresh failed after at least one earlier successful refresh.
- Problem
	Repeated refresh failures are occurring, or the integration has not yet
	established a successful refresh baseline.

The Status sensor is about integration health, not a full upstream Control D
service-health contract.

Status attributes may include:

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

This sensor uses the unit `profiles` so Home Assistant can show that the value
is a current count of discovered profiles rather than an unlabeled raw number.

### Endpoint count

Endpoint count shows the current protected endpoint total.

This sensor uses the unit `endpoints` so Home Assistant can show that the value
is a current count of protected endpoints rather than an unlabeled raw number.

This total is intentionally broader than the number of standalone endpoint
entities because it includes:

- explicitly discovered endpoints from the Control D devices inventory
- nested router client counts when the same inventory payload exposes them

Endpoint count attributes:

- discovered endpoint count
- router client count

### Sync now

Sync now runs an immediate refresh of the account inventory and profile detail
data currently used by the integration.

Use this when you have made recent changes in Control D and do not want to wait
for the next scheduled refresh.

### Total queries

Total queries shows the current account-level query total for the rolling last
day window used by the Control D statistics page.

This total is the scoped aggregate formed from the blocked, bypassed, and
redirected action buckets for the same reporting window.

### Blocked queries

Blocked queries shows the current account-level blocked bucket for the same
reporting window.

### Bypassed queries

Bypassed queries shows the current account-level bypassed bucket for the same
reporting window.

### Redirected queries

Redirected queries shows the current account-level redirected bucket for the
same reporting window.

This count combines both analytics redirect action types currently documented by
Control D:

- redirected by IP
- redirected by Location

Analytics sensor notes:

- they request a rolling last-day account-level reporting window, then expose
	the UTC-normalized window returned by the Control D analytics API
- they use the unit `queries` so Home Assistant can show that these values are
	counts of DNS queries for the current reporting window
- the total is computed from the same scoped blocked, bypassed, and redirected
	buckets shown in the dashboard-style action model, rather than from the raw
	unsliced aggregate count endpoint alone
- the returned analytics start and end times are exposed as state attributes
- blocked query ratio is exposed as a percentage sensor for both the account
	and each managed profile
- these sensors are best-effort telemetry and do not affect the core inventory
	refresh path if the analytics endpoint is temporarily unavailable

## Dashboard compatibility

### Pi-hole card

The integration exposes several account and profile analytics sensors using
translation keys that the `custom:pi-hole` Lovelace card already understands.
This gives you a practical way to reuse that card for a Control D dashboard.

Compatible surfaces include:

- total queries
- blocked queries
- blocked queries ratio
- unique clients or endpoint count
- status
This is limited compatibility rather than a full Pi-hole emulation layer. The
card still includes Pi-hole-specific sections that expect Pi-hole services and
Pi-hole data models.

### Practical limitations

Some built-in Pi-hole card sections are not a direct fit for Control D.

- pause controls in the card trigger Pi-hole-specific service calls
- charts and footer content are designed around Pi-hole behavior and may not be
	useful in a Control D dashboard
- card actions may assume Pi-hole endpoints or service names that this
	integration does not provide

For that reason, it is usually better to hide those sections with
`exclude_sections` and let the Control D entities provide the controls.

### Example configuration

This example uses one card for account statistics and one card for a single
profile control surface.

```yaml
type: grid
cards:
	- type: custom:pi-hole
		device_id: ACCOUNT_DEVICE_ID  # Replace with your account device ID
		title: Control D - Account
		icon: mdi:dns-outline
		exclude_sections:
			- pause
			- chart
			- footer
			- switches

	- type: custom:pi-hole
		device_id: PROFILE_DEVICE_ID  # Replace with your profile device ID
		title: Control D - Profile 1
		icon: mdi:dns-outline
		exclude_sections:
			- actions
			- chart
			- footer
			- pause
		entity_order:
			- switch.profile_1_disable  # Replace with the disable switch for the selected profile
			- divider
```

What this configuration does:

- The account card is used as a read-only summary card for account-wide
	statistics.
- The profile card keeps the statistics layout from the Pi-hole card while
	leaving room for Control D switches and other profile entities.
- The excluded sections avoid Pi-hole-specific controls that would otherwise
	call unsupported actions.
- `entity_order` lets you keep the main profile disable switch near the top of
	the switch list.

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

Supported options are `Off`, `Blocked`, `Bypassed`, and `Redirected`.

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

The integration registers these Home Assistant services:

- `controld_manager.create_rule`
- `controld_manager.delete_rule`
- `controld_manager.disable_profile`
- `controld_manager.enable_profile`
- `controld_manager.set_client_alias`
- `controld_manager.clear_client_alias`
- `controld_manager.rename_endpoint`
- `controld_manager.set_endpoint_analytics_logging`
- `controld_manager.set_default_rule_state`
- `controld_manager.set_filter_state`
- `controld_manager.set_option_state`
- `controld_manager.set_rule_state`
- `controld_manager.set_service_state`
- `controld_manager.get_catalog`

### Client alias services

`controld_manager.set_client_alias` and `controld_manager.clear_client_alias`
target Control D clients that sit under a parent endpoint in analytics data.

- both services operate inside exactly one loaded Control D config entry
- if more than one config entry is loaded, use `config_entry_id` or
	`config_entry_name` to scope the request, with `config_entry_id` taking
	precedence
- supported selectors are `endpoint_mac`, `endpoint_name`,
	`endpoint_hostname`, and `endpoint_ip`
- selector precedence is MAC address, then endpoint name, then hostname, then
	IP address
- `parent_endpoint_name` is optional and is primarily useful for resolving
	duplicate hostname or IP matches behind routers, gateways, or VLAN endpoints
- MAC, hostname, and IP selectors can resolve analytics-only client rows even
	when that client does not currently exist as a standalone endpoint entity in
	Home Assistant
- these services intentionally target client-alias rows, not endpoint rename
	rows

Manual examples:

- set one client alias by MAC address:
	`endpoint_mac: ["50:eb:71:b6:78:3a"]`
	`alias: "Kids iPhone"`
- clear one client alias by current endpoint name:
	`endpoint_name: ["Chads-Phone"]`
- set one client alias by hostname and parent endpoint name:
	`endpoint_hostname: ["duplicate-host"]`
	`parent_endpoint_name: "Firewalla-VLAN60"`
	`alias: "Shared Host"`

### Endpoint rename service

`controld_manager.rename_endpoint` updates the endpoint label stored on the
Control D `/devices/{device_id}` surface.

- this service is endpoint-scoped, not client-alias-scoped
- select targets with `endpoint_name`
- if more than one loaded Control D config entry exists, use `config_entry_id`
	or `config_entry_name` to scope the request, with `config_entry_id` taking
	precedence
- if one current endpoint name matches more than one endpoint inside the same
	config entry, the service raises an ambiguity error instead of guessing
- `new_name` is required and must be a non-empty value
- endpoint entity unique IDs stay anchored to immutable Control D `device_id`
	values, so renames do not orphan entities

Manual examples:

- rename one endpoint by its current label:
	`endpoint_name: ["Chads-Phone"]`
	`new_name: "Kids iPhone"`
- rename one endpoint in a specific config entry when multiple instances are
	loaded:
	`config_entry_id: "a1b2c3d4e5f6g7h8i9j0"`
	`endpoint_name: ["Cabin Tablet"]`
	`new_name: "Guest Tablet"`

### Endpoint analytics logging service

`controld_manager.set_endpoint_analytics_logging` updates the endpoint analytics
logging level stored on the Control D `/devices/{device_id}` surface.

- this service is endpoint-scoped, not client-alias-scoped
- select targets with `endpoint_name`
- if more than one loaded Control D config entry exists, use `config_entry_id`
	or `config_entry_name` to scope the request, with `config_entry_id` taking
	precedence
- if one current endpoint name matches more than one endpoint inside the same
	config entry, the service raises an ambiguity error instead of guessing
- `mode` is required and currently supports the validated values `None`,
	`Some`, and `Full`
- those values map exactly to the proven Control D endpoint `stats` payload
	values `0`, `1`, and `2`

Manual examples:

- set one endpoint to the highest logging level:
	`endpoint_name: ["Chads-Phone"]`
	`mode: "Full"`
- reduce logging for one endpoint in a specific config entry:
	`config_entry_id: "a1b2c3d4e5f6g7h8i9j0"`
	`endpoint_name: ["Cabin Tablet"]`
	`mode: "Some"`

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

`controld_manager.set_filter_state` uses the same profile-targeting rules as
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

### Default rule state service

`controld_manager.set_default_rule_state` updates the default query behavior
for one or more selected profiles.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence
- `mode` is required and supports `Blocking`, `Bypassing`, and `Redirecting`

Supported behavior:

- `Redirecting` supports Control D location-family redirect behavior
- `redirect_target` is optional and may be used with `Redirecting`
- supported default-rule redirect targets are Control D location-style values:
	POP codes or names, `LOCAL` for auto routing, and `?` for random routing
- `redirect_target_type` is optional and supports `location`
- IP-style proxy redirects are not supported for default rules
- manual POP-target selections do not stay sticky upstream if you switch away
	from redirecting and then return to it

Manual examples:

- set one profile to redirect unmatched queries by default:
	`profile_name: ["Primary"]`
	`mode: "Redirecting"`
- set one profile to redirect unmatched queries through one POP:
	`profile_name: ["Primary"]`
	`mode: "Redirecting"`
	`redirect_target: "WFR"`
- set one profile to use Control D auto routing explicitly:
	`profile_name: ["Primary"]`
	`mode: "Redirecting"`
	`redirect_target: "LOCAL"`
- set one profile to use Control D random routing explicitly:
	`profile_name: ["Primary"]`
	`mode: "Redirecting"`
	`redirect_target: "?"`

### Option state service

`controld_manager.set_option_state` updates one or more Control D profile
options across the selected profiles.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- select options with `option_id` or `option_name`
- `option_id` wins if both option selectors are provided
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence
- use `enabled` for toggle-style options such as Safe Search
- for select-style options such as AI Malware Filter:
	`enabled: false` turns the option off
- for select-style options such as AI Malware Filter:
	`enabled: true` turns the option back on using the upstream default value
	when available, otherwise the first available level

- `b_resp` supports the values `0.0.0.0 / ::`,
	`NXDOMAIN`, and `REFUSED`
- `ecs_subnet` supports the values `No ECS` and `Auto`, and `enabled: false`
	turns it off
- for numeric TTL-style field options such as Block TTL:
	`value` sets the number of seconds and implies `enabled: true`
- for numeric TTL-style field options such as Block TTL:
	use `enabled: false` with no `value` to turn the option off
- use `value` when you want a specific select-style option value instead of the
	default
- for supported select-style options, `value` may be either the Home Assistant
	label or the raw upstream option value

Manual examples:

- turn AI Malware Filter off:
	`profile_name: ["Primary"]`
	`option_id: ["ai_malware"]`
	`enabled: false`
- turn AI Malware Filter back on using the default or first available level:
	`profile_name: ["Primary"]`
	`option_id: ["ai_malware"]`
	`enabled: true`
- set AI Malware Filter to a specific level:
	`profile_name: ["Primary"]`
	`option_id: ["ai_malware"]`
	`value: "Aggressive"`
- set Block Response to NXDOMAIN:
	`profile_name: ["Primary"]`
	`option_id: ["b_resp"]`
	`value: "NXDOMAIN"`
- set Block Response by raw upstream value:
	`profile_name: ["Primary"]`
	`option_id: ["b_resp"]`
	`value: "5"`
- `Custom` and `Branded` remain unsupported for Block Response until their
	full implementation path is intentionally added
- set EDNS Client Subnet to Auto:
	`profile_name: ["Primary"]`
	`option_id: ["ecs_subnet"]`
	`value: "Auto"`
- set EDNS Client Subnet by raw upstream value:
	`profile_name: ["Primary"]`
	`option_id: ["ecs_subnet"]`
	`value: "1"`
- turn EDNS Client Subnet off:
	`profile_name: ["Primary"]`
	`option_id: ["ecs_subnet"]`
	`enabled: false`
- `Custom` remains unsupported until its upstream mapping is captured
- set Block TTL to 20 seconds:
	`profile_name: ["Primary"]`
	`option_id: ["ttl_blck"]`
	`value: 20`
- turn Block TTL off:
	`profile_name: ["Primary"]`
	`option_id: ["ttl_blck"]`
	`enabled: false`

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
- when `mode: "redirect"` is used, `redirect_target` may be a Control D
	location code or name, `LOCAL`, `?`, or an IPv4 or IPv6 address
- `redirect_target_type` is optional; when omitted, the integration infers
	IPv4 or IPv6 from a valid IP address and treats other values as
	location-family redirects
- `comment` attempts to replace the upstream rule comment
- `cancel_expiration` clears the current expiration
- `expiration_duration` sets a relative expiration
- `expire_at` sets an absolute expiration in the Home Assistant local timezone

Precedence rules:

- `cancel_expiration` overrides both `expiration_duration` and `expire_at`
- `expire_at` overrides `expiration_duration` when both are provided

Backend limitation:

- rule comment updates do not persist reliably in Control D
- the browser UI shows the same behavior: a comment can appear to update until
	the page refreshes, then the previous value returns
- the Home Assistant service exposes the field because it matches the observed
	write contract, but comment changes should be treated as backend-limited

Expired rule behavior:

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
- redirect one rule through auto routing:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
	`mode: "redirect"`
	`redirect_target: "LOCAL"`
- redirect one rule through random routing:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
	`mode: "redirect"`
	`redirect_target: "?"`
- redirect one rule through an IPv4 proxy target:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
	`mode: "redirect"`
	`redirect_target: "1.1.1.1"`

### Create rule service

`controld_manager.create_rule` creates one or more custom rules in the selected
profiles.

- select profiles with `profile_id` or `profile_name`
- `profile_id` wins if both profile selectors are provided
- provide one or more hostnames with `hostname`
- optionally place the new rules inside one rule folder with
	`rule_group_id` or `rule_group_name`
- `rule_group_id` wins if both rule-group selectors are provided
- the selected rule folder must resolve unambiguously in every targeted
	profile
- `enabled`, `mode`, `comment`, `expiration_duration`, and `expire_at` reuse
	the same semantics as `set_rule_state`
- when `mode: "redirect"` is used, `redirect_target` and
	`redirect_target_type` reuse the same redirect semantics as
	`set_rule_state`
- if `enabled` is omitted, the new rules default to enabled
- if `mode` is omitted, the new rules default to `block`
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence
- duplicate hostnames inside the same create request are rejected before any
	upstream write is attempted
- create requests are rejected if a targeted profile already has the same
	hostname as an existing rule, even in a different folder

This service does not accept generic entity targets, and the Account device is
not a valid profile target.

Manual examples:

- create one top-level blocking rule:
	`profile_name: ["Primary"]`
	`hostname: ["example.org"]`
- create two bypass rules in one folder:
	`profile_name: ["Primary"]`
	`hostname: ["example.org", "example.net"]`
	`rule_group_name: "Allow folder"`
	`mode: "bypass"`
- create one redirect rule with an expiration:
	`profile_name: ["Primary"]`
	`hostname: ["example.org"]`
	`mode: "redirect"`
	`expiration_duration: "00:30:00"`
- create one redirect rule using random routing:
	`profile_name: ["Primary"]`
	`hostname: ["example.org"]`
	`mode: "redirect"`
	`redirect_target: "?"`

### Delete rule service

`controld_manager.delete_rule` deletes one or more existing custom rules from
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

This service does not accept generic entity targets, and the Account device is
not a valid profile target.

Manual examples:

- delete one top-level rule:
	`profile_name: ["Primary"]`
	`rule_identity: ["root|example.com"]`
- delete one grouped rule by bare hostname:
	`profile_name: ["Primary"]`
	`rule_identity: ["example2.com"]`

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
live service data even when the matching category is not enabled for entities.

Redirect target behavior:

- when `mode: "Redirected"` is used, `redirect_target` may be a Control D
	location code or name, `LOCAL`, `?`, or an IPv4 or IPv6 address
- `redirect_target_type` is optional; when omitted, the integration infers
	IPv4 or IPv6 from a valid IP address and treats other values as
	location-family redirects
- when `redirect_target` is omitted, the integration prefers the service's
	suggested `unlock_location` when one is available and otherwise falls back
	to explicit auto routing equivalent to `LOCAL`
- the Control D web app may instead prefill a concrete suggested location for
	some services based on the service catalog `unlock_location` metadata; when
	available, service select entities expose that suggestion as the
	`suggested_redirect_target` state attribute

Manual examples:

- block one service by raw ID:
	`profile_name: ["Primary"]`
	`service_id: ["amazonmusic"]`
	`mode: "Blocked"`
- redirect one service by user-facing name:
	`profile_name: ["Primary"]`
	`service_name: ["Amazon Music"]`
	`mode: "Redirected"`
- redirect one service using random routing:
	`profile_name: ["Primary"]`
	`service_name: ["Amazon Music"]`
	`mode: "Redirected"`
	`redirect_target: "?"`
- redirect one service through an IPv4 proxy target:
	`profile_name: ["Primary"]`
	`service_name: ["Amazon Music"]`
	`mode: "Redirected"`
	`redirect_target: "1.1.1.1"`

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

## Limitations

- endpoint discovery still treats the Control D devices inventory as the
	authoritative source for endpoint entities
- nested router clients contribute to the account endpoint total, but they are
	not created as standalone endpoint entities
- profile analytics and endpoint analytics refresh intervals are configured, but
	the integration centers runtime behavior on the configuration inventory
	refresh path

## Troubleshooting

- If Status reports Degraded or Problem, check the last refresh error attribute.
- If the Control D API key is rejected, ensure a Home Country is set in your
	Control D preferences on the website.
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