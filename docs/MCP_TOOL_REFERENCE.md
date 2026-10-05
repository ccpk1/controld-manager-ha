# Control D Manager — MCP Tool Reference

The authoritative reference for the tools this integration exposes to LLMs and MCP
clients (via Home Assistant's `mcp_server`).

- **Audience:** LLM/MCP tool authors, agent developers, and anyone wiring a client
  to this integration. Users of the Home Assistant UI or service calls should read
  [`USER_GUIDE.md`](USER_GUIDE.md) instead.
- **Scope:** every tool, as shipped — **24 in total**: 5 read, 16 control, and 3
  destructive. Nothing here is aspirational; if a tool is listed, it is registered
  and tested.
- **Status:** complete for the current initiative. The decision history behind each
  contract, including the ones that were corrected, is in
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
- A device can therefore be **both**. A client that became its own endpoint is
  listed as an endpoint with its own `device_id` and as a client under its
  original parent, where `is_standalone_endpoint: true` and `own_endpoint_id`
  mark it, and `parent_client_id` records the client identity it had. Its
  `client_id` is still what aliases it.
- Never call an endpoint a device or a client, and never call a client an
  endpoint.

### Client identity

Endpoints have **no MAC address**; clients do. A client is identified by its
`client_id`, and that is the identifier the alias API keys on. Two clients under
one endpoint routinely share a MAC address *and* an IP while differing by
`client_id` — a phone and a tablet behind one router segment, for example — so a
MAC selector can be ambiguous where a client id never is.

`endpoint_mac` is therefore a convenience selector naming the *client's* MAC,
not the endpoint's, and is the wrong name for what it does. Prefer `client_id` on
`set_client_alias` and `clear_client_alias`, and check the `client_id` a control
result reports when the account has duplicates.

### Choosing a client row

Client rows are never cleaned up, so a parent endpoint with a long history
carries rows for devices that no longer exist. Two fields say whether a row is
attributable to a real device, and they are **independent** of each other:

- `last_active` — when Control D last saw that client. Recent means live.
- `mac_address` — blank or `00:00:00:00:00:00` on some rows.

A blank MAC is expected rather than broken, and it does **not** indicate a stale
row. Measured on this account, 58 of 397 client rows carry a blank or all-zeros
MAC, and their median age (40 days) is the same as the rows with a valid MAC (41
days) — 10 of the 58 were active within the previous week. The rows behind those
blank MACs are identifiable devices with hostnames and IPs, not leftovers:
`nvidia-shield`, `echo-payton`, `metaquest3`, `metaquest2`, `echo-basement`,
`echo-bonusroom`, `fire-tablet-hd10-office`, and the router itself appear this
way. When ctrld runs on the router, some relayed traffic reaches Control D
without a MAC to record, which is what produces them.

Recency and MAC validity are independent, so neither one implies the other.
Prefer a row that satisfies both, but do not discard a recency-bearing row just
because its MAC is blank.

This affects which row to pick, not whether a write can succeed — the alias API
keys on `client_id` and never needs a MAC. A blank-MAC client is still aliasable;
the MAC only helps a human recognise which device the row belongs to.

### A client row is an observation, not configuration

This is the single most important thing to know before proposing to tidy client
rows, and it decides whether cleanup is worth doing at all.

A client row exists because Control D has *seen* that client's traffic. It is not
something an account configures, so deleting one is **not durable**: if the same
client identity is seen again, the row is re-created. Only two things about a
client outlive its traffic:

- an **alias**, which is stored and survives until cleared, and
- a **policy assignment**, which promotes the client to an endpoint.

Everything else — the row itself, its hostname, its IP, its MAC, and its recorded
history — is derived from traffic. So for an ordinary client, deleting the row
only clears history and the row returns the next time the device is online. A
delete is effectively permanent only for an identity that will not be seen again.

That carve-out is real, though, and it has a common cause on this account.

### Private MAC rotation manufactures client rows

A device using a rotating private MAC arrives under a **new** MAC each time it
connects, so it cannot be recognised as a repeat client and each connection
creates its own row. Apple Watches here do exactly this: 29 rows under one parent
endpoint share the hostname `watch` and have **29 distinct MACs** — one row per
rotation, median age 69 days, 6 active within the last 30 days. This is routine
churn rather than corruption, and it is the main reason a parent endpoint
accumulates a long tail of rows.

Because the rotated MAC is never reused, deleting those rows *is* durable —
unlike deleting an ordinary client. But it does not stop the churn: the next
connection simply adds a fresh row. Cleanup is therefore a recurring chore rather
than a fix, and it is worth saying so rather than presenting a one-off sweep as a
solution.

### A device can be a client and an endpoint at once

The two views are not in conflict, and it helps to be explicit about why, because
seeing one device in both places invites the conclusion that one of them is
wrong.

Take `chads-phone`. It is listed as an endpoint with its own `device_id`, and it
is simultaneously a client under `Firewalla-VLAN60`:

```
device_id      = 22pad6pj5t        (the endpoint row)
profile        = Chads Phone
profile2       = 7580 Default Profile
parent_device  = {device_id: 461wtt4eyr, client_id: 65a84a0daca5}
```

Both are correct, because they answer different questions about the same physical
device. The **client** view comes from observed traffic and is where aliases live.
The **endpoint** view is the stored configuration — the profile assignment that
grants it its own policy — and is where policy is set. Assigning a profile does
not remove the client row, which is why a device with a profile still appears
under its parent and still shows as a client with a profile assigned.

In tool terms: alias it through the client identity, and change its policy
through the endpoint. `is_standalone_endpoint`, `own_endpoint_id`, and
`parent_client_id` are what connect the two.

### Deleting clients

`delete_client` removes client rows, individually or in bulk, through
`DELETE /v2/client` on the analytics host, taking the parent endpoint id and a
list of client ids. It is registered **only in the Full tier**, because there is
no undo.

Keep the families apart, because the neighbouring names invite a mistake:
`clear_client_alias` removes a client's alias and leaves the client in place, and
`delete_service` and `delete_rule` remove profile configuration rather than
anything about a device. Only `delete_client` removes the observed client row
itself, and it purges that client's stored query history by default.

It is a **history-hygiene tool, not a device-retirement one**, and saying so is
part of using it honestly. For an ordinary client the deletion is **not durable**:
the row reappears the next time that client is seen. Only an alias or a policy
assignment outlives the traffic, and this tool changes neither. An identity that
will never recur — a rotated private MAC — is the case where the removal actually
sticks. So an age-based or blank-MAC-based sweep clears history rather than
retiring devices, and on a network with rotating private MACs the churn continues
afterwards.

Because a convenience selector can match more than intended, resolve the set with
`get_inventory` first and prefer `client_id`. A MAC may match several clients, and
a hostname such as `watch` can match a long list produced by repeated private-MAC
rotations. The result reports the number of rows the API confirmed it removed,
which can be fewer than the number requested. Set `delete_history: false` to
remove only the rows and keep their history.

### Endpoint write limitations

Endpoint creation and deletion are now exposed as `create_endpoint` and
`delete_endpoint`.

Every endpoint row also reports the dashboard's **Advanced Settings** as
`advanced`, with the labels the dashboard uses: `description`, `icon`,
`authorize_by_secure_dns`, `require_authorized_ips`, and `legacy_dns`,
`authorize_by_dynamic_dns`, `expose_ip_via_dns` and `prevent_deactivation` as
`{enabled, ...}` objects. None of these is enabled on this account, so the block
reads as all-false.

**These are reported, not controlled**, with one exception: `set_endpoint_description`
sets and clears `description`, because a note on an endpoint is genuinely useful.
The remaining Advanced Settings writes are deliberately not exposed — the write
keys are captured and recorded in `docs/ENGINEERING_FINDINGS.md` if they are ever
needed.

Two details a reader should know:

- An absent field in the API means the feature is off, not unknown: Control D
  omits `legacy_ipv4`, `ddns`, and `ddns_ext` entirely when unset, so the rows
  derive enablement from whether the field is there at all.
- `prevent_deactivation.enabled` reports only **whether** a PIN is set. The PIN
  itself is a credential and is never read back.

### Creating and deleting endpoints

`create_endpoint` requires a profile, because an endpoint always enforces exactly
one. The name must be unique across the account, and Control D assigns the
`device_id`, so it only exists after the call — which is why the tool's `undo`
names the reverse by endpoint **name** rather than by id. This is the one place a
name is a safe selector here.

`delete_endpoint` is irreversible and belongs to the destructive tier. Deleting an
endpoint removes the resolver itself along with the records kept against it, so
whatever resolved through it stops being filtered. Deleting a router endpoint is
the extreme case: it enforces a profile for a whole network segment, so every
device behind it loses that policy at once. A newly created endpoint is **Pending**
— `status: 0`, no activity — until it first sends queries; that is the dashboard's
own label for the state, and it is not a disabled endpoint.

### Only two things here were ever "unavailable", and neither was a real limit

Worth recording because both were mistakes of mine, and the same one twice:

- **Primary and secondary profile assignment works.** The write keys are
  **`profile_id` and `profile_id2`** — note the suffix — while the *read* keys are
  `profile` and `profile2`. Setting `profile_id2` to a profile PK attaches the
  secondary profile, and setting it to the integer `-1` clears it. I had probed
  `profile2` as a write key, which is the read name, and concluded the write was
  unsupported.
- Why the mistake was possible: **`PUT /devices/{device_id}` returns `200 ok` for
  keys it does not act on.** A wrong key name is indistinguishable from a
  successful write by status code alone. The fields it does honour — `name`,
  `stats`, `desc`, `status`, `learn_ip`, `restricted` — each reject a bad value,
  so a validated field gives a real error and an unknown one gives silence.

The lesson, and the rule this documentation now follows: **a `200` with no
observed change is not evidence that a capability is missing — it is evidence that
the request was wrong.** Everything the Control D web client does is done through
its backend API; some of it is simply not in the published reference. Capture the
real request from the browser rather than inferring a limit, and never write
"not possible through the API" on the strength of a failed guess.

Also note `status` is **not** a disabled flag. Two endpoints here report `status:
0`, and both are simply unseen — one is a new endpoint that was just created,
neither has a `last_activity` field, both have `ip_count: 0` and no clients. A
`0` therefore means "no activity observed yet" and clears on its own once traffic
flows; it needs no re-enabling.

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

`already_in_state` applies to **idempotent** tools only. `create_rule` and the
three deletes are not idempotent and can never report it.

Both shapes are strictly JSON-serializable (no datetimes or sets).

### Annotations

Every tool declares all four MCP annotations: `read_only`, `destructive`,
`idempotent`, `open_world`. Read tools declare `read_only=True, destructive=False`
explicitly, because the annotation defaults are the least safe case.

`open_world` is `True` for every tool, because all of them call the Control D
cloud API rather than reading local state. Home Assistant's own platform tools
are all `open_world=False` for that reason, so the value cannot be copied from
them.

`create_rule` declares `idempotent=False` — creating the same rule twice creates
two rules — and so do the three irreversible deletes, following Home Assistant's
convention for removals.

Home Assistant never reads these annotations itself; the MCP Server integration
forwards them to MCP clients as tool hints. Nothing on the Assist path acts on
them.

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
  `open_world=True`.

### Group 2 — Inventory and topology

| Tool | Answers |
| --- | --- |
| `get_inventory` | "What are my profiles, endpoints, and clients, and what is assigned to what?" |

### Group 3 — Troubleshooting and activity

| Tool | Answers |
| --- | --- |
| `get_activity_log` | "What happened, and why was this blocked?" |
| `test_domain` | "Would this endpoint block this domain, and by what?" |

### Group 4 — Block analytics

**Not exposed.** Aggregate block/bypass/redirect counts come from
`get_account_overview`, and per-record cause comes from `get_activity_log`.
Control D's ranked breakdown endpoints (`statistic/count/question`,
`statistic/count/triggerValue`, `statistic/count/srcCountry`) take only
`profileId`, `endpointId[]`, `action`, and `limit`. A capped ranking cannot be
narrowed further or paged, so it returns a slice rather than a complete answer.
Forcing everything through `get_activity_log`, which has the full filter set, is
strictly better than exposing a surface that cannot be drilled into.

