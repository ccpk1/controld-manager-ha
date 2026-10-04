# Control D Manager — MCP Tool Reference

The authoritative reference for the tools this integration exposes to LLMs and MCP
clients (via Home Assistant's `mcp_server`). It is also the **spec** the tool
surface is built and tested against.

- **Audience:** LLM/MCP tool authors, agent developers, and anyone wiring a client
  to this integration. Users of the Home Assistant UI or service calls should read
  [`USER_GUIDE.md`](USER_GUIDE.md) instead.
- **Scope:** every available and planned tool. Tools marked *(planned)* do not
  exist yet; this document is the target they are built to.
- **Status:** the spec exists, the API foundation is complete, and `get_account_overview`
  is implemented. The remaining tools are added in Phase 2 of
  `plans/in-process/CONTROLD_MANAGER_LLM_TOOLS_IN-PROCESS.md`.
- **How to read it:** [Conventions](#conventions) apply to every tool; each tool
  below follows one fixed template. Read Conventions first.

**Who can use these tools.** The surface is not Assist-only. Home Assistant's
`mcp_server` integration serves it to **any MCP client** — desktop and editor
assistants, chat clients, and custom agents — as well as to Assist. Enabling it is
therefore a disclosure decision, and the tier is the control that governs it.

---

## Conventions

### Identifier spaces

Every identifier a tool accepts is a **Control D** identifier, obtained from a
read tool. The model is never asked for a Home Assistant id.

That distinction matters for `profile_id`, because the underlying services
declare it with a Home Assistant device selector while every read surface returns
the Control D profile PK. The tool layer translates the PK to the profile's device
id before calling the service, so one identifier flows end to end. A value that
does not map is passed through untouched and the service rejects it, rather than
the tool silently dropping the scope.

`get_inventory` and `get_activity_log` are the exception in the other direction:
their services filter on the Control D PK directly, so their `profile_id` is
passed through and is never translated.

### Terminology

These words are exact and are not interchangeable. They come from the repository
lexicon in `ARCHITECTURE.md` and `DEVELOPMENT_STANDARDS.md`.

| Term | Meaning |
| --- | --- |
| **Profile** | A Control D configuration container holding rules, services, and blocklists |
| **Endpoint** | A top-level Control D protected row from `/devices` (router segment, ctrld instance, or individually protected client) |
| **Client** | A client visible under an endpoint; client aliases are client-scoped |
| **Device** | A Home Assistant device-registry container only |
| **Entity** | A Home Assistant platform object only |

Scope rules:

- A **client under an endpoint follows that endpoint's profile** (a ctrld VLAN
  endpoint, whose clients inherit its profile).
- A client that is **explicitly assigned** a profile **is its own endpoint**.
  There is no "individually protected" flag on a sub-client; assignment is what
  makes it an endpoint.
- Never call an endpoint a device or a client, and never call a client an
  endpoint.

### Naming

Every tool is named `controld_manager__<verb>_<noun>`, named for **what it
returns, not where the data came from**. Control tool names mirror the underlying
service name (`set_filter_state`, `rename_endpoint`, …). The `controld_manager__`
prefix disambiguates our tools when several LLM APIs are merged.

### Availability model

A single option, **AI assistant (MCP) tool access**, controls what is registered.
Every write service requires an **admin user**, so a non-admin caller is rejected
by the service layer and the tool reports `status: failed`. This tier is the
additional limit on what a connected client can reach at all: it decides which
tools are registered, while the admin check decides who may use them.
a connected client can reach. Profile names are not treated as private: they are
user-assigned labels already shown as Home Assistant device names.

| Tier | Registered | Identifiers |
| --- | --- | --- |
| **Off** | nothing | — |
| **Summary only** *(default)* | the account overview | counts plus per-profile names and counts |
| **Read only** | all read tools | full detail |
| **Read and control** | read tools + reversible controls | full |
| **Full** | read + control + destructive | full, irreversible |

Requires **Home Assistant Core 2026.10+**. On older Core the integration registers
no tools and offers no option; every other feature is unaffected.

### Response shape — reads

```json
{
  "result": { "...payload..." },
  "meta": { "response_type": "block_breakdown", "truncated": true }
}
```

- `result` — the payload.
- `meta.response_type` — a stable name for the shape.
- `meta.truncated` / `meta.applied_limit` — present only when a cap was applied.
- `meta.has_more` / `meta.page` / `meta.page_size` — present on paged surfaces.

### Response shape — control actions

```json
{
  "status": "applied",
  "changed": true,
  "target": { "id": "461wtt4eyr", "name": "Firewalla-VLAN60" },
  "before": { "enabled": true },
  "after": { "enabled": false },
  "undo": ["controld_manager__set_filter_state(...)"],
  "warnings": []
}
```

The envelope is **synthesized, never wrapped**. Control D write responses are not
uniform — a filter write returns a map of every filter, a service or rule write a
list, an option write a list, and a rule delete an empty body — so wrapping would
hand back a different shape per tool. The write response is used only as
confirmation that the call succeeded; `target` is built from what the tool
resolved, because a rule write does not echo which rule it changed.

`status` values: `applied`, `already_in_state`, `failed`. A rejected write
returns `status: "failed"` with `error` set rather than raising.

**`already_in_state`** is decided by reading the runtime registry before writing:
if every addressed target is already in the requested state, the service is not
called at all and `changed` is `false`. Tools may read the registry for exactly
this purpose (see the LLM tool layer rules in `ARCHITECTURE.md`); all writes still
go through services. When the state cannot be read, the write proceeds rather than
being skipped, and the result carries a warning (see below) because the comparison
that supports `changed` and `undo` could not be made.

- `status` — `applied` | `already_in_state` | `failed`.
- `changed` — whether anything actually changed. When the prior state could not
  be read this reports that the action was **sent**, not that the value differs,
  and the result says so in `warnings`.
- `target` — the **resolved** object acted on (id + name).
- `before` / `after` — `before` is the state observed before the action; `after`
  is the state the action **requested**, not a fresh reading.
- `undo` — the calls that reverse the action, as a **list**, or `null`. It is a
  list because the tools accept lists of targets: restoring three services with
  three different previous modes takes three calls. Each entry may name a tool
  from a higher tier than the caller has enabled; the tool then states that the
  configured tier does not permit it. The undo restores the value read **before**
  the write, so it is `null` for `already_in_state` (nothing changed) and for the
  tools that cannot read their own previous value.
- `warnings` — degradations or side effects. A write whose prior state could not
  be read returns one warning saying so, so `changed` and a missing `undo` are
  never mistaken for a confirmed account of what happened.

`already_in_state` applies to **idempotent** tools only. `create_rule` is not
idempotent and can never report it.

Both shapes are strictly JSON-serializable (no datetimes or sets).

### Annotations

Every tool declares all four MCP annotations: `read_only`, `destructive`,
`idempotent`, `open_world`. Read tools declare `read_only=True, destructive=False`
explicitly, because the annotation defaults are the least safe case. `create_rule`
declares `idempotent=False`.

### Analytics surfaces

Two surfaces with different retention and dimensions:

| Surface | Shape | Retention | Dimensions |
| --- | --- | --- | --- |
| **Activity log** | per-record DNS queries | ~33 days | all (incl. destination) |
| **Statistics** | pre-aggregated counts | up to ~1 year | source-side only |

Retention is a user setting and these are **maximums**; a deployment may have less
or logging may be off. An empty activity result can mean no traffic, an expired
window, or logging disabled — the response cannot distinguish them.

### Truncation

A capped result is never presented as complete. Ranked tools report
`meta.truncated`; paged tools report `meta.has_more`. Neither surface provides a
total, so a total is never claimed.

### Comparison and cost

There is no caching layer. Affordability comes from scope, limits, and filters. A
typical activity-log page is roughly 47 KB per 100 records, so read tools default
to a narrow window and a small limit, and callers narrow further.

---

## Tool catalog

Tools are grouped to match how a person actually asks. Within each group, reads
come before controls.

### Group 1 — Orientation

| Tool | Answers |
| --- | --- |
| `get_account_overview` | "How many profiles/endpoints/clients? Is anything being blocked?" |

#### `controld_manager__get_account_overview`

- **Answers** — "What is the overall state of my account, and is anything being blocked?"
- **When to use** — first, to size the account and see which profile is doing what.
- **When not to use** — for per-query detail (use `get_activity_log`).
- **Inputs** — none. The tool binds to its own config entry.
- **Returns** — `result.account` with `region`, `status`, `profile_count`,
  `endpoint_count`, `discovered_endpoint_count`, `router_client_count`, and an
  `analytics` block (`total_queries`, `blocked_queries`, `bypassed_queries`,
  `redirected_queries`, `blocked_queries_ratio`, `window_start`, `window_end`),
  plus `result.profiles[]` with `profile_id`, `profile_name`, `endpoint_count`,
  `paused`, and blocked/bypassed/redirected counts.
- **`status` is Control D's 0/1 account flag**, not a free-form code: `1`
  enabled, `0` disabled. It is the same enablement integer the API uses for
  filters, services, options, and restrictions (`PUT`/`DELETE` on a restriction
  is documented as equivalent to `status=0`). The vendor defines no richer code
  set for accounts, and both values are integers upstream, so it is exposed as an
  integer rather than a label. Note the dashboard's device *Status* setting
  (Pending / Active / Soft Disabled / Hard Disabled) is a different, UI-level
  concept and does not apply to this field.
- **Counts never diverge from the entities.** Every count comes from the same
  `ControlDRegistry` accessors the account and profile entities read, so the tool
  and the sensors always agree. `endpoint_count` is the protected count
  (`discovered + router clients`), not the raw `/devices` row count.
- **The per-profile `endpoint_count` rows do not sum to the account total.** An
  endpoint attached to more than one profile (Control D's `profile` plus
  `profile2`) is counted under each attachment, so the rows intentionally total
  more than `account.endpoint_count`. Both figures are correct; the account one
  is the count of distinct protected endpoints. Callers must quote the account
  figure rather than adding the rows up.
- **Availability** — every enabled tier, including Summary.
- **Reversibility** — read-only; `undo` is `null`.
- **Annotations** — `read_only=True`, `destructive=False`, `idempotent=True`,
  `open_world=False`.

### Group 2 — Inventory and topology *(planned: Phase 2)*

| Tool | Answers |
| --- | --- |
| `get_inventory` *(planned)* | "What are my profiles, endpoints, and clients, and what is assigned to what?" |

### Group 3 — Troubleshooting and activity *(planned: Phase 2)*

| Tool | Answers |
| --- | --- |
| `get_activity_log` *(planned)* | "What happened, and why was this blocked?" |
| `test_domain` *(planned)* | "Would this endpoint block this domain, and by what?" |

### Group 4 — Block analytics

**Not exposed.** Aggregate block/bypass/redirect counts come from
`get_account_overview`, and per-record cause comes from `get_activity_log`.
Control D's ranked breakdown endpoints (`statistic/count/question`,
`statistic/count/triggerValue`, `statistic/count/srcCountry`) take only
`profileId`, `endpointId[]`, `action`, and `limit`. A capped ranking cannot be
narrowed further or paged, so it returns a slice rather than a complete answer.
Forcing everything through `get_activity_log`, which has the full filter set, is
strictly better than exposing a surface that cannot be drilled into.

