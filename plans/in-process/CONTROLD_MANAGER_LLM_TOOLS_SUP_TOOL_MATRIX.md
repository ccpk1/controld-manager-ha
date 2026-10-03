# Supporting note: LLM/MCP tool matrix, tiers, and terminology

Companion to `CONTROLD_MANAGER_LLM_TOOLS_IN-PROCESS.md`. This note is the quick-reference
for tool naming, tier contents, and terminology. It is a working matrix, not the
authoritative spec — the spec is authored in Phase 1 as `docs/MCP_TOOL_REFERENCE.md`.

## 1. Terminology contract (authoritative, from the repo lexicon)

These are distinct objects and must never be conflated in tool names, descriptions,
prompts, or code. Source: `docs/ARCHITECTURE.md` (Official lexicon) and
`docs/DEVELOPMENT_STANDARDS.md` (Lexicon standards).

| Term | Meaning | Must not be called |
| --- | --- | --- |
| **Profile** | Control D configuration container (rules, services, blocklists) | entity, device |
| **Endpoint** | Top-level Control D protected row from `/devices` | device, client |
| **Client** | A client seen under an endpoint (analytics + device relationships) | device, endpoint |
| **Device** | Home Assistant device-registry container only | endpoint, client |
| **Entity** | Home Assistant platform object only | profile, endpoint, policy |

**Scope rules the tools and prompt must state:**

- An endpoint reports into exactly one owning profile in Home Assistant presentation
  terms, but may be attached to **multiple** profiles upstream (`profile`, `profile2`).
- A **client under an endpoint follows that endpoint's profile** (the ctrld-on-Firewalla
  case: one endpoint per VLAN, clients inherit the endpoint's profile).
- A client that is **explicitly assigned** a profile **is its own endpoint** and is
  protected by its own profile. There is no "individually protected" flag on a
  sub-client — assignment is what makes it an endpoint.
- Expose `is_endpoint` / `is_client_under_endpoint` so the model never infers this
  (`endpoint_device_id` set = endpoint; `parent_endpoint_device_id` set = sub-client).
- Client aliases are **client-scoped**; endpoint names are **endpoint-scoped**. These
  are separate mutation families and separate identity models.

## 2. Tier contents

Five tiers, matching the Firewalla precedent. The tier is the only write control (there
is no admin gate on Control D).

| Tier | Registers | Identifier sensitivity |
| --- | --- | --- |
| **Off** | nothing | — |
| **Summary only** *(recommended default)* | `get_account_overview` only | **No** identifiers; sends region plus profile/endpoint/client **counts** and overall blocked / bypassed / redirected counts |
| **Read only** | all read tools | Full read detail |
| **Read and control** | read + reversible controls | Full |
| **Full** | read + control + destructive (`delete_rule`) | Full, irreversible write |

## 3. Proposed tool matrix

Naming rule: `controld_manager__<verb>_<noun>`, named for **what the tool returns, not
where the data came from**. Mirrors Control D's own vocabulary (e.g. "activity log").

| Tool | Tier | Backs onto | Notes |
| --- | --- | --- | --- |
| `get_account_overview` | Summary | registry + account analytics | Non-identifying counts/region + action counts; per-profile counts in Read tiers |
| `get_inventory` | Read | `/profiles`, `/devices`, `/v2/client` | Profiles, endpoints, owning + attached profiles, client counts, parent/child, `is_endpoint` |
| `get_activity_log` | Read | `/v2/activity-log` | Per-record; filters mirror the dashboard chips; carries `trigger` + `triggerValue` |
| `test_domain` | Read | `dns.controld.com/<endpoint>` | One endpoint, one domain; `no_log=1`; `RCODE 5` = blocked |
| `get_block_summary` | Read | `count` | Action counts for a scope/window |
| `get_top_blocked_domains` | Read | `count/question` | Ranked domains |
| `get_block_breakdown` | Read | `count/triggerValue` | Ranked filters/services; resolved labels |
| `get_policy` | Read | profile detail endpoints | Filters, services, options, rules, default rule |
| `get_catalog` | Read | `get_catalog` service | Global catalog resolution |
| `set_filter_state` | Control | `set_filter_state` | Reversible |
| `set_service_state` | Control | `set_service_state` | Reversible |
| `set_option_state` | Control | `set_option_state` | Reversible |
| `set_rule_state` | Control | `set_rule_state` | Reversible |
| `set_default_rule_state` | Control | `set_default_rule_state` | Reversible |
| `enable_profile` / `disable_profile` | Control | `enable_profile` / `disable_profile` | Account-wide impact; confirm |
| `rename_endpoint` | Control | `rename_endpoint` | Endpoint-scoped |
| `set_endpoint_analytics_logging` | Control | `set_endpoint_analytics_logging` | Endpoint-scoped |
| `set_client_alias` / `clear_client_alias` | Control | `set_client_alias` / `clear_client_alias` | Client-scoped |
| `create_rule` | Control | `create_rule` | Additive but **not idempotent**; never `already_in_state`; `undo` = `delete_rule` |
| `delete_rule` | **Full** | `delete_rule` | Destructive; `confirm: true` |

**Deliberately not proposed:** a separate `get_block_causes` (folded into
`get_activity_log` + `get_block_breakdown`), a `list_analytics_clients` tool (misnames
endpoint data), an endpoint-to-profile assignment tool (deferred), any bulk action, and
any time-series tool (none exists upstream).

## 4. Envelope shapes (copy the Firewalla contract)

Reads:

```json
{ "result": { "...payload..." }, "meta": { "response_type": "...", "truncated": true } }
```

Controls:

```json
{
  "status": "applied | already_in_state | failed",
  "changed": true,
  "target": { "id": "...", "name": "..." },
  "before": { "...": "..." },
  "after": { "...": "..." },
  "undo": "controld_manager__set_filter_state(...)",
  "warnings": []
}
```

- `already_in_state` applies to **idempotent** tools only. `create_rule` is not
  idempotent and can never report it.
- `undo` may name a tool from a **higher tier** than the caller has enabled (for
  example, `create_rule`'s undo is `delete_rule` in the Full tier). The tool reports
  the undo and states that the configured tier does not permit it, so the user knows
  to raise the tier.

Both envelopes must be strictly JSON-serializable (no datetimes or sets).

## 5. Gotchas the tool schemas must encode

- `statusCode`, **not** `rcode` (`rcode` is silently ignored).
- `clientId` requires a co-present `endpointId`.
- Activity Log `pageSize` max is 500; deep pages return older records.
- Activity Log retains **33 days**; Statistics up to **365 days**; both are user-settable maximums.
- `endpointName` comes back empty on activity records — resolve names from `/devices`.
- Destination filters (`dstCountry`, `dstIsp`, `dstAsn`) exist on the Activity Log only.
- Activity Log defaults to a **short window across all profiles**; the caller narrows.
- Truncation must be honest: on ranked reads compare rows to `limit`; on paged reads
  report that more pages exist. A capped result is never presented as complete.
- Never sum ranked rows for a total; never round-trip a display label back as a query input.
- DNS verdict: HTTP 200 with `RCODE 5` means **blocked**; empty `verdict` means **no policy matched**. Neither is an error.
- Analytics maintenance returns `503` code `50303`.
- There is **no caching layer**; affordability comes from scope, limits, filters, and prompt warnings.