### Group 5 — Configuration reads

| Tool | Answers |
| --- | --- |
| `get_catalog` | "What filters, services, options, rules, and default rules exist, and what state are they in?" |

`get_catalog` returns **state**, not just availability: filters carry `enabled`,
`supports_modes`, and `current_mode`; services carry `current_mode`; rules carry
`action`, `enabled`, `comment`, and `group`; profile options carry
`current_value`. There is deliberately **no separate policy tool**, because it
would be a re-skin of this one.

`catalog_type: 'redirect_locations'` is the one type that is **not**
profile-scoped: it returns the account's **107** usable redirect destinations,
each with the 3-letter code a redirect takes (`PK`) plus its city and country,
so a `redirect_target` is chosen rather than guessed. Codes look like `LHR`
(London), `JFK` (New York), and `RES_ORD` (Residential Chicago). Verified
end-to-end: a rule created with `redirect_target: 'LHR'` resolved to `action:
3` with a London-range answer.

`search` filters a catalog down to the rows whose own names and ids contain the
string, case-insensitively. It exists because the service catalog carries over a
thousand rows while `limit` caps at 500 and there is no paging, so a named entry
would otherwise be unreachable: `search='apple'` finds the Apple service in one
call where listing never would. `item_count` reports the filtered total, and the
profile columns are deliberately excluded from matching so that searching for a
service cannot select every row through a profile name.

