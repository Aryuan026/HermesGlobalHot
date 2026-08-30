# Plan

## Product boundary

Hermes Global Hot owns only a request-time, cross-mouth near-field and its
body-free delivery evidence. It does not own canonical transcript storage,
session compression, long-term memory, search, or the Continuity source
adapter.

The v1 behavior is fixed deliberately:

- read a two-hour canonical window once per logical turn;
- select the latest two eligible human/scheduled inputs plus the latest
  selected turn's assistant outcome, at most three items;
- freeze that packet across retries, tool follow-ups, provider fallback, and
  visible continuations;
- project it into each supported physical provider request without adding a
  role or message;
- verify the final `hermes.transport.v3` provider body after ordinary
  transforms and the plugin's final budget guard; and
- persist only body-free checks and canonical delivery receipts.

There is no unseen-delta cursor. Repeated projection is the feature, not a
storage bug.

## Hard gates

- Preserve the owner-authorized donor compiler and frozen recent-anchor
  reference. Keep its selection limits while using a neutral production
  adapter and renderer.
- Consume `hermes-continuity:canonical-source.v2` through the profile-local
  service registry; never import Continuity internals or read `state.db`.
- Request only closed `human` and verified `scheduled` source classes. Let
  Continuity omit clearly classified policy exclusions before returning
  bodies, while incomplete, ambiguous, or over-cap source history remains an
  atomic block.
- Keep model-visible roles and sources Hermes-neutral; donor/Home labels may
  exist only in the frozen reference and provenance record.
- Keep quoted history outside current-user instruction authority with an exact
  dynamic marker and explicit end boundary.
- Settle delivery only from `post_api_request` against the same successful,
  unambiguous final provider-body record.
- Bound orphan physical attempts by count and TTL, protect active execution
  from sweeping, and make late terminal hooks no-ops after authority expires.
- Claim the metadata database with a plugin owner and reject state, foreign,
  or unclaimed nonempty SQLite files before creating Global Hot tables.
- Leave `codex_app_server` and subagent calls unsupported; remove Global Hot
  from MoA and unproven smaller-window fallbacks so their providers receive the
  native request.

## Release gates

1. Keep donor, runtime, metadata, and request-carrier suites Green, then pass
   the cross-repo real-host proof through plugin discovery,
   `AIAgent.run_conversation`, final provider body, post/error settlement,
   SQLite readback, and manager unload/reload.
2. Replace the obsolete two-commit repository history with the reviewed tree.
3. Push the exact revision for external web review.
4. Address external findings and record the accepted revision.
5. Only then perform a reversible disabled installation under separate
   authorization.
6. Enable and run live cross-mouth canaries only after deployment approval.

The first published candidate completed gates 1-3 and received external
review. Its P1 findings are being incorporated in the next exact-revision
candidate. Installation and live observation remain separate, later states
and are not implied by publication.