### Group 5 — Configuration reads *(planned: Phase 2)*

| Tool | Answers |
| --- | --- |
| `get_catalog` *(planned)* | "What filters, services, options, rules, and default rules exist, and what state are they in?" |

`get_catalog` returns **state**, not just availability: filters carry `enabled`,
`supports_modes`, and `current_mode`; services carry `current_mode`; rules carry
`action`, `enabled`, `comment`, and `group`; profile options carry
`current_value`. There is deliberately **no separate policy tool**, because it
would be a re-skin of this one.

### Group 6 — Control

Reversible or additive actions, registered in the **Read and control** and **Full**
tiers:

| Tool | Effect |
| --- | --- |
| `set_filter_state` | Enable or disable a blocklist filter on a profile |
| `set_service_state` | Set a service to blocked, bypassed, or redirected |
| `set_option_state` | Enable, disable, or set a profile option |
| `set_rule_state` | Enable, disable, or modify one custom rule |
| `set_default_rule_state` | Set a profile's catch-all action |
| `enable_profile` / `disable_profile` | Control D's own pause, reversible (disable can be timed) |
| `rename_endpoint` | Rename an endpoint (cosmetic, endpoint-scoped) |
| `set_endpoint_analytics_logging` | Set an endpoint's logging to None, Some, or Full |
| `set_client_alias` | Label one client under an endpoint (cosmetic, client-scoped) |
| `clear_client_alias` | Remove a client's alias |
| `create_rule` | Create a custom rule — **not idempotent**; undo is `delete_rule` |

