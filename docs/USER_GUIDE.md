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
- Generate endpoint sensors
	Creates endpoint activity entities for devices that belong to that profile.
- Endpoint inactivity threshold (minutes)
	Controls how long an endpoint can remain inactive before its endpoint status
	entity reports inactive.
- Allowed service categories
	Limits which Control D service categories are exposed as switches.
- Auto-enable switches for allowed service categories
	Leaves newly created service switches enabled by default for the allowed
	categories. This can increase entity count over time.
- Expose custom rules
	Lets you expose selected rule folders or individual custom rules as switches.

### Integration settings

This form controls refresh cadence only.

- Configuration sync interval (minutes)
	Controls how often structural account data is refreshed.
- Profile analytics interval (minutes)
	Reserved for higher-level analytics refresh cadence.
- Endpoint analytics interval (minutes)
	Reserved for endpoint telemetry refresh cadence.

Current supported bounds are 5 to 60 minutes.

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

- a pause or disable switch for the profile
- filter switches
- filter mode selectors where the upstream filter supports multiple levels
- service switches for allowed service categories
- custom rule switches for exposed rules
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

### Disable switch

Each managed profile exposes a Disable switch. Turning it on pauses the profile.
Turning it off resumes the profile.

### Filter switches and mode selectors

Filters are exposed as switches. Filters with multiple upstream levels also get
a selector entity for the active mode.

### Service switches

Service switches are only created for the service categories you allow in the
profile options.

### Custom rule switches

Custom rules are only created for the rule folders or individual rules you
expose in the profile options.

### Endpoint status entities

When enabled for a profile, endpoint status entities are created for that
profile's endpoints. These entities are compact activity surfaces derived from
last activity time.

## Services

The integration currently registers these Home Assistant services:

- `controld_manager.pause_profile`
- `controld_manager.resume_profile`

These services can target profiles by entity, config entry ID, or config entry
name.

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
- If expected service switches are missing, verify that the relevant service
	categories are enabled for that profile.
- If expected custom rule switches are missing, verify that the specific rules
	or rule folders are exposed for that profile.