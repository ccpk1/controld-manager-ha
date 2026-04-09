[![Quality Baseline: Platinum-ready](https://img.shields.io/badge/Quality%20Baseline-platinum--ready-1E88E5.svg)](https://github.com/ccpk1/controld-manager-ha)
[![Quality Gates](https://img.shields.io/github/actions/workflow/status/ccpk1/controld-manager-ha/lint-validation.yaml?branch=main&label=Quality%20Gates)](https://github.com/ccpk1/controld-manager-ha/actions/workflows/lint-validation.yaml)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/controld-manager-ha/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs)
[![Version](https://img.shields.io/github/v/release/ccpk1/controld-manager-ha?include_prereleases&label=Version&color=1E88E5)](https://github.com/ccpk1/controld-manager-ha/releases)
[![Stars](https://img.shields.io/github/stars/ccpk1/controld-manager-ha?color=1E88E5&labelColor=555)](https://github.com/ccpk1/controld-manager-ha/stargazers)

![Control D Manager for Home Assistant](https://github.com/ccpk1/controld-manager-ha/blob/main/docs/assets/3-1%20Logo%20Rectangle%402x.png)

> Cloud-smart Home Assistant control for Control D DNS. Profile-driven, automation-first, and designed to keep your entity registry focused instead of flooded.

Control D Manager is a standalone Home Assistant custom integration for managing one or more authenticated Control D instances. It gives you native Home Assistant control over profiles, filters, services, profile options, custom rules, endpoint activity, and analytics while keeping the runtime typed, entry-scoped, and aligned with a platinum-quality engineering bar.

## 💡 Why Control D?

Control D is especially compelling in Home Assistant because its **profile model translates cleanly into automation**. **Filters, service overrides, custom rules, default-rule behavior, and endpoint activity** all map naturally to scripts, dashboards, and conditions in a way that many DNS products simply do not expose.

That matters because a good Home Assistant integration should do more than mirror a web dashboard. It should **make Control D feel programmable**. This project leans into that by combining a selective entity model with a broader native service layer, so you can build polished dashboards when you want them and keep routine policy changes in the background when you do not.

Control D is also **unusually strong as a homelab foundation**. If you already use `ctrld` on a firewall or router, Control D makes it much easier to segment policy by VLAN, client, or profile without resorting to brittle scripts and manual workarounds. That broader ecosystem is a big part of why this integration exists: the service is already flexible enough to deserve a Home Assistant layer that can actually keep up with it.

## 📷 Screenshots

![Hero1](https://github.com/ccpk1/controld-manager-ha/blob/main/docs/assets/Integration_Hero.png)

![Hero2](https://github.com/ccpk1/controld-manager-ha/blob/main/docs/assets/Integration_Hero2.png)

## Table of contents

- 💡 [Why Control D?](#why-control-d)
- 📷 [Screenshots](#screenshots)
- 🏆 [The platinum-quality approach](#the-platinum-quality-approach)
- ✨ [What it enables](#what-it-enables)
- ❤️ [Support the project](#support-the-project)
- 🧩 [Supported setup and prerequisites](#supported-setup-and-prerequisites)
- ⚡ [Quick installation](#quick-installation)
- 📖 [User guide](#user-guide)
- 🧭 [Design philosophy and scope](#design-philosophy-and-scope)
- 🏗️ [Development and architecture docs](#development-and-architecture-docs)
- 🤝 [Community and contribution](#community-and-contribution)
- 🛡️ [Security and privacy notes](#security-and-privacy-notes)
- 🔒 [Security and support posture](#security-and-support-posture)
- ⚠️ [Disclaimer and liability](#disclaimer-and-liability)
- 📄 [License](#license)

## 🏆 The platinum-quality approach

This repository is not part of Home Assistant Core, but it is intentionally built against the same quality bar serious integrations are judged by. The emphasis is on durable runtime behavior, clear ownership boundaries, strict typing, translation-ready user surfaces, and predictable recovery behavior rather than a thin wrapper around a handful of API calls.

- Entry-scoped runtime: one config entry maps to one authenticated Control D instance, with multi-instance-safe isolation.
- Stable identity: devices and entities are anchored to immutable instance, profile, and endpoint identifiers rather than mutable display names.
- Manager-based architecture: business logic lives in the manager layer, while entities, services, and flows stay thin.
- Coordinator-owned refresh: one bounded polling path drives inventory, profile detail, endpoint activity, and analytics refresh.
- Opt-in expansion: high-cardinality profile surfaces stay selective so Home Assistant only creates what you actually want to manage.
- Supportability: reauthentication, reconfigure, diagnostics, translated exceptions, and unavailable or recovery logging are already part of the implementation.

The repository tracks this work in `custom_components/controld_manager/quality_scale.yaml` and documents its durable standards in `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, and `docs/QUALITY_REFERENCE.md`.

## ✨ What it enables

Control D Manager is already more than a basic status integration. It gives Home Assistant a practical operating surface for day-to-day DNS policy control.

### Highlights

- Zero entity bloat by default: the integration starts with a compact core surface, then lets you opt into the higher-cardinality Control D objects you actually want exposed.
- Goldilocks entity expansion: Control D can surface thousands of possible filters, services, and options, but Home Assistant only creates the categories and profile surfaces you deliberately enable.
- Native profile operations: disable profiles, change service modes, adjust filters, modify options, and work with custom rules directly from Home Assistant.
- Endpoint activity visibility: expose per-endpoint activity entities to see when clients were last active on Control D and which profile currently owns them.
- Automation-ready service layer: the integration is built for scripts and automations as much as dashboards, including temporary policy changes and copyable catalog discovery.
- Partial Pi-hole dashboard compatibility: reuse familiar DNS dashboard cards for summary analytics without pretending Control D is a full Pi-hole clone.

### Profile-centric control

- Create one Home Assistant account device per Control D instance and one device per managed profile.
- Expose profile disable state, filters, filter modes, service modes, profile options, default-rule behavior, and selected custom rules as native Home Assistant entities.
- Keep endpoint activity visible through compact endpoint status entities without creating a device-registry explosion.
- Use the options flow to choose which profiles and high-cardinality surfaces Home Assistant should expose.

That opt-in model matters with Control D because the available surface is enormous. The integration is capable of exposing very large numbers of filters, services, and options as Home Assistant entities, but it does so thoughtfully so your registry stays usable instead of turning into a wall of noise.

### Automation-first service layer

When a dashboard switch is not the right tool, the integration exposes shared services for direct automation.

Current service surface:

- `controld_manager.disable_profile`
- `controld_manager.enable_profile`
- `controld_manager.set_filter_state`
- `controld_manager.set_service_state`
- `controld_manager.set_option_state`
- `controld_manager.set_default_rule_state`
- `controld_manager.set_rule_state`
- `controld_manager.create_rule`
- `controld_manager.delete_rule`
- `controld_manager.get_catalog`

This makes it possible to target profiles by name or identity, create or expire custom rules from automations, adjust service modes in the background, and query copyable catalogs for filters, services, rules, or profile options.

### Analytics and endpoint visibility

- Account-level and profile-level sensors expose total queries, blocked queries, blocked-query ratio, bypassed queries, redirected queries, and status.
- A diagnostic `Sync now` button lets you force an immediate refresh after making changes in Control D.
- Endpoint status entities use last-activity data and profile-level inactivity thresholds to show whether a client is still active.
- Several analytics sensors intentionally align with the `custom:pi-hole` card's expected translation keys, giving you a practical way to reuse existing DNS dashboard layouts.

👉 Check the [Pi-hole card example in the user guide](docs/USER_GUIDE.md#pi-hole-card) for a ready-to-use YAML snippet you can drop into a `custom:pi-hole` dashboard.

For households and family-control use cases, endpoint visibility is more than a convenience feature. It can act as a practical tamper-detection signal. If a phone or tablet is normally chatty on Control D and suddenly stops showing activity, that is a useful indicator to investigate whether the device has switched away from the expected DNS path. It is not a cryptographic guarantee, but it is a valuable operational hook for catching the real-world ways DNS controls get bypassed.

### Homelab and segmentation value

Control D pairs especially well with environments that already use profile-based network segmentation. If you run `ctrld` at the firewall or router layer, Control D can give you broad visibility across your network while still letting you separate policy by VLAN and by individual client. This integration complements that model by bringing those profile controls and status surfaces into Home Assistant, where they can participate in the same automations and dashboards as the rest of your stack.

### At-a-glance capabilities

| Feature | Description |
| --- | --- |
| Profile devices | Dedicated Home Assistant devices for the Control D account and each managed profile, giving rules, controls, analytics, and endpoints a clean home. |
| Dynamic routing | Change supported service modes such as Off, Blocked, Bypassed, or Redirected from Home Assistant. |
| Custom rule exposure | Opt in to expose selected rule folders or individual custom rules as Home Assistant controls. |
| Tamper-detection hooks | Cross-reference endpoint activity with router or firewall visibility to spot likely DNS bypass behavior. |
| Stateless pausing | Temporarily disable a profile with a duration while Control D handles the upstream countdown. |

### Important current limitation

Redirect-related controls exist in the current release, but redirect behavior has not yet been fully validated end to end against live Control D behavior. Treat redirect-capable options and rule modes as early functionality until that validation work is complete.

## ❤️ Support the project

Building and maintaining integrations like this takes a substantial amount of time across implementation, testing, release validation, documentation, and long-term maintenance. If Control D Manager is giving you the DNS control and visibility you have been looking for in Home Assistant, here is how you can help keep the project moving.

⭐ Star this repository. This is the easiest and most important signal that the project is providing real value. It helps more users discover the integration, gives the repository visible momentum, and tells me the work is landing with the community.

❤️ Sponsor or tip if you want to go further. Financial support is never required, but it is the strongest possible signal that the time spent building, testing, and maintaining this integration is worth continuing. It helps justify the less visible work too: validation gates, bug fixes, documentation, release prep, and the higher-quality standards that make a project like this feel dependable instead of fragile.

If Control D Manager is making your smart home or homelab better, I would genuinely appreciate the support.

- ⭐ Star the repository: <https://github.com/ccpk1/controld-manager-ha>
- ❤️ Sponsor on GitHub: <https://github.com/sponsors/ccpk1>
- ☕ Buy me a coffee: <https://buymeacoffee.com/ccpk1>


## 🧩 Supported setup and prerequisites

- Control D account: you need a valid Control D account and a write-capable API token.
- Home Assistant: requires Home Assistant `2026.3` or newer.
- Installation method: HACS is recommended, but manual installation is also supported.
- Connectivity: Home Assistant must be able to reach the Control D cloud API.

Why a write-capable token? Because this integration supports real mutation paths, not just read-only reporting. Profile pause, filter changes, service changes, option changes, and rule management all depend on that permission level.

## ⚡ Quick installation

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=controld-manager-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open HACS -> Integrations -> Custom repositories.
3. Add `https://github.com/ccpk1/controld-manager-ha` as an Integration repository.
4. Search for `Control D Manager`, install it, and restart Home Assistant.
5. Go to Settings -> Devices & Services -> Add Integration.
6. Select `Control D Manager` and complete the API-token flow.

### Manual installation

1. Download this repository.
2. Copy `custom_components/controld_manager` into your Home Assistant `custom_components/` directory.
3. Restart Home Assistant.
4. Add the integration from Settings -> Devices & Services.

### Before you start the config flow

Create a Control D API key with write access. The integration uses that token for both inventory refresh and supported policy mutations.

## 📖 User guide

The operating guide lives in [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

It covers:

- installation and removal
- config flow, reauthentication, and reconfigure behavior
- options-flow policy selection
- account and profile entities
- endpoint status entities
- analytics sensors and Pi-hole-card compatibility
- service examples and catalog discovery
- diagnostics and availability behavior

## 🧭 Design philosophy and scope

Control D Manager is designed to be opinionated in the right places.

- The goal: expose the Control D surfaces that have clear automation value and present them in a way that feels native in Home Assistant.
- The flexibility: you decide how much of Control D becomes a Home Assistant surface and how much stays service-driven, giving you precise control without forcing unnecessary entity bloat.
- The device model: the device registry stays compact by modeling the Control D instance and profiles as devices while leaving physical endpoints as entities only.
- The service model: richer write operations belong in Home Assistant services so automations can stay expressive without depending on a wall of always-on switches.

This is a Home Assistant integration for real household and homelab workflows, not a Control D account-management console or a full mirror of every upstream API object.

## 🏗️ Development and architecture docs

The durable project rules live in:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md)
- [docs/QUALITY_REFERENCE.md](docs/QUALITY_REFERENCE.md)
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)

Repository layout:

```text
├── custom_components/
│   └── controld_manager/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_STANDARDS.md
│   ├── QUALITY_REFERENCE.md
│   └── USER_GUIDE.md
└── tests/
    └── components/
        └── controld_manager/
```

## 🤝 Community and contribution

- Issues and feature requests: <https://github.com/ccpk1/controld-manager-ha/issues>
- Discussions: <https://github.com/ccpk1/controld-manager-ha/discussions>
- Pull requests: <https://github.com/ccpk1/controld-manager-ha/pulls>
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## 🛡️ Security and privacy notes

Bridging DNS policy control into Home Assistant is powerful, and that power deserves a clear security posture.

- Unofficial project: this repository is an independent community project and is not affiliated with, endorsed by, or supported by Control D.
- Sensitive capability: the integration can modify Control D policy, so your Home Assistant security posture matters.
- Redacted diagnostics: diagnostics are designed to remain useful without exposing sensitive data directly.
- Cloud-backed integration: this is a `cloud_polling` integration, not a local Control D control plane.

If your Home Assistant instance is exposed or compromised, DNS policy changes could be triggered through this integration. Protect Home Assistant accordingly with sound account, remote-access, and permission practices.

## 🔒 Security and support posture

- Vulnerability reporting guidance lives in [SECURITY.md](SECURITY.md)
- Support expectations and contact posture live in [SUPPORT.md](SUPPORT.md)
- This repository should not be treated as an official Control D support channel

## ⚠️ Disclaimer and liability

This software is provided "as is", without warranty of any kind, express or implied. It is an unofficial community project and is not affiliated with, endorsed by, or supported by Control D. While the integration is being engineered carefully and validated continuously, you are responsible for reviewing the behavior you automate and for securing the Home Assistant environment that is allowed to control your DNS policy.

Use this project with appropriate caution, especially when exposing Home Assistant remotely or granting other users access to service calls that can alter Control D behavior.

## 📄 License

This project is licensed under the GPL-3.0 license. See [LICENSE](LICENSE).
