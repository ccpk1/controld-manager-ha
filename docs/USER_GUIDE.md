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
- Expose all active services
	Turns on exposure for the current explicit live service rows already present on
	the Control D profile.
	This cannot be combined with specific service category selections.
	This is the default for new entries and for migrated profiles that did not
	have stored manual categories.
- Service categories
	Select one or more categories to expose only those services.
	This cannot be combined with Expose all active services.
	New entities from category exposure are created disabled by default because
	some categories can create a large number of entities.
	If no categories are selected and Expose all active services is off, Home
	Assistant exposes no service entities for that profile.
- Expose all custom rules
	Turns on exposure for every current folder and custom rule on that profile.
	This cannot be combined with specific custom rule selections.
- Custom rules
	Lets you expose selected rule folders or individual custom rules as Home
	Assistant controls.
	This cannot be combined with Expose all custom rules.
- Expose endpoint sensors
	Creates endpoint activity entities for devices that belong to that profile.
- Endpoint inactivity threshold (minutes)
	Controls how long an endpoint can remain inactive before its endpoint status
	entity reports inactive.

The endpoint controls are intentionally kept at the bottom of the profile form
so the service-category and custom-rule exposure decisions stay grouped
together.

Home Assistant remembers entity-registry enable or disable choices after an
entity has been created. The integration handles the normal defaults for newly
created surfaces and removes entities when an exposure path is no longer
eligible, but it cannot safely override every manual registry change you may
have made earlier. After changing options-flow exposure settings, you may still
need to re-enable or disable some entities to match your preferred registry
state.

### Integration settings
This form controls the active refresh cadence.

- Configuration sync interval (minutes)
	Controls how often the integration refreshes the
	Control D inventory and configuration data. The allowed range is 5 to 60
	minutes.

The integration uses one polling path for inventory, profile detail, endpoint
activity, and analytics refresh. Separate polling controls are not exposed.

This form also carries the AI assistant (MCP) tool access setting described in
AI assistants and MCP tools.

## Diagnostics and availability

Home Assistant diagnostics for a Control D config entry include redacted entry
data plus a runtime summary of refresh intervals, sync status, registry counts,
and per-profile policy scope.

That policy scope includes the current service policy for each profile and
whether Expose all custom rules is active.

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
- Protected devices
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
- service mode selectors for either explicit live service rows or manually
	selected service categories
- custom rule switches and rule folder selectors for either explicit manual
	picks or the Expose all custom rules toggle
- endpoint status entities for endpoints owned by that profile when enabled

### Shared entity metadata

Every entity created by the integration exposes a shared metadata contract in
its state attributes.

Shared attributes:

- `integration`
	Always `controld_manager`.
- `profile_name`
	Uses `Account` for account-scoped entities, the owning profile name for
	profile entities, and the current owning profile name for endpoint entities.
- `purpose`
	The raw purpose key that explains what the entity controls or represents.
- `item_type`
	A stable machine-friendly type such as `status`, `summary_metric`,
	`analytics_metric`, `filter`, `service`, `rule`, `option`, or
	`profile_pause`.
- `taxonomy_path`
	An ordered list of Control D hierarchy labels above the leaf item. Non-control
	surfaces usually expose an empty list.
- `item_name`
	The leaf item label represented by the entity.

Examples:

- Account status:
	`profile_name=Account`, `item_type=status`, `taxonomy_path=[]`
- Profile service select:
	`profile_name=Primary`, `item_type=service`,
	`taxonomy_path=["Services", "Audio"]`, `item_name=Amazon Music`
- Rule switch:
	`item_type=rule`, `taxonomy_path=["Rules", "Domain"]` or the current rule
	folder name when the rule belongs to a folder

These attributes are intended to make automations, templates, and dashboard
filters more robust without relying on entity-name parsing.

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

### Protected devices

Protected devices shows everything DNS protection covers on this account: the
endpoints plus the clients seen behind them.

