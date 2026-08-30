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
  `969cf5bdbc3a110e475c02ed8e4ee84f64be32ed`; Continuity `>=0.4,<1`.
- Verification: the public-shaped suite runs 95 cases with nine expected
  real-host skips and 86 passes; exact Hermes
  `969cf5bdbc3a110e475c02ed8e4ee84f64be32ed` plus Continuity
  `5c0b84ea9721711a85d8856638426449d68c1057` runs all 95/95 Green. The
  focused runtime/metadata/registration matrix is 52/52 Green, including both
  execution registration orders, late provider-body expansion, attempt
  expiry/cap, metadata load order, and Global Hot drift without poisoning
  Continuity delivery.
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
- Runtime status: not installed, not enabled, not deployed, and not validated
  in a live cross-mouth conversation.
- Remaining long-input gate: exact carrier ownership proof still scans for the
  original contiguous carrier material. Its worst case is not claimed
  constant-time; add the recorded 100 KB / 1 MB / 10K-part performance gate
  before treating unusually large user carriers as a deployment-normal case.
- Product adaptation: the frozen donor still records its original labels, but
  the Hermes production path renders only `human_input`, `scheduled_input`,
  and `assistant_outcome` with closed source class and actual Hermes source.

The next review should focus on practical installation, patch replay, upgrade,
rollback, latency, and live cross-mouth canaries against the exact revision.
