# Repository instructions

Preserve these owner and provenance boundaries:

- Before changing the compiler or recent-interaction anchor, compare the exact
  donor symbols and tests at AsherieSystem revision
  `ddfb1e9aeb7c6f7797912e959a0970c621875c83` and update `PROVENANCE.md`.
- Keep `recent_interaction_anchor.py` as a frozen donor/reference module.
  Production eligibility and rendering must use the Hermes-neutral adapter;
  Asherie/Home source predicates and visible labels must not cross that seam.
- Consume the profile-local `hermes-continuity:canonical-source.v2` service;
  never import Continuity private modules or read Hermes `state.db` here.
- Request only the closed `human` and `scheduled` source classes. Unknown,
  internal, delegated, and tool dialogue stays out of the hot field without
  turning a proven policy exclusion into source ambiguity.
- Keep the two-hour / latest-two-human / latest-assistant / 240 / 220 /
  three-item near-field contract unless the owner explicitly changes it.
- This is a request-only ordinary plugin, not a memory backend, transcript
  owner, compressor, FTS/search system, or recall store.
- There is no delivery cursor. Retry, tool follow-up, compatible provider
  fallback, and the next logical turn must each receive Global Hot on every
  supported physical request.
- Verify delivery against `hermes.transport.v3` final `provider_body`; do not
  settle from middleware projection or provider return alone.
- Use only host-resolved context windows with explicit provenance. Unknown or
  fallback windows stay native, and the final provider-body budget guard must
  run after ordinary transport transforms.
- Never write message bodies to Global Hot metadata. Preserve latest-check and
  canonical-delivery truth as separate body-free surfaces.
- Keep physical attempts bounded by TTL and count, and require the metadata
  owner/path guards before any Global Hot table is created.
- Keep `codex_app_server` unsupported; keep MoA and unproven smaller-window
  fallbacks native until a reviewed physical carrier/proof contract exists.
- Runtime dependencies remain standard-library-only. Use
  `HERMES_SOURCE_ROOT` and `HERMES_CONTINUITY_ROOT` for real host integration.
- Never commit real IDs, paths, secrets, configs, logs, databases, SQLite
  sidecars, runtime state, or conversation fixtures.
- Do not describe the plugin as published, installed, enabled, deployed, or
  live-verified until that exact state has been demonstrated.

## Integration and audit truth

- A unit, runtime-helper, or registry test cannot prove host wiring. Delivery
  claims require real Hermes discovery and `AIAgent.run_conversation`, the
  final SDK provider body, production post/error hooks, and the real Global Hot
  and Continuity SQLite stores.
- Report only the highest proven layer: code-correct -> discovered/registered
  -> request projected -> final provider body -> post-settled -> next-turn
  readback -> restart readback -> surface-observed. Never promote an earlier
  Green layer into a later one.
- Reproduce an alleged host-order bug on the exact Hermes revision before
  changing production code. A manual execution/settle/post helper is not proof
  of the host's current order.
- After code correctness and the real-host gate are Green, default review moves
  to practical integration: dependency/version resolution, patch replay,
  config/doctor output, per-mouth latency, operator-visible failures, rollback,
  upgrades, and real channel canaries. Reopen compiler/runtime design only for
  a new reproducible regression or an owner-requested product change.
- The cross-repo gate lives at
  `HermesContinuity/tests/test_real_host_entrypoint.py`; run it against exact
  Hermes and Global Hot trees rather than duplicating its host sequence here.

Use the smallest compatible change and keep external review, installation, and
deployment as separate gates.
