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
- Use the generic Hermes request-overlay owner for provider carrier shapes,
  scoped proof/removal, canonical hashes, and final-budget dispositions; keep
  only Global Hot policy and identity in this plugin.
- Settle delivery only from `post_api_request` against the same successful,
  unambiguous final provider-body record.
- Bound orphan physical attempts by count and TTL, protect active execution
  from sweeping, and make late terminal hooks no-ops after authority expires.
- Fix the receipt database inside the active profile's host-owned plugin-data
  realm. Claim it with a plugin owner and reject canonical, foreign, or
  unclaimed nonempty SQLite files before creating Global Hot tables.
- Leave `codex_app_server` and subagent calls unsupported; remove Global Hot
  from MoA and unproven smaller-window fallbacks so their providers receive the
  native request.

## Release gates

1. For Wave 6, keep the donor compiler, frozen anchor, runtime budget, overlay,
   and metadata contracts unchanged. Declare Continuity `>=0.5,<1` and pin the
   exact accepted source in the assembly so the service is backed by the H13
   group classifier; Hermes currently treats the manifest range as advisory.
2. Pass the mixed Bot Chat path from real 0.21 SessionDB origin proofs through
   Continuity, Global Hot, the final provider body, post settlement, and the
   body-free SQLite receipt. Keep both execution-middleware orders and every
   final-budget disposition Green.
3. Push the exact revision for independent external review and address only
   findings inside the Wave 6 contract.
4. In Wave 7, publish and replay the complete 0.21 host patch series in public
   Actions, then run the paired production entrypoint and official disabled
   install/Doctor/remove lifecycle.
5. Install, deploy, enable, and run live cross-mouth canaries only under their
   later explicit gates.

The current stop condition is a Wave 6 external-review source candidate.
Installation and live observation remain separate later states and are not
implied by publication.