This is **not** the endpoint count. An endpoint is a protected row in Control D's
devices inventory — a router segment, a ctrld instance, or an individually
protected device. A client is something seen under an endpoint. Both are
protected, so both are counted here, and the two underlying figures are exposed
as attributes so you can tell them apart.

This sensor uses the unit `endpoints` so Home Assistant can show that the value
is a current count rather than an unlabeled raw number.

Protected devices attributes:

- endpoint count
- client count

The per-profile Protected devices sensors do **not** sum to the account figure.
An endpoint enforcing two profiles is counted under each of them, so the profile
rows deliberately total more. Quote the account value rather than adding the rows
up.

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
- unique clients or protected devices
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

Service mode selectors follow the service exposure controls for each profile.

- turning on Expose all active services exposes only the explicit live service
	rows already present on the Control D profile
- selecting manual service categories exposes only services from the categories
	you choose in the profile options
- leaving both the all-services toggle off and the category selector empty
	exposes no service entities for that profile

Expose all active services is the default because it follows the smaller set of
services you already chose upstream instead of forcing broad category exposure.

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

Custom rule entities can be created in either of these ways:

- choose specific rule folders or individual rules in the profile options
- turn on Expose all custom rules for the profile

- a rule folder appears as a selector because you choose a folder-wide action
- an individual rule appears as a switch because you are simply turning that
	rule on or off
- you can expose both a folder and individual rules inside that folder when you
	want both kinds of control, but you cannot combine those manual picks with the
	Expose all custom rules toggle

### Endpoint status entities

When enabled for a profile, endpoint status entities are created for that
profile's endpoints. These entities are compact activity surfaces derived from
last activity time.

## Services

The integration registers these Home Assistant services:

- `controld_manager.create_endpoint`
- `controld_manager.create_rule`
- `controld_manager.delete_client`
- `controld_manager.delete_endpoint`
- `controld_manager.delete_rule`
- `controld_manager.delete_service`
- `controld_manager.disable_profile`
- `controld_manager.enable_profile`
- `controld_manager.get_account_overview`
- `controld_manager.get_activity_log`
- `controld_manager.get_catalog` (its `catalog_type` accepts `filters`,
`services`, `rules`, `profile_options`, `default_rule`, and
`redirect_locations`; the last is account-wide and lists the redirect
destinations a redirect rule or service may target)
- `controld_manager.get_inventory`
- `controld_manager.set_client_alias`
- `controld_manager.clear_client_alias`
- `controld_manager.rename_endpoint`
- `controld_manager.set_endpoint_analytics_logging`
- `controld_manager.set_endpoint_description`
- `controld_manager.set_endpoint_profile`
- `controld_manager.set_default_rule_state`
- `controld_manager.set_filter_state`
- `controld_manager.set_option_state`
- `controld_manager.set_rule_state`
- `controld_manager.set_service_state`
- `controld_manager.test_domain`

The `get_*` and `test_domain` services are read-only response services. They do
not change anything and return their data as a service response, which is
intended for use from automations, scripts, and AI assistant tools rather than
from the Home Assistant user interface.

Every other service in that list changes Control D policy, so it requires an
**administrator**. A non-admin user calling one of them is rejected. Automations
and scripts are unaffected, because the check only applies when a user is
attached to the call.

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

### Endpoint profile service

`controld_manager.set_endpoint_profile` attaches the profile an endpoint enforces,
and optionally a second one. This is what moves a device between policies.

- select targets with `endpoint_id` (preferred; ids are unique) or
    `endpoint_name`
- `profile_id` sets the **primary** profile, and accepts a profile id or name
- `profile_id2` sets the **secondary** profile
- `clear_profile2: true` detaches the secondary, leaving only the primary
- the primary **cannot be cleared**: every endpoint always enforces exactly one
    profile, and Control D rejects an attempt to empty the primary. To make an
    endpoint permissive, assign a permissive profile instead
- when two profiles are attached the rule engine **merges** them before matching
    rather than applying them in order, so a custom rule in the secondary can
    override a filter in the primary. That is how a shared baseline plus a
    device-specific policy is built