**Diagnosing a block.** The activity record names its own cause, so the path is:
widen the window (traffic is often older than the default hour), set
`query_action` to `blocked`, read `trigger` and `triggerValue`, then resolve what
they name with `get_catalog` (`filters`, `services`, or `rules`) and change it
with the matching tool. `profileId` on the record says which profile produced the
verdict, which is what matters when one endpoint enforces two profiles.

**Client note:** a new enumerated value will be rejected by an editor client
until its cached tool schema refreshes, and only a **window reload** does that
— reloading the integration or the MCP server does not. If a value the server
logs as registered is rejected as invalid, reload the window before suspecting
the integration.

### Group 6 — Control

Reversible or additive actions, registered in the **Read and control** and **Full**
tiers:

| Tool | Effect |
| --- | --- |
| `set_filter_state` | Enable or disable a blocklist filter on a profile |
| `set_service_state` | Set a service to blocked, bypassed, or redirected |
| `delete_service` | Remove a configured service from a profile — reversible by re-adding it |
| `set_option_state` | Enable, disable, or set a profile option |
| `set_rule_state` | Enable, disable, or modify one custom rule |
| `set_default_rule_state` | Set a profile's catch-all action |
| `enable_profile` / `disable_profile` | Control D's own pause, reversible (disable can be timed) |
| `rename_endpoint` | Rename an endpoint (cosmetic, endpoint-scoped) |
| `set_endpoint_description` | Set or clear the note an endpoint carries |
| `set_endpoint_profile` | Attach the primary profile an endpoint enforces, and optionally a second |
| `create_endpoint` | Create an endpoint enforcing a profile. Name must be unique; undo deletes it by name |
| `set_endpoint_analytics_logging` | Set an endpoint's logging to None, Some, or Full |
| `set_client_alias` | Label one client under an endpoint (cosmetic, client-scoped; select by `client_id`) |
| `clear_client_alias` | Remove a client's alias (select by `client_id`) |
| `create_rule` | Create a custom rule — **not idempotent**; undo is `delete_rule` |

