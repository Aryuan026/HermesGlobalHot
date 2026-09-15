# Progress

## 2026-09-15 — Hermes Agent 0.21.0 Wave 6 source candidate

- Lifecycle: active, Global-Hot-only external-review candidate. Wave 7 is not
  open and no installation, deployment, enablement, or live canary occurred.
- Manifest version: 0.4.0. The declared Continuity compatibility floor is now
  `>=0.5,<1`, matching the first service candidate whose complete-group source
  classes are derived from the accepted H13 host proof. Hermes 0.21 uses this
  range as advisory dependency metadata, so the exact assembly pin remains the
  runtime release authority.
- Exact pairing: Hermes upstream
  `29112bef099274229cadff79cdff7bf7b99c4b77`, accepted host
  `13900108780ae712059075200b243aa049c634cf` with tree
  `5e82789d9984f8c338c09bdd0ebb31794af1f0dc`, and Continuity
  `8eb44f3e8afe5d134691d258607ee67af518d706`.
- Production runtime, metadata schema, donor compiler, frozen recent anchor,
  projection policy, final-budget logic, and receipt semantics are unchanged.
- New exact-host integration starts from one real mixed Bot Chat in SessionDB,
  with host-minted scheduled, internal, delegated, missing, and human proofs.
  Real PluginManager discovery loads Continuity before Global Hot; the final
  provider body contains the human and scheduled inputs exactly once, excludes
  internal/delegated/unknown bodies, and labels scheduled-looking text carrying
  a human proof as `human_input` rather than `scheduled_input`.
- The same run settles one real `hermes.transport.v3` record and reads back one
  body-free Global Hot delivery receipt with three selected facts. No network
  provider or real transcript is used.
- Exact-host Global Hot suite: 80/80 Green. Adjacent accepted-host H13, service,
  request-overlay, and middleware matrix: 82 passed plus 23 subtests. Existing
  tests retain both two-plugin execution orders, final-budget removal,
  estimate-unproven removal, kept delivery, drift rejection, retry/fallback,
  and body-free receipt coverage.
- The public workflow still replays the installed-control 0.20.5 host and skips
  the new H13 test. Public 0.21 patch replay and disabled lifecycle belong to
  Wave 7; current evidence must not be described as public Actions, install, or
  natural cross-mouth behavior.

## Retained product and predecessor evidence

- Donor source: owner-authorized AsherieSystem revision
  `ddfb1e9aeb7c6f7797912e959a0970c621875c83`.
- Donor core: Global Hot compiler and recent-interaction anchor extracted with
  their behavior tests; the anchor remains a frozen reference while production
  uses a neutral adapter. Exact lineage is in `PROVENANCE.md`.
- Hermes source adapter: consumes the profile-local Continuity
  `canonical-source.v2` service with a closed request/response contract and
  closed human/scheduled/internal/delegated/tool/unknown classification.
- Runtime: per-logical-turn source freeze and per-supported-physical-request
  projection, compatible provider fallback, tool follow-up, continuation, final
  provider-body proof, and body-free delivery metadata are implemented.
- Predecessor host prerequisite: generic Hermes 0.20.5 seams through
  `5a680e5e38625fb3275b4bf6973a40d089ec11a7`; Continuity
  `9a98acfe53ab74be5dae0b86c9b0303a9dab96bc`.
- Predecessor verification: public CI replays all twelve host patches, installs the
  materialized runtime, exports the real-host roots, runs the shared overlay
  and middleware tests, then runs the Global Hot suite and Continuity's paired
  production entrypoint. The exact local Hermes + Continuity matrix is 79/79
  Green and covers both two-plugin final-guard orders, late provider-body
  expansion, attempt expiry/cap, metadata load order, and Global Hot drift
  without poisoning Continuity delivery.
- Real-host wiring proof: Hermes discovered both real directory plugins and
  ran two production conversation turns. Continuity and Global Hot were each
  exact-once in both final provider bodies; Global Hot wrote two canonical
  delivery receipts, manager unload/reload preserved Continuity revision
  readback, and a real provider-error turn wrote no new receipt. CLI and
  gateway-tagged platform contexts were exercised locally; no live channel is
  claimed.
- Plugin lifecycle proof: exact public candidates `698fd4d` and `9f01f61`
  installed through the official CLI into a disposable profile with full
  commit pins and remained disabled; Continuity passed native Doctor, this
  plugin passed joint Doctor with Continuity, and official removal left no
  plugin directory or install-metadata entry. This is not target-profile
  deployment.
- Publication: the prior exact revision received a second external review.
  Its source/product, attempt-lifetime, and metadata-ownership findings are
  incorporated in this replacement root; repeat exact-revision review remains
  the current gate.
- Fixed profile-realm candidate: the body-free receipt database is pinned to
  the active profile's host-owned plugin-data namespace, the obsolete
  `metadata_db` setting is removed, and a real two-profile `PluginManager`
  test proves independent ledgers after ambient profile overrides are reset.
- Shared-overlay candidate: the duplicate projector and mirror test file are
  removed. Generic carrier/proof/final-budget behavior now comes from Hermes;
  Global Hot keeps its current-user anchor and near-field policy. Deliberate
  final-budget or unproven-estimate removal is visible as its own native reason
  rather than `execution_projection_drift`.
- Runtime status: not installed, not enabled, not deployed, and not validated
  in a live cross-mouth conversation.
- Long-input boundary: exact ownership necessarily hashes the original carrier
  once. The shared-host regression covers a 1 MB string and a 10K-part carrier
  and proves one adjacent-slice hash per verification; it does not claim
  constant-time work.
- Product adaptation: the frozen donor still records its original labels, but
  the Hermes production path renders only `human_input`, `scheduled_input`,
  and `assistant_outcome` with closed source class and actual Hermes source.

The next review should assess only the Wave 6 dependency floor and real H13 to
final-provider-body mixed Bot Chat proof. Installation and deployment remain
separate later gates.