- changing a profile changes what the endpoint blocks, so confirm the target

Manual examples:

- move one endpoint onto a different policy:
        `endpoint_id: ["461wtt4eyr"]`
        `profile_id: "962691chipwa5"`
- enforce a shared baseline as well, without changing the primary:
        `endpoint_id: ["461wtt4eyr"]`
        `profile_id2: "886818chik7jg"`
- detach the secondary again:
        `endpoint_id: ["461wtt4eyr"]`
        `clear_profile2: true`

### Endpoint description service

`controld_manager.set_endpoint_description` sets the free-text note an endpoint
carries, and an **empty string clears it**.

- select targets with `endpoint_id` (preferred) or `endpoint_name`
- the note changes no behaviour; it is for recording what a device is or why it
    is configured a certain way
- the current value is reported by `get_inventory` under `advanced.description`

### Create endpoint service

`controld_manager.create_endpoint` adds one endpoint, which is a DNS resolver that
enforces a profile.

- `endpoint_name` is required and must be **unique**; Control D rejects a
    duplicate
- `profile_id` is required, because an endpoint always enforces exactly one
    profile
- `description` and `icon` are optional, as is `mode` for the initial analytics
    logging level
- the new endpoint's id is assigned by Control D and is only known after the call
- a new endpoint reports **Pending** until it first sends queries, which is
    normal and clears on its own

### Delete endpoint service

`controld_manager.delete_endpoint` permanently removes one or more endpoints.

**This is destructive and cannot be undone.** Deleting an endpoint removes the
resolver itself and the records kept against it, so anything resolving through it
stops being filtered. Deleting a router endpoint is the widest case: it enforces a
profile for a whole network segment, so every device behind it loses that policy
at once.

- select targets with `endpoint_id` (preferred) or `endpoint_name`
- if you only want to stop filtering for a while, assign a permissive profile
    with `set_endpoint_profile` instead — the endpoint and its history stay intact
- requires an **administrator**

### Delete client service

`controld_manager.delete_client` permanently removes client rows, and by default
their stored query history with them.

Read this before using it, because the effect is usually not what it sounds like:

- a client row exists because Control D **observed** that client's traffic, so it
    is derived rather than configured. For an ordinary client the row **comes
    back** the next time the device is online, so the removal is not durable
- the only things about a client that outlive its traffic are its **alias** and a
    **policy assignment**, and this service changes neither
- where deletion does stick is a client that will never recur. A device using a
    **rotating private MAC** is the everyday case: each rotation arrives under a
    new address and creates its own row that can never be seen again
- it is therefore a **history-hygiene** tool, not a device-retirement tool, and
    on a network with rotating private MACs it is a recurring chore rather than a
    one-off fix

- select targets with `client_id` (preferred; it is the only selector guaranteed
    to match one client), or by MAC, hostname, name, or IP
- a MAC or a hostname such as `watch` can match a long list, so confirm the set
    with `get_inventory` first
- `delete_history: false` removes only the rows and keeps their history
- requires an **administrator**

### Delete service

`controld_manager.delete_service` removes a configured service from a profile
entirely, so the profile no longer carries a row for it.

This is **not** the same as setting the service to Off with
`controld_manager.set_service_state`:

- **Off** switches the service off but leaves it configured on the profile, and
	you can switch it back on at any time.
- **Delete** removes the configuration, so using the service again means adding
	it back.

Prefer Off when you only want to stop a service applying, because it keeps the
configuration. Delete only when the service should not remain configured.

Targeting follows the same rules as the other services: select a profile by ID or
name, and a service by ID or name. Deleting is reversible, because setting the
service again on the profile adds it back.

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
- `default_rule`
- `redirect_locations`

Targeting rules:

- `catalog_type` is required
- `profile_id` and `profile_name` are optional
- if both profile selectors are provided, `profile_id` wins
- leave both profile selectors empty to return all managed profiles in the
	selected config entry scope
- `config_entry_id` and `config_entry_name` remain optional multi-entry
	disambiguators, with `config_entry_id` taking precedence