### Destructive *(Full tier only)*

| Tool | Effect |
| --- | --- |
| `delete_rule` | Permanently delete a custom rule. No undo; prefer `set_rule_state` with `enabled: false` |
| `delete_client` | Permanently delete client rows and, by default, their query history. No undo; not durable for an ordinary client |
| `delete_endpoint` | Permanently delete an endpoint, its resolver, and its records. No undo |

## Endpoint identity

Endpoint-scoped services accept **`endpoint_id`** (from `get_inventory`) and
`endpoint_name`. Ids take precedence, because an id is an exact, unique key while
endpoint names are not guaranteed to be unique. Prefer the id for any write; use
the name only when a human is choosing interactively.

`create_endpoint` is the one exception in the other direction: the new endpoint's
id does not exist until the call returns, so the undo that reverses a create must
address it by name. That is safe precisely because the API enforces name
uniqueness.

### What an endpoint row carries

`get_inventory` endpoint rows report:

| Field | Meaning |
| --- | --- |
| `device_id`, `name`, `role`, `is_endpoint` | Identity and that this row is an endpoint |
| `owning_profile_id`, `owning_profile_name` | The **primary** enforced profile |
| `secondary_profile_id`, `secondary_profile_name` | The **second** enforced profile, when one is attached |
| `attached_profiles` | Every attached profile, with names |
| `associated_client_count` | Clients attributed to this endpoint |
| `parent_device_id`, `parent_client_id` | Set when the device is also a client under another endpoint |
| `last_active` | When the endpoint was last seen. **Absent** when it has never been seen |
| `advanced` | The dashboard's Advanced Settings; see above |

