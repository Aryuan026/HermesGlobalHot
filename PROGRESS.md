# Progress

- Lifecycle: active, corrected external-review candidate.
- Manifest version: 0.3.0.
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
- Host prerequisite: generic Hermes seams through
  `ccd7bf350ca54a44b7351904e079f5ffdb64eec0`; Continuity `>=0.4,<1`.
- Verification: the public-shaped plugin suite runs 77 cases with eleven expected
  real-host skips and 66 passes; public CI also replays all eleven host patches
  and runs the 17 shared-overlay tests. Exact Hermes `ccd7bf3` plus Continuity
  `12858c987332f658e0d969e6a39f03ff972cd74e` runs all 77/77 Green,
  including both two-plugin final-guard orders, late provider-body expansion,
  attempt expiry/cap, metadata load order, and Global Hot drift without
  poisoning Continuity delivery.
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

The next review should assess H11's shared ownership boundary, deleted plugin
copy, patch replay, and extensibility. Installation and deployment remain
separate later gates.
