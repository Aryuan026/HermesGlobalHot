# Security and privacy

Hermes Global Hot runs in process with Hermes and has the same local privilege
level. Install only an exact reviewed revision.

## Data boundary

- Global Hot never opens Hermes `state.db` and never imports Continuity private
  modules or metadata schemas.
- Canonical message bodies arrive only through a synchronous, profile-local
  Continuity service response and live only for compilation/request projection.
- The Global Hot SQLite ledger contains hashes, IDs, counts, statuses, and UTC
  timestamps only. It has no transcript-body column, FTS table, search index,
  consumer cursor, or network client. The file is owner-claimed and rejects a
  foreign owner, canonical Hermes tables, or an unclaimed nonempty database.
- Real conversation fixtures, databases, sidecars, logs, configuration,
  credentials, owner/channel IDs, and private paths must not enter Git.

## Prompt and delivery boundary

Cross-mouth text is untrusted quoted dialogue data, not a system message,
persona, memory authority, or current-user instruction. Projection modifies an
existing real user carrier only, uses a dynamic exact-once marker, and closes
the reference block before the current user content.

Source windows fail closed as a whole when Continuity reports ambiguous or
unavailable history, a response violates the closed schema, an excluded/current
session appears, or a scan cap is exceeded. Clearly classified policy-excluded
groups are omitted by Continuity before their bodies cross the service
boundary; that omission is revision-bound and body-free traced.

A `delivered` state requires the same `hermes.transport.v3` record that reached
the final provider SDK body, one exact projection, a successful provider return,
`post_api_request`, and a canonical body-free receipt. Middleware projection,
transport return, and delivery receipt are distinct states. Receipt write
failure remains visibly `receipt_failed`.

Context-window trust also fails closed. Authoritative host values are used
directly; catalog/cached values keep a 10% margin; unknown or fallback values
remain native. The final guard runs after ordinary provider-body transforms and
uses the host's explicitly labelled heuristic-with-margin estimate. That
estimate is not represented as exact provider tokenization.

Process-private projection and transport attempts have a hard count cap and
TTL. Expiry revokes later settlement; an execution already inside the provider
boundary is protected until it exits, and a late post/error hook cannot revive
an expired attempt.

`codex_app_server` is unsupported because it bypasses Hermes request
middleware; subagent calls are also outside this plugin's v1 surface. MoA
prepared requests are transport-ambiguous, so this plugin removes its
projection and the provider receives the native request. Fallbacks with
unproven context provenance or headroom likewise remain native.

Use GitHub private security advisories for vulnerabilities. Never attach real
transcripts, credentials, local database excerpts, or deployment paths to a
public report.
