# Hermes Global Hot

Hermes Global Hot gives one Hermes profile a small shared near-field across its
different mouths. A QQ, web, CLI, cron, wakeup, or custom-front-end turn can see
the most recent complete dialogue from the other sessions without merging
their native histories.

It is an ordinary request plugin, not the selected Hermes memory backend. That
is what lets it run alongside any long-term memory provider: Global Hot handles
the immediate conversational room tone, while the memory backend remains free
to own recall, writing, compression, and lifecycle policy.

## What is projected

The source is the profile-local `hermes-continuity:canonical-source.v2`
service. Global Hot never opens Hermes `state.db` and never imports Continuity's
private adapter or metadata schema.

For each logical turn it freezes one bounded two-hour source snapshot, then
uses the owner-reviewed AsherieSystem near-field limits through a
Hermes-neutral production adapter:

- at most the latest two eligible human or scheduled inputs;
- the assistant outcome from the latest selected turn;
- 240 characters per human item and 220 for the assistant outcome;
- at most three quoted items in total; and
- a five-minute future-clock tolerance.

Only complete user/final-assistant groups with a closed source classification
are eligible. Global Hot asks Continuity for exactly `human` and `scheduled`;
clearly classified `internal`, `delegated`, `tool`, and `unknown` groups are
counted and omitted before their bodies cross the service boundary. Scheduled
wakeup dialogue is eligible only when Continuity has durable host provenance.
The current session's compression lineage is excluded. Ambiguous, incomplete,
or over-cap source history still blocks the whole hot window instead of
silently presenting a partial view as complete.

The production-visible fact roles are `human_input`, `scheduled_input`, and
`assistant_outcome`. Each fact carries the closed `source_class` and the actual
Hermes `source`; Asherie/Home routing labels remain only in the frozen donor
reference and provenance record, never in the production eligibility path.

The selected material then passes through the extracted Global Hot compiler,
which retains canonical-alias and exact-body deduplication, structural ordering,
hard row/character bounds, source revisions, plan digests, and body-free traces.

## Each supported physical provider request

Global Hot registers `llm_request`, `llm_execution`, `post_api_request`, and
`api_request_error` boundaries. The frozen turn packet is adapted again for
each supported physical request, including SDK retries, tool follow-ups,
compatible provider fallbacks, and later continuations within the same logical
turn. A new logical turn reads a fresh two-hour window even when the source is
unchanged.

Projection changes only the last real user carrier and never inserts a new role
or message. String, text-block, image/document, Anthropic tool-result, Codex,
and Bedrock request shapes are handled without turning tool-only rows into a
fake user. The block has a dynamic marker and an explicit end boundary; quoted
history cannot masquerade as the current user's instructions.

Hermes `hermes.transport.v3` captures the final provider body after
provider-specific preflight, Relay rewriting, and ordinary transport
transforms. Global Hot registers a final, non-expansive budget guard: an
authoritative host window is used as reported, catalog/cached windows retain a
10% margin, and unknown or fallback windows stay native. The host's final-body
estimate includes messages, top-level prompts, tools/schema, attachments, and
framing margin; it is still an explicitly labelled conservative heuristic, not
a provider-tokenizer proof.

Carrier selection, provider-shape adaptation, exact overlay ownership,
scoped removal, canonical request hashing, and final-budget dispositions come
from Hermes `hermes.request_overlay.v2`. Global Hot retains only its marker,
frozen current-user identity, near-field policy, and receipt semantics. When a
final guard deliberately removes the field, status reports
`final_provider_budget_removed` or `final_provider_estimate_unproven` rather
than mislabelling the expected native request as projection drift.

A canonical delivery receipt is written only when that final body contains
this exact projection once, fits the proven usable window under that estimate,
the provider call succeeds, and `post_api_request` receives the same settled
transport record. Errors, drift, missing post hooks, ambiguous transport, and
receipt-storage failures never become `delivered`.

There is deliberately no delivery cursor: the hot field is supposed to be
present again on the next physical request and the next turn. `/global-hot-status`
reports the latest body-free check plus the last canonical delivery receipt.
Attempts that miss both terminal hooks are bounded by a process-private count
cap and TTL; expiry revokes settlement authority, while an execution currently
in progress is protected from the sweeper.

## Storage and privacy

The plugin stores no conversation bodies. Its profile-local SQLite ledger
contains session hashes, turn/request identities, source and plan digests,
selection counts, statuses, and timestamps only. The ledger claims a closed
plugin owner and refuses foreign-owned, canonical-Hermes, or unclaimed nonempty
databases. Its path is fixed at
`plugin-data/<host-owned-plugin-namespace>/global_hot.sqlite3` inside the
active Hermes profile; it is not a plugin setting. Hermes remains the transcript
owner; Continuity remains the canonical-source owner.

`api_mode=codex_app_server` and subagent calls are unsupported. MoA prepared
requests do not currently expose an unambiguous final provider carrier, so
Global Hot removes its projection: the provider receives the native request,
not an unreceipted hot field. A provider fallback whose context provenance or
usable headroom cannot be proven also stays native and visibly unsettled.

## Compatibility

The reviewed host lineage is:

- Hermes upstream 0.20.5: `fcbd1076a93841fa88855acce810e342a5b78101`;
- owner overlay: `c7c36f36ccee592a96f90e8acd9c6401808a02ad`;
- final generic host seams through:
  `5a680e5e38625fb3275b4bf6973a40d089ec11a7`;
- Hermes Continuity: `>=0.4,<1`; paired candidate
  `9a98acfe53ab74be5dae0b86c9b0303a9dab96bc`.

The twelve ordered Hermes patches are published by
[Hermes Continuity](https://github.com/Aryuan026/HermesContinuity/tree/9a98acfe53ab74be5dae0b86c9b0303a9dab96bc/patches).
The first eight provide the earlier runtime schemas, the next two align
official manifest-v2 installation and joint Doctor, and the final two own the
shared request overlay plus host-accepted disposition. Registration fails
visibly when the service, middleware, transport, or overlay schema is missing
or incompatible.

## Test

```bash
PYTHONPATH=/path/to/patched/hermes \
python -B -m unittest discover -s tests -v
```

Real Hermes and dual-plugin integration tests use `HERMES_SOURCE_ROOT` and
`HERMES_CONTINUITY_ROOT`. Every committed transcript fixture is synthetic.
Public CI replays all twelve patches from pure upstream, installs that host,
exports both roots, runs the host overlay/middleware suite and all Global Hot
real-host tests, then executes Continuity's paired production
`AIAgent.run_conversation` entrypoint. The shared-overlay matrix covers both
two-plugin final-guard orders.

The previously published revision received external review. This corrected
tree is the next external-review candidate; use the Git revision itself as the
publication identity rather than a self-referential hash in this file. It is
not installed, enabled, deployed, or live-verified.

The exact donor lineage and intentional omissions are recorded in
[`PROVENANCE.md`](PROVENANCE.md); trust and persistence boundaries are in
[`SECURITY.md`](SECURITY.md).

## License

MIT.