- `search` is optional and filters the catalog to rows whose own name or id
	contains the text, ignoring case. Use it to find one named entry: the service
	catalog holds over a thousand rows while `limit` caps at 500, so without a
	search a named service cannot be located. Put the name in the search box, for
	example `apple`, rather than trying to page through the list
- `profile_name` is optional and lets you scope the catalog without knowing the
  profile PK. `profile_id` wins if you supply both
- `profiles` for the selected scope
- typed `items` for the requested catalog family
- `item_count`, which reports how many rows matched after any `search`
- a plain-text `text` block that is easy to copy into service calls or notes

Manual example:

- return the available service catalog for one managed profile:
	`catalog_type: services`
	`profile_name: ["Primary"]`

- find one named service in a catalog too large to list:
	`catalog_type: services`
	`search: apple`

### Selecting profiles and endpoints by name

Every service that acts on a profile or an endpoint, and every read that can be
scoped to one, accepts either the Control D id or the display name:

| Object | By id | By name |
| --- | --- | --- |
| Profile | `profile_id` | `profile_name` |
| Endpoint | `endpoint_id` | `endpoint_name` |
| Client | `client_id` | `endpoint_mac`, `endpoint_hostname`, `endpoint_ip` |
| Filter | `filter_id` | `filter_name` |
| Service | `service_id` | `service_name` |
| Option | `option_id` | `option_name` |
| Rule group | `rule_group_id` | `rule_group_name` |

Names are convenient but not unique, so:

- An explicit id always wins when both are supplied.
- A name that matches nothing is an error, not an empty result.
- A name that matches more than one object is an error, not an arbitrary pick.
  Rename the duplicate or use the id.

The one exception is `create_endpoint`, where `endpoint_name` is the name of the
new endpoint to create rather than a way to select an existing one.

### Account overview service

`controld_manager.get_account_overview` is a read-only response service that
returns high-level account counts and block statistics for the selected Control D
scope, in one call.

Targeting rules:

- `config_entry_id` and `config_entry_name` are optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

### Inventory service

`controld_manager.get_inventory` is a read-only response service that returns the
Control D account topology: profiles and endpoints, plus clients at full detail.

Fields:

- `detail: summary` (default) returns identifying fields only
- `detail: full` adds per-row detail and includes clients
- `client_limit` caps how many clients are returned per endpoint. Default `100`,
	range 1 to 500
- `profile_id` and `endpoint_id` optionally narrow the result to one profile or
	one endpoint
- `config_entry_id` and `config_entry_name` are optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

Clients require DNS-over-HTTPS relay from the endpoint to be visible.

### Activity log service

`controld_manager.get_activity_log` is a read-only response service that returns
individual DNS queries for a recent window, including what caused each action.
This is record-level data, not aggregates.

Fields:

- `window` selects the lookback window: `15m`, `1h` (default), `6h`, `24h`,
	`7d`, or `30d`
- `search` is a free-text search over the records
- `query_action` filters by outcome: `blocked`, `bypassed`, `redirected`, or
	`failed`
- `trigger` filters by what caused the action: `default`, `grule`, `filter`,
	`service`, `custom`, or `rebind`
- `trigger_value` narrows to a specific trigger target
- `profile_id`, `endpoint_id`, and `client_id` narrow the scope
- `protocol`, `source_country`, `destination_country`, `source_isp`, `source_asn`,
	`status_code`, and `record_type` filter on record attributes
- `page` (default `0`) and `page_size` (default `50`, range 1 to 500) page through
	a larger result
- `sort_order` is `desc` (default) or `asc`

Results are capped and paged. A capped result is never presented as complete, and
no total is claimed because the surface does not provide one.

Retention is a user setting in your Control D account and is not readable by the
integration. An empty result can mean no matching traffic, a window older than
your retention, or logging being disabled. Those cases cannot be told apart.

This is the service to use for why a domain was blocked, because each record
carries the trigger that caused the action.

### Domain test service

`controld_manager.test_domain` is a read-only response service that reports the
policy verdict for one domain on one endpoint, without waiting for that traffic
to occur.