Two profiles are common here: 11 of 20 endpoints on the account that motivated
this integration enforce a primary *and* a secondary, so a caller reading only
`owning_profile_id` sees half the picture.

## Not yet exposed

Captured and documented, deliberately not built:

- **The remaining Advanced Settings writes** — Legacy DNS, Authorize by Dynamic
  DNS, Expose IP via DNS, Require Authorized IPs, and Prevent Deactivation. The
  read side is reported; the write keys and clear sentinels are recorded in
  `docs/ENGINEERING_FINDINGS.md` if they are ever wanted.
- **Endpoint `status`** (`1` Active, `2` Soft disabled, `3` Hard disabled,
  `0` Pending). Forceable, but not exposed.
- **`get_account_overview`-adjacent redirect locations** — `GET /proxies` lists the
  locations a redirect may target. Without it a caller must know a region code.

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
- Activity Log `pageSize` max is 500; deep pages return older records, and a page
  is **not** the whole window — check `has_more`.
- Activity Log retains ~33 days; statistics up to ~1 year; both are user-settable.
- `endpointName` arrives **empty** from the vendor on activity records and is
  filled in from the inventory we already hold, so it is populated for an endpoint
  we currently know and empty for one we no longer hold. `endpointId` is always
  present and is the field to act on.
- Activity record `action` codes are **not contiguous and one is negative**:
  `-1` failed, `0` blocked, `1` bypassed, `3` redirected. Read `action_label`
  instead of comparing `action` to a number.
- A record's `triggerValue` is **absent** whenever there is no list or object to
  name, which is the normal case for a `default` trigger. Its absence is the
  answer, not missing data. `trigger` itself is absent only on a failed lookup.
- `get_catalog` has **no paging** — only `limit`, capped at 500 — while the
  service catalog runs past a thousand rows, so `search` is what makes a named
  entry reachable. `search` matches a row's own names and ids, never its profile
  columns.
- Never sum ranked rows for a total; never round-trip a display label back as a
  query input.
- DNS verdict: HTTP 200 with `RCODE 5` means **blocked**; empty `verdict` means
  **no policy matched**. Neither is an error.
- Analytics maintenance returns `503` code `50303`.