### Destructive *(Full tier only)*

| Tool | Effect |
| --- | --- |
| `delete_rule` | Permanently delete a custom rule. No undo; prefer `set_rule_state` with `enabled: false` |

## Endpoint identity

Endpoint-scoped services accept **`endpoint_id`** (from `get_inventory`) and
`endpoint_name`. Ids take precedence, because an id is an exact, unique key while
endpoint names are not guaranteed to be unique. Prefer the id for any write; use
the name only when a human is choosing interactively.

## Not yet exposed

Endpoint-to-profile assignment is deferred: changing which policy governs a whole
segment has the widest blast radius of anything in this integration, and it needs
firm multi-profile precedence handling before a model may call it.

---

## Per-tool template

Every tool documented below uses this exact shape, in this order:

- **Name** — `controld_manager__<name>`
- **Answers** — the user question it responds to (one line)
- **When to use / not to use** — disambiguation from its nearest sibling
- **Inputs** — flat, each with type, `description`, and valid values
- **Returns** — the envelope or action-result shape
- **Availability & tier**
- **Reversibility & undo** — for controls
- **Annotations** — the four flags

## Gotchas the tool schemas must encode

- `statusCode`, **not** `rcode` (`rcode` is silently ignored).
- `clientId` requires a co-present `endpointId`.
- Activity Log `pageSize` max is 500; deep pages return older records.
- Activity Log retains ~33 days; statistics up to ~1 year; both are user-settable.
- `endpointName` comes back empty on activity records — resolve names from the
  inventory.
- Destination filters (`dstCountry`, `dstIsp`, `dstAsn`) exist on the Activity Log
  only.
- Never sum ranked rows for a total; never round-trip a display label back as a
  query input.
- DNS verdict: HTTP 200 with `RCODE 5` means **blocked**; empty `verdict` means
  **no policy matched**. Neither is an error.
- Analytics maintenance returns `503` code `50303`.