Fields:

- `endpoint_id` is required, from the inventory
- `domain` is required
- `record_type` is optional and defaults to `A`
- `config_entry_id` and `config_entry_name` are optional multi-entry
	disambiguators, with `config_entry_id` taking precedence

The response names the verdict and the source that produced it, so it answers why
a domain would be blocked. The lookup does not add a record to your activity log.

## Runtime behavior

The integration keeps normalized runtime data in memory inside the config
entry's runtime state.

That runtime data is refreshed on poll and reused by entities, managers, and
service handlers while Home Assistant is running. It is not intended to be
persistent state across Home Assistant restarts.

## AI assistants and MCP tools

Home Assistant can hand this integration's data to a connected AI assistant or
MCP client, such as the Home Assistant voice assistant pipeline or a desktop MCP
client. The integration exposes a set of tools the assistant can call to read
your Control D configuration and, if you allow it, to change it.

### Requirements

This feature needs **Home Assistant Core 2026.10 or newer**. On older versions
the integration still works normally; it simply registers no tools and the
setting described below is not shown in the options flow.

### The access tiers

One option, AI assistant (MCP) tool access, decides what the assistant can
reach. It is independent of the profile exposure settings above: exposing nothing
to Home Assistant entities does not restrict an assistant, and vice versa.

| Tier | What an assistant can do |
| --- | --- |
| Off | Nothing. No tools are registered. |
| Summary only (default) | Read account-wide counts and block statistics, plus one row per profile with the profile's name, protected device count, paused state, and block counts. The overview result also carries the system model, so this tier can explain the integration's own vocabulary. |
| Read only | Read everything: profiles, endpoints, clients, filters, services, options, rules, the activity log, and DNS lookups for a specific domain. |
| Read and control | Everything above, plus reversible changes: enabling or disabling a profile, filter, service, option, or rule; setting a service to blocked, bypassed, or redirected; attaching or clearing an endpoint's profiles; renaming an endpoint; setting an endpoint's description or analytics logging level; removing a service's row; creating or deleting an endpoint; and setting or clearing client aliases. |
| Full | Everything above, plus the three irreversible deletes: `delete_rule`, `delete_endpoint`, and `delete_client`. Each names what it destroys before acting. |

The default is Summary only. An assistant cannot reach a tier you did not select,
including through a tool that names a lower tier: a control tool reports that the
configured tier does not permit the action rather than performing it.

### What each tier sends

Every tier above Off sends profile names, because the account overview lists one
row per profile. Tiers above Summary only additionally send identifying detail to
whichever model the assistant uses. That includes:

- endpoint names and endpoint hardware identifiers
- client names and IP addresses
- domains and destination addresses from the activity log

Summary only is the narrowest tier. It sends counts and the per-profile row
described above, and stops there: no endpoint or client detail, and no
query-level analytics.

**Changing anything also requires an administrator.** Every write service is
registered as an admin-only service, so a non-admin user is rejected by the
service itself, independent of the tier. Automations and scripts are unaffected,
because the admin check only applies when a user is attached to the call.

**Reaching the surface may also require an administrator.** The MCP Server
integration has its own *Require an administrator account* option, which gates
the MCP endpoint itself rather than anything this integration controls. With it
enabled, a non-admin user cannot reach these tools at all, whatever tier is
configured.

**The assistant receives a system model.** The account overview tool returns a
short description of what the integration is and what is true across all of its
tools: the vocabulary, where identifiers come from, how to read a write result,
and how to report what is not exposed. Assist gets this in its system prompt
automatically; an MCP client receives it from that tool, which is why the
tool is worth calling once before asking anything substantive.

Treat Read and control and Full as consequential tiers: the assistant can change
real policy, and a mistake affects every device on the affected profile. Prefer
timed changes and leave the tier at Summary only or Off unless you specifically
want the assistant to make changes.

### Enabling it

1. Open the integration options and choose Integration settings.
2. Set AI assistant (MCP) tool access to the tier you want.
3. Save, then reload the integration so the tools re-register.

