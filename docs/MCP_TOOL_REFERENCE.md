# Control D Manager — MCP Tool Reference

The authoritative reference for the tools this integration exposes to LLMs and MCP
clients (via Home Assistant's `mcp_server`).

- **Audience:** LLM/MCP tool authors, agent developers, and anyone wiring a client
  to this integration. Users of the Home Assistant UI or service calls should read
  [`USER_GUIDE.md`](USER_GUIDE.md) instead.
- **Scope:** every tool, as shipped — **24 in total**: 5 read, 16 control, and 3
  destructive. Nothing here is aspirational; if a tool is listed, it is registered
  and tested.
- **Status:** complete for the current initiative, released as `2.0.0-beta.2`. The decision history behind each
  contract, including the ones that were corrected, is in
  `plans/completed/CONTROLD_MANAGER_LLM_TOOLS_COMPLETED.md`.
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

The words are not interchangeable. A **profile** is a policy container. An
**endpoint** is a DNS resolver that enforces a profile: a protected row from
`/devices`, whether a router segment, a ctrld instance, or an individually
protected device. **An endpoint always enforces at least one profile**, so its
primary is never empty and only its secondary can be removed. A **client** is a
device seen under an endpoint. Home Assistant devices are containers only.

These definitions come from the repository lexicon in `ARCHITECTURE.md` and
`DEVELOPMENT_STANDARDS.md`.

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

### The system model

One canonical piece of text explains what this surface is and what is true
across all of its tools: the vocabulary, where identifiers come from, how to read
a write result, and how to report what is not exposed. It is served two ways:

- As the API prompt, which Assist appends to the system prompt on every turn.
- As `result.system_model` on `get_account_overview`, so a client that only ever
  sees tool results can still obtain it.

The second path exists because MCP's `prompts` primitive is **user-controlled**:
a client shows a prompt for explicit invocation rather than injecting it, and
the clients in common use send `tools/list` and nothing more. Relying on it would
exclude the majority of clients, so the model travels inside a tool result.

This is the one place the two paths deliberately carry identical text. The cost
is that Assist holds it twice; the alternative was two texts that drift.

### How guidance reaches a client

The model is not the only text a client sees, and it cannot be. Neither delivery
path is universal:

| Path | Assist | Any other MCP client |
| --- | --- | --- |
| API prompt | yes, every turn | **no** — Home Assistant's MCP server leaves `InitializeResult.instructions` empty, and its MCP client ignores the field |
| `result.system_model` | yes | **only if the agent calls `get_account_overview`** |
| Tool descriptions | yes | **yes, on `tools/list`** |

So an agent that sends `tools/list` and goes directly to a write tool would
otherwise know nothing about what a profile, endpoint, or client is. **Tool
descriptions are the only channel every client is guaranteed to receive**, which
makes them the one place a rule that must not be missed can live.

Text is therefore layered, and no two layers say the same thing:

| Layer | Scope | Examples |
| --- | --- | --- |
| **System model** | true across all 24 tools | the vocabulary, identifier provenance, the action-result fields, `undo`, the `200 ok` trap, tier gating, retention |
| **Family injection** | true across one family, and absent from the model | read: a capped result is not complete. delete: there is no undo, prefer a reversible alternative |
| **Description body** | true of one tool | its arguments, its enums, its own failure modes |

#### The injection block

Every description is composed as `injection + body` at construction time, from an
`_injection` class attribute on the tool's base class. The three destructive
tools override it. A tool cannot be registered without a block.

All three blocks open with the same **orientation question**:

> **If you cannot clearly explain what a Control D profile, endpoint, and client
> are, and what the account's counts mean, call `get_account_overview` once** —
> it returns the system model that defines them, …

Three properties of that sentence are deliberate:

- **It asks a question the model can answer**, rather than instructing it to be
  careful. "Confirm you understand the vocabulary" is not actionable; "can you
  explain what a profile, endpoint, and client are?" is checkable.
- **It names a concrete remedy**, so the instruction can be followed in one call.
- **It bounds itself** — once per session, or only if a result stops making
  sense — so it does not prompt a call before every read.

The control and delete variants bind it *before writing* rather than leaving it
idle. A wrong write changes a live network; a wrong read does not. The delete
variant then adds what the model cannot say because it is not true of every tool:
that this family has no undo, and to prefer a reversible alternative.

**Control adds nothing beyond orientation.** That is a considered result, not an
omission: every control-wide rule it could carry — read state before writing,
confirm wide-reaching changes, writes return an `undo` — is already in the system
model, and repeating it would mean paying for the same sentence sixteen times.
Read and delete each carry one rule the model genuinely lacks.

A rule that belongs to two tools rather than a whole family goes in those two
bodies. `'Off'` is not removal is the worked example: it is stated on
`set_service_state` and `delete_service`, because it is meaningless to the other
fourteen controls and would be dead weight on all sixteen.

#### Writing a description for a machine, not a reader

A description is not prose about a tool; it is the argument and result contract.
It is written as field → meaning:

| Written for a reader | Written for a machine |
| --- | --- |
| "Resolve the filter first with `get_catalog` (`catalog_type 'filters'`), which returns each filter's id, name, and current enabled state." | "`filter_id` / `filter_name` — from `get_catalog`, `catalog_type: 'filters'`." |
| "This is reversible — set the previous value back, or use the `undo` field." | *(deleted — the model defines `undo`)* |
| "Use it to stop a category from being blocked, or to start blocking one that is currently off." | *(deleted — the `enabled` argument states the effect)* |

Two kinds of sentence come out in that pass. **Justification clauses** explain why
a rule exists; they cost tokens on every request and change no behaviour.
**Restatements** repeat what the model or the argument list already says. Both are
removed, and what remains is the set of facts a caller cannot get from anywhere
else.

The pass is not cosmetic. Applied across the read tools it cut 9,995 characters to
6,783 (−32%) *while adding* the injection to all five, and the same register for
control cut 16,211 to 9,971 (−38.5%). It also removes the failure it looks like it
might cause: a description that states an enum with the wrong case, or paraphrases
it, sends the model to a value the schema rejects.

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

- `last_active` — when Control D last saw that client. Recent means live. For a
  client that has become a standalone endpoint this is the **endpoint's** last
  activity, since that is where its traffic is attributed once promoted.
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

**A promoted client reports its endpoint's recency.** When a client is made its
own standalone endpoint, Control D attributes that client's traffic to the
endpoint from then on and stops updating the analytics client row. The row's own
timestamp therefore freezes on the day of promotion, so `last_active` is read
from the endpoint instead whenever there is one. Without that join every
promoted client looks dormant: on the account this was diagnosed against, **all
six** standalone endpoints reported 146 to 174 days ago while their endpoints
reported activity minutes earlier, for phones in daily use. A client with no
endpoint of its own has only the analytics timestamp, and uses it.

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

**A client may add its own prefix to that name.** A client presenting an MCP tool
to its model commonly renames it to `mcp_<server>_<tool name>`, which shares a
64-character budget with the server name the user chose. `Home Assistant`'s MCP
server passes names through untouched, so this is a client-side constraint, not
one the integration enforces or can see. Where a client does enforce it, a tool
whose name does not fit is dropped from the list entirely — which reads as a
missing tool rather than a long name.

`set_endpoint_analytics_logging` is the longest action here and sits closest to
that budget. It is left as-is, because it mirrors its service name and other
clients are unaffected. A deployment using a client with such a limit and a long
server name may find it unavailable; shortening the server name restores it.

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
- `before` — the state observed before the action, as `{"targets": [...]}` with
  one **named** row per addressed object. Every tool that reports per-target
  state uses this one container, and each row carries the id it belongs to, so
  nothing is matched by position. The two deletes report what they are about to
  destroy rather than a prior *state* — a name, profiles, and client count for an
  endpoint; the id, action, and comment for a rule — because that information
  cannot be recovered once the row is gone. `delete_client` is the other
  deliberate exception: it reports a *summary* of what is about to be destroyed
  (`{client_count, clients, delete_history}`), because the question it answers
  there is "how much history goes with this", not "what was each value".
- `after` — the state the action **requested**, flat and identical for every
  addressed target, so it is not repeated per row. It takes this shape on every
  status, including `already_in_state`; compare it against each
  `before.targets[]` entry.
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

#### A field with a service default declares that default

`after` is the field the system model tells a caller to trust, so a `null` there
for a value the service did apply is a false report. The tool cannot supply the
vendor's default on its own — it only sees the caller's arguments — so an
optional field whose absence still has a definite effect declares the default in
its schema:

| Field | Declared default | Without it |
| --- | --- | --- |
| `create_rule.mode` | `block` | `after: {"mode": null}` while the rule blocks |
| `create_endpoint.mode` | `None` | `after` reports three nulls for values the API chose |
| `disable_profile.minutes` | `15` | the undo cannot name when it re-enables |

The tool's hooks receive **schema-validated** arguments, so a declared default
reaches `before`, `after`, and `undo` without any other change. This is enforced
by `test_optional_fields_with_a_service_default_are_declared`.

The same echo is why a tool whose target is not simply its arguments overrides
`_target`: the base implementation returns every non-null argument, which is
correct until an optional argument carries a default, and then the default is
reported as though it were part of what the call addressed.

#### A write is not immediately visible to a read

Writes invalidate refresh groups that are re-polled on their own cycles, so a
newly created object can be absent from a read for a short window after a
successful write — and a read scoped by *name* can fail to resolve it, because
resolution is against the inventory that has not caught up yet.

A create returning `applied` is the authoritative signal that the object exists.
Absence from an immediately following read is not evidence the create failed, and
a caller should not report one as the other. Address an object by **id** wherever
the id is known, which is unaffected by the lag.

#### An id wins outright; it is not unioned with a name

Both the tool layer and the backing services accept an id or a display name for
the same object. When a caller supplies **both**, the services resolve the id
group and never consult the names — and the tool layer now resolves the same way,
so the two agree on the target set.

This matters because `before`, `after`, and `undo` are built from the tool's
resolution. Treating the two selectors as a union made the result name every row
either selector matched, while the write reached only the ids: a caller would be
told two filters were enabled and handed an undo that disables two, of which one
was never touched.

Supplying only a name still works. Supplying both means the name is ignored, so
pass one or the other rather than both as a belt-and-braces measure.

#### A select option is cleared with `enabled: false`, not `value: 'Off'`

A dropdown option with no current value is reported by the catalog as
`current_value: "Off"`, and `'Off'` is also listed among the option's selectable
values. It is **not**, however, a valid `value` argument: upstream it means *no
value*, which is indistinguishable from an unrecognised one, so the service
rejects the literal string with *"The selected Control D option value is not
supported"*.

Clearing such an option is `enabled: false` with no `value`. That is also what
the `undo` emits for a dropdown that was previously unset, so an undo is never a
call that would fail when used.

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
- **Returns** — `result.system_model` (the cross-cutting model, identical to the
  API prompt), `result.account` with `region`, `status`, `profile_count`,
  `endpoint_count`, `client_count`, `protected_device_count`, and an `analytics`
  block (`total_queries`, `blocked_queries`, `bypassed_queries`,
  `redirected_queries`, `blocked_queries_ratio`, `window_start`, `window_end`),
  plus `result.profiles[]` with `profile_id`, `profile_name`,
  `protected_device_count`, `paused`, and blocked/bypassed/redirected counts.
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
  and the sensors always agree.
- **Three counts, and the names say which is which.** An *endpoint* is a
  protected row in `/devices`, so `endpoint_count` is that row count alone. A
  *client* is a device seen under an endpoint, so `client_count` is the sum of
  the endpoints' client counts. `protected_device_count` is the two added
  together: everything DNS protection covers. It is therefore **not** the
  endpoint count, and conflating the two was a real defect — the figure was
  reported as `endpoint_count` while counting clients as endpoints.
- **The account identity holds exactly, and the profile rows deliberately do
  not.** At account level `protected_device_count == endpoint_count +
  client_count`, because the account view is a single pass over the endpoints.
  The per-profile rows cannot share that property: an endpoint enforcing two
  profiles (Control D's `profile` plus `profile2`) is counted under each, so they
  total more. Measured on the account that motivated this: 20 endpoints plus 266
  clients gives 286 protected devices, while the eight profile rows sum to 297.
  Quote the account figure rather than adding the rows up.
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
`supports_modes`, and `current_mode`; services carry `current_mode` and
`configured`; rules carry `action`, `enabled`, `comment`, and `group`; profile
options carry `current_value`. There is deliberately **no separate policy tool**,
because it would be a re-skin of this one.

**`configured` is what separates "switched off" from "never configured".** The
service catalog lists every service the vendor offers — over a thousand rows —
while a profile carries rows only for the services configured on it. Both kinds
of row report `current_mode: off`, so without `configured` the two are
indistinguishable, and a caller cannot tell which services have a previous mode
worth naming. Only a configured service does.

This matters on the write side. `set_service_state` on an unconfigured service is
how a service *gets* configured: it creates the row. That call therefore has no
previous mode to restore, so `before` reports `configured: false` and the `undo`
names `delete_service` — removing the row — rather than a mode reversal. Without
the field that same call would look like a state that failed to read, and the
model would report a perfectly reversible change as irreversible.

**Read surfaces say `action`, write surfaces say `mode`.** The write tools take a
`mode` argument and report it back under that name in `before` and `after`, so one
write result is internally consistent. `get_catalog` reports `action`, which is
what the catalog rows carry upstream. A caller mapping between them is crossing
from the read vocabulary to the write one, and that is the only place the two
should meet.

### `action` means three different things

The word is overloaded in this surface, and only one of the three is a rule's
behaviour. Read this before writing any description that mentions `action`.

| Where | What `action` is | Values |
| --- | --- | --- |
| `get_catalog`, `catalog_type: 'rules'` | a rule's behaviour | `block`, `bypass`, `redirect` |
| `get_activity_log`, `records[]` | a query's verdict, as a **code** | `-1`, `0`, `1`, `3` |
| upstream only, never exposed | the vendor's JSON object wrapping `do` + `status` | — |

The third is the vendor's own shape and is not surfaced: Control D writes a rule
with `{"do": <int>, "status": 0|1}` and its validation errors say *"Invalid rule
action"*, so `action` is the vendor's word for the concept while `do` is the value
inside it. We normalize both away at the client boundary.

**The write surface is uniformly `mode`, and that is ours.** Control D has no
`mode` field. The three mode families are named by us, in three different cases
because they are three different things:

| Family | Keys | Service calls take |
| --- | --- | --- |
| Rules | `block` / `bypass` / `redirect` | the key itself |
| Services | `off` / `blocked` / `bypassed` / `redirected` | `Off` / `Blocked` / `Bypassed` / `Redirected` |
| Default rule | `blocking` / `bypassing` / `redirecting` | `Blocking` / `Bypassing` / `Redirecting` |

`SERVICE_FIELD_MODE = "mode"` is the one write argument across services, rules,
and the default rule, so a caller uses `mode` everywhere the caller writes and
`action` only where the caller reads. A rule's `before` and `after` inside a write
result use `mode`, because a write result is compared against the write that
produced it; a catalog row uses `action`, because that is what it carries.

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

**`search` filters `items` and `item_count`, and sets `text` to `null`.** `text`
is the unfiltered copyable listing of the whole catalog, so it is withheld
rather than returned whole once a search has narrowed `items` — returning both
would show a caller rows the search had removed, with nothing marking which of
the two was authoritative. Read `items` for a narrowed result; `text` is present
only when nothing was filtered.

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
| `enforced_profiles` | Every profile this endpoint enforces, in order, each with `profile_id`, `profile_name`, and its `slot` |
| `associated_client_count` | Clients attributed to this endpoint |
| `parent_device_id`, `parent_client_id` | Set when the device is also a client under another endpoint |
| `last_active` | When the endpoint was last seen. **Absent** when it has never been seen |
| `analytics_logging` | `None`, `Some`, or `Full` — the level `set_endpoint_logging` sets |
| `advanced` | The dashboard's Advanced Settings; see above |

`analytics_logging` sits at the top level rather than inside `advanced`, because
`advanced` is documented read-only and this is the one endpoint setting a tool
here can change. Control D reports it as `stats` (`0`/`1`/`2`); the read side maps
it back, which is what lets `set_endpoint_logging` name the level it replaces.

Two profiles are common here: 11 of 20 endpoints on the account that motivated
this integration enforce a primary *and* a secondary. The rule engine **merges**
both before matching, so an endpoint whose second profile blocks something is
blocked regardless of what the primary allows. Reading only the primary sees half
the picture — which is why this is one list rather than a primary/secondary pair.

`slot` is `primary`, `secondary`, or `additional` beyond those. The list is the
single stored statement of what the endpoint enforces: the primary/secondary
accessors used internally are read from it, so they cannot disagree with it.

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

### The description template

A tool's description is composed at construction from two parts, and the split
decides what goes where:

```
[family injection — identical for every tool in the family]

[body — unique to this tool]
```

The body is written for a machine consumer, in this order:

1. **One line: what the tool does.** No justification clause.
2. **A bullet per argument**, as `field — meaning`. State the source
   (`get_catalog, catalog_type: 'filters'`) and exact enum values in their exact
   case, because the three mode families use three different cases for the same
   concept: `'Off'`/`'Blocked'`/`'Bypassed'`/`'Redirected'` on services,
   `'block'`/`'bypass'`/`'redirect'` on rules, and
   `'Blocking'`/`'Bypassing'`/`'Redirecting'` on the default rule.
3. **Only genuine tool-specific warnings**, such as `create_rule` being
   non-idempotent, `set_endpoint_profile` merging two profiles before matching,
   or `delete_service` not being the same as `mode: 'Off'`.

Do not restate any of the following, which are already covered elsewhere:

- what `undo`, `before`, `after`, `changed`, `warnings`, or `status` mean — the
  system model defines every one of them
- that the tool is reversible, in the thirteen forms this was previously written
- the definition of a profile, endpoint, or client — the system model defines all
  three, and the injection exists to make sure the agent has it
- what a count means, or when to prefer the activity log over `test_domain`

## Gotchas the tool schemas must encode

- **Selecting a profile or an endpoint** — every tool that acts on one, and every
  read that can be scoped to one, accepts either the id or the display name.
  Prefer the id: names are not unique, and a name matching more than one target
  is refused with `endpoint_target_ambiguous` or `profile_target_ambiguous`
  rather than resolved arbitrarily. An explicit id wins when both are supplied.
  The one deliberate exception is `create_endpoint`, where `endpoint_name` is the
  name of the endpoint to *create*, not a selector — resolving it against the
  inventory would reject every creation, so the resolution is opt-in per tool.
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
