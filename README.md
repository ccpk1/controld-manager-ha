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

Control D's profile model translates cleanly into automation. Filters, service overrides,
custom rules, default-rule behavior, and endpoint activity all map naturally to scripts,
dashboards, and conditions in a way most DNS products simply do not expose. If you already
run `ctrld` on a firewall or router, this makes segmenting policy by VLAN, client, or
profile far easier than brittle scripts and manual workarounds.

The aim is an integration that does more than mirror the Control D dashboard: one that
makes Control D feel programmable, and lets you keep routine policy changes in the
background when you do not want to see them.

## 📷 Screenshots

![Hero1](https://github.com/ccpk1/controld-manager-ha/blob/main/docs/assets/Integration_Hero.png)

![Hero2](https://github.com/ccpk1/controld-manager-ha/blob/main/docs/assets/Integration_Hero2.png)

## Table of contents

- 💡 [Why Control D?](#why-control-d)
- 📷 [Screenshots](#screenshots)
- 🏆 [The platinum-quality approach](#the-platinum-quality-approach)
- ✨ [What it enables](#what-it-enables)
- 🤖 [AI assistant and MCP tool surface](#ai-assistant-and-mcp-tool-surface)
- ❤️ [Support the project](#support-the-project)
- 🧩 [Supported setup and prerequisites](#supported-setup-and-prerequisites)
- ⚡ [Quick installation](#quick-installation)
- 📖 [User guide](#user-guide)
- 🧭 [Design philosophy and scope](#design-philosophy-and-scope)
- 🏗️ [Development and architecture docs](#development-and-architecture-docs)
- 🤝 [Community and contribution](#community-and-contribution)
- 🛡️ [Security and privacy notes](#security-and-privacy-notes)
- ⚠️ [Disclaimer and liability](#disclaimer-and-liability)
- 📄 [License](#license)

## 🏆 The platinum-quality approach

This repository is not part of Home Assistant Core, but it is intentionally built against the same quality bar serious integrations are judged by. The emphasis is on durable runtime behavior, clear ownership boundaries, strict typing, translation-ready user surfaces, and predictable recovery behavior rather than a thin wrapper around a handful of API calls.

- Entry-scoped runtime: one config entry maps to one authenticated Control D instance, with multi-instance-safe isolation.
- Stable identity: devices and entities are anchored to immutable instance, profile, and endpoint identifiers rather than mutable display names.
- Manager-based architecture: business logic lives in the manager layer, while entities, services, and flows stay thin.
- Coordinator-owned refresh: one bounded polling path drives inventory, profile detail, endpoint activity, and analytics refresh.
- Opt-in expansion: high-cardinality profile surfaces stay selective so Home Assistant only creates what you actually want to manage.
- Supportability: reauthentication, reconfigure, diagnostics, translated exceptions, and unavailable or recovery logging are part of the implementation.

The repository tracks this work in `custom_components/controld_manager/quality_scale.yaml` and documents its durable standards in `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, and `docs/QUALITY_REFERENCE.md`.

## ✨ What it enables

Control D Manager goes beyond a basic status integration. It gives Home Assistant a practical operating surface for day-to-day DNS policy control.

### At-a-glance capabilities

| Capability | What it gives you |
| --- | --- |
| Profile devices | One Home Assistant device per Control D instance and one per managed profile, giving controls, analytics, and endpoint entities a clean home. |
| Selective exposure | Control D can offer thousands of filters, services, and options. Home Assistant creates only the profile surfaces you deliberately enable, so the registry stays readable. |
| Filter and service control | Enable or disable filters, and set service modes to Off, Blocked, Bypassed, or Redirected, from entities or services. |
| Custom rules | Expose selected rule folders, individual custom rules, or the full live rule surface for a profile. |
| Endpoint status | Per-endpoint activity entities showing when a client was last seen and which profile currently owns it. |
| Endpoint hygiene | Rename endpoints, set analytics logging levels, and manage client aliases, without turning those high-churn surfaces into entities. |
| Analytics | Account and profile sensors for total, blocked, blocked-ratio, bypassed, and redirected queries, plus a manual sync button. |
| Automation-ready services | Every mutation is a service, so automations never depend on a wall of always-on switches. |
| Pi-hole dashboard compatibility | Summary analytics sensors align with the `custom:pi-hole` card, so familiar DNS dashboards can be reused. |
| Tamper-detection hooks | Endpoint activity can be cross-referenced with router or firewall visibility to spot likely DNS bypass behavior. |
| Stateless pausing | Temporarily disable a profile with a duration, and Control D handles the countdown upstream. |
| AI assistant access | The same surface is available to an AI assistant or MCP client, from read-only reporting up to a gated destructive set. |

### The entity model

One Home Assistant device per Control D instance, and one per managed profile. Endpoints
stay as entities rather than devices, which keeps the device registry compact while still
making per-endpoint activity visible.

Exposure is opt-in. Control D offers thousands of possible filters, services, and options,
and the integration creates only the profile surfaces you enable. Home Assistant also
honours entity-registry enable and disable choices after creation, so changing exposure
later may need a manual re-enable.

### Services

Every mutation is available as a service, so automations do not depend on a wall of
always-on switches. There are 24 in total: read services that change nothing, and write
services covering profiles, filters, services, options, rules, endpoints, and client
aliases. Writes require an administrator, while a call with no user attached, such as a
service call from an automation, is not blocked.

Services can target profiles and endpoints by name or by id, read per-query activity with
the filter, service, or rule that caused each action, adjust service modes, create or
expire rules, and discover configured filters, services, options, and rules.

Parameters, examples, and the full list are in the [user guide](docs/USER_GUIDE.md#services).

### Analytics and endpoint visibility

- Account-level and profile-level sensors expose total queries, blocked queries, blocked-query ratio, bypassed queries, redirected queries, and status.
- A diagnostic `Sync now` button lets you force an immediate refresh after making changes in Control D.
- Endpoint status entities use last-activity data and profile-level inactivity thresholds to show whether a client is still active.
- Every entity exposes shared metadata attributes such as `integration`, `profile_name`, `purpose`, `item_type`, `taxonomy_path`, and `item_name`, making dashboards, templates, and automations less dependent on entity-name parsing.
- Several analytics sensors intentionally align with the `custom:pi-hole` card's expected translation keys, giving you a practical way to reuse existing DNS dashboard layouts.

👉 Check the [Pi-hole card example in the user guide](docs/USER_GUIDE.md#pi-hole-card) for a ready-to-use YAML snippet you can drop into a `custom:pi-hole` dashboard.

For households and family-control use cases, endpoint visibility is more than a convenience feature. It can act as a practical tamper-detection signal. If a phone or tablet is normally chatty on Control D and suddenly stops showing activity, that is a useful indicator to investigate whether the device has switched away from the expected DNS path. It is not a cryptographic guarantee, but it is a valuable operational hook for catching the real-world ways DNS controls get bypassed.

## 🤖 AI assistant and MCP tool surface

Control D Manager registers its own Home Assistant LLM API. Home Assistant serves that
to its built-in Assist pipeline and, through the MCP Server integration, to any
MCP-capable client: desktop and editor assistants, chat apps, and custom agents. There
is no separate server to run, so the same surface is reachable from Assist or from
whichever AI harness you already trust.

Tools alone would not make this useful. The part that makes it work is the context
shipped alongside them. Every tool description is composed from a shared model of how
Control D works, a block of rules that hold across a family of tools, and that tool's own
specifics, so an assistant knows what a profile, endpoint, and client are, where
identifiers come from, and how to read the result of a write, before you ask it anything.

That context is the difference between an assistant that can call the API and one that
reasons about your setup correctly.

Access is tiered and only summary level by default, from read-only reporting up to a separate destructive
set. Every write requires an administrator, selectors are never guessed, and a write
reports what actually changed, what the previous value was, and the call that reverses it.
The tier list, what each tier sends, and how to enable it are in the
[user guide](docs/USER_GUIDE.md#ai-assistants-and-mcp-tools).

### In practice

These are real Assist sessions, lightly trimmed, transcribed from Home Assistant Assist
using a low-cost zero-data-retention model on OpenRouter. Profile names are changed;
everything else is as it came back. The tier each session needs is noted, so you can see
what the default buys you before raising it.

**A status check** — works at Summary only, the default

> **tell me about my control d**
>
> Your Control D account protects 293 devices across 18 endpoints using 8 profiles. In
> the recent analytics window, your network handled 348,140 total queries: 153,741
> blocked queries, 194,046 bypassed queries, 353 redirected queries. All 8 profiles are
> currently active and unpaused.

> **Show me the profiles**
>
> Your Control D account has 8 profiles:
>
> 1. **Default Profile** (293 protected devices, active)
> 2. **Alex's Phone** (1 protected device, active)
> 3. **Ben's Phone** (3 protected devices, active)
> 4. **Developer Testing** (0 protected devices, active)
> 5. **Jane's Devices** (3 protected devices, active)
> 6. **Jane's Phone** (2 protected devices, active)
> 7. **Nora's Devices** (1 protected device, active)
> 8. **Nora's Phone** (1 protected device, active)

**An investigation** — needs Read only

> **Jane's phone wasn't working right this morning**
>
> Looking at the activity log for **Jane's Phone** today, it has experienced several
> blocked queries by the `x-hagezi-light` filter. Some of the domains being blocked
> include:
>
> - `app-measurement.com`
> - `googleads.g.doubleclick.net`
> - `api-eu.mixpanel.com`
> - `app-analytics-services.com`
> - `incoming.telemetry.mozilla.org`
>
> These are standard tracker/analytics blocks, but if an app or service Jane was trying
> to use relies on one of them, it could cause issues. Would you like me to make an
> exception or pause protection for Jane's phone?

> **Give me some time ranges those blocks happened today**
>
> Based on the activity log for **Jane's Phone** today, the blocked queries occurred in
> these time windows (all times in UTC):
>
> - **07:06 to 10:56 UTC**: Consistent background telemetry and analytics blocks (such as
>   `api-eu.mixpanel.com`, `app-measurement.com`, and `googleads.g.doubleclick.net`)
>   occurring roughly every 30 minutes.
> - **10:19 to 10:56 UTC**: Additional blocks including telemetry domains
>   (`incoming.telemetry.mozilla.org`) and app measurement services.
>
> If Jane was using her phone around 7:00 AM to 11:00 AM UTC, those background blocks
> might have affected her apps.

> **tell me more about that blocking service**
>
> The blocking service causing those blocks on Jane's phone is **Hagezi's Light
> blocklist** (tracked in Control D as `x-hagezi-light`).
>
> It is a popular, lightweight third-party community blocklist designed to block common
> online annoyances without being overly aggressive. Specifically, it targets:
>
> - **Ad networks and tracking domains** (like Google Ads / `doubleclick.net`)
> - **App analytics and telemetry** (like Mixpanel and `app-measurement.com`)
> - **Browser telemetry** (like Mozilla's telemetry)
>
> Because it runs at the DNS level through Control D, it prevents Jane's phone from even
> resolving the addresses for these trackers and analytics servers, stopping them in the
> background.

> **why is it being applied?**
>
> The `x-hagezi-light` filter is being applied because it is enabled within the
> configuration of the **Jane's Phone** profile (profile ID `733915vbnc48r`).
>
> Every profile in Control D can have its own set of built-in and third-party security or
> blocking filters turned on. In this case, the Hagezi Light blocklist has been activated
> specifically for Jane's phone profile, so any DNS requests matching that list get
> blocked automatically.

> **What blocks and filters apply to her Chromebook?**
>
> Jane's Chromebook is covered under the **Jane's Devices** profile (with the **Default
> Profile** applied as a secondary/fallback profile).
>
> The active filters and protection categories enabled on the **Jane's Devices** profile
> include: Adult Content, Clickbait, Dating, Drugs, Gambling, Malware, New Domains,
> Phishing, Torrents & Piracy, and VPN & DNS.

**Acting on it** — the one step that needs Read and control

> **I want to pause the blocking on Ben's phone for 5 minutes**
>
> I have paused the "Ben's Phone" profile for 5 minutes.
>
> You can reverse this change at any time by running
> `controld_manager__enable_profile(profile_id='518044mplx72q')`.

Nothing in that sequence was clicked. The assistant resolved a device to the profile that
owns it, named the filter responsible, described what that filter does, explained why it
was active on that profile, and compared the protections on a second device — all of that
without write access. The pause is the only step above Read only, and it is the clearest
illustration of why this beats a dashboard: the duration is part of the request, so the
change is timed and self-reversing, and the result hands back the call that cancels it.

## ❤️ Support the project

Building and maintaining integrations like this takes a substantial amount of time across implementation, testing, release validation, documentation, and long-term maintenance. If Control D Manager is giving you the DNS control and visibility you have been looking for in Home Assistant, here is how you can help keep the project moving.

⭐ Star this repository. This is the easiest and most important signal that the project is providing real value. It helps more users discover the integration, gives the repository visible momentum, and tells me the work is landing with the community.

❤️ Sponsor or tip if you want to go further. Financial support is never required, but it is the strongest possible signal that the time spent building, testing, and maintaining this integration is worth continuing. It helps justify the less visible work too: validation gates, bug fixes, documentation, release prep, and the higher-quality standards that make a project like this feel dependable instead of fragile.

If Control D Manager is making your smart home or homelab better, I would genuinely appreciate the support.

- ⭐ Star the repository: <https://github.com/ccpk1/controld-manager-ha>
- ❤️ Sponsor on GitHub: <https://github.com/sponsors/ccpk1>
- ☕ Buy me a coffee: <https://buymeacoffee.com/ccpk1>


## 🧩 Supported setup and prerequisites

- Control D account: a valid account and a write-capable API token.
- Home Assistant: `2026.3` or newer. The optional AI assistant surface needs `2026.10`
  or newer; on older versions every other feature works normally and the setting is not
  offered.
- Installation: HACS is recommended, and manual installation is supported.
- Connectivity: Home Assistant must be able to reach the Control D cloud API.

A write-capable token is required because the integration supports real mutation paths,
not just read-only reporting. Profile pause, filter changes, service changes, option
changes, and rule management all depend on that permission level.

## ⚡ Quick installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=controld-manager-ha&category=integration)

Create a Control D API key with write access, then restart Home Assistant and add the
integration from **Settings → Devices & services**.

Step-by-step instructions for HACS and for manual installation are in the
[user guide](docs/USER_GUIDE.md#installation).

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
- AI assistant (MCP) tool access and its tiers

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
- [docs/ENGINEERING_FINDINGS.md](docs/ENGINEERING_FINDINGS.md)
- [docs/MCP_TOOL_REFERENCE.md](docs/MCP_TOOL_REFERENCE.md)
- [docs/QUALITY_REFERENCE.md](docs/QUALITY_REFERENCE.md)
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)

Repository layout:

```text
├── custom_components/
│   └── controld_manager/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_STANDARDS.md
│   ├── ENGINEERING_FINDINGS.md
│   ├── MCP_TOOL_REFERENCE.md
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

Bridging DNS policy control into Home Assistant is powerful, and that power deserves a
clear security posture.

- Unofficial project: this repository is an independent community project, not
  affiliated with, endorsed by, or supported by Control D. It is not an official Control D
  support channel.
- Sensitive capability: the integration can modify Control D policy, so your Home
  Assistant security posture matters. If your instance is exposed or compromised, DNS
  policy changes could be triggered through it. Protect Home Assistant accordingly with
  sound account, remote-access, and permission practices.
- Redacted diagnostics: diagnostics are designed to stay useful without exposing sensitive
  data directly.
- AI assistant data sharing: the default summary tier sends counts and profile names.
  Read only and above also send endpoint names and MAC addresses, client names and IP
  addresses, and activity-log domains to whichever model you use. Credentials, API tokens,
  and passwords are never sent.
- Cloud-backed integration: this is a `cloud_polling` integration, not a local Control D
  control plane.

Vulnerability reporting guidance lives in [SECURITY.md](SECURITY.md), and support
expectations live in [SUPPORT.md](SUPPORT.md).

## ⚠️ Disclaimer and liability

This software is provided "as is", without warranty of any kind, express or implied. It is an unofficial community project and is not affiliated with, endorsed by, or supported by Control D. While the integration is being engineered carefully and validated continuously, you are responsible for reviewing the behavior you automate and for securing the Home Assistant environment that is allowed to control your DNS policy.

Use this project with appropriate caution, especially when exposing Home Assistant remotely or granting other users access to service calls that can alter Control D behavior.

AI-Assisted Development: In today’s age, leveraging AI is one of the few ways a maintainer can realistically build, thoroughly test, and actively support a truly complex, high-quality open-source project. But to be clear, this integration isn't just blindly "vibe coded." While AI acts as a significant force multiplier for the workflow, human oversight dictates the architecture. Every commit is strictly audited, backed by extensive tests, and measured against rigorous Home Assistant development standards to ensure long-term stability.

## 📄 License

This project is licensed under the GPL-3.0 license. See [LICENSE](LICENSE).