Reducing the tier takes effect on the same reload. Removed tools are no longer
advertised to the assistant.

### What it can answer

The tools are grouped by how a person asks, and orientation tools are available
at every tier above Off:

- an account overview with per-profile counts
- an inventory of profiles, endpoints, clients, filters, services, options, and
  rules
- recent activity, including which rule or filter blocked a request and why
- a DNS lookup for a single domain on a single endpoint, which does not add a
  record to your activity log
- the available filters, services, options, and rule folders on a profile

A common question is why a domain was blocked. The assistant answers it by
looking the domain up, then reading the activity log for that domain, then
reading the policy that matched.

### Retention

Activity log and analytics retention is a **user setting in your Control D
account**, and the integration cannot read its current value. The integration
reports the documented maximums: about 33 days for the activity log and up to
about a year for aggregated statistics. Your account may keep less, and activity
logging may be turned off entirely.

An empty activity result therefore does not prove there was no traffic. It can
mean no matching traffic, a window older than your retention, or logging being
disabled, and the integration cannot tell these apart. Extend the window before
concluding that nothing happened.

### Cost and size

There is no caching layer. A typical page of 100 activity records is roughly
47 KB, so read tools default to a short window and a small page size, and the
assistant is expected to narrow the query rather than pull everything. A capped
result is always labeled as capped; the integration never reports a truncated
list as complete and never claims a total it does not have.

### Related documentation

`docs/MCP_TOOL_REFERENCE.md` documents the full tool surface, response shapes,
and annotations. `docs/ARCHITECTURE.md` describes the layer rules the tool layer
follows.

## Limitations

- endpoint discovery still treats the Control D devices inventory as the
	authoritative source for endpoint entities
- nested router clients contribute to the account endpoint total, but they are
	not created as standalone endpoint entities
- profile analytics and endpoint analytics refresh intervals are configured, but
	the integration centers runtime behavior on the configuration inventory
	refresh path
- assistant tools report an action as applied even when it was already in that
	state for endpoint analytics logging only, because the runtime inventory
	does not carry each endpoint's current logging level. Every other control
	tool checks first and reports already_in_state
- assistant tools offer no undo for endpoint analytics logging changes or for
	deleting a custom rule. Deleting is permanent, and the endpoint logging level
	is not readable, so there is no previous value to restore
- an assistant undo is a list of calls, one per affected target, because a
	change that spans several targets usually needs several calls to reverse

## Troubleshooting

- If Status reports Degraded or Problem, check the last refresh error attribute.
- If the Control D API key is rejected, ensure a Home Country is set in your
	Control D preferences on the website.
- If a profile should disappear from Home Assistant, verify that Enable
	management in Home Assistant is turned off for that profile.
- If expected service controls are missing, verify that either Expose all
	active services is on for that profile or the relevant service categories are
	selected for that profile.
- If expected 3rd-party filter entities are missing, verify that Expose
	3rd-party filters is turned on for that profile.
- If expected custom rule controls are missing, verify that either Expose all
	custom rules is on for that profile or the specific rules or rule folders are
	exposed for that profile.
- If expected profile options are missing, verify that the profile is managed
	in Home Assistant and that Expose advanced profile options is turned on when
	you expect the larger option set.
- If entities stay enabled or disabled after you change profile exposure
	settings, remember that Home Assistant keeps entity-registry enable or disable
	state after entities are created. The integration handles the normal default
	state for newly created entities and basic cleanup when exposure is removed,
	but manual registry changes may still require you to re-enable or disable
	entities yourself.
- If no assistant tools appear, check that Home Assistant is 2026.10 or newer
	and that AI assistant (MCP) tool access is not set to Off. After changing the
	tier, reload the integration.
- If an assistant reports that a change is not permitted, the configured tier is
	lower than the tool the assistant tried to use. Raise the tier and reload.
- If an assistant reports no activity for an endpoint, verify that endpoint's
	analytics logging is not set to None before treating the result as no traffic.