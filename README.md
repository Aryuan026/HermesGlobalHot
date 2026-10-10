# Hermes Global Hot

**Give one Hermes profile a shared near-field across its conversation mouths.**

A small request-time context plugin: recent verified human or scheduled
interactions from other sessions can inform the current turn without merging
their histories. It complements [Continuity](https://github.com/Aryuan026/HermesContinuity)
and can coexist with a separate long-term memory provider.

## Compatibility

Last reviewed: **2026-10-10**. The instructions below target the reviewed
`0.3.0` ref `af605282d3b221e705d1ee47b886f2d054cc3598`, **not unpinned main**.
Public main currently trails that integration ref; this docs-only change does
not merge its runtime changes.

- **Hermes 0.20.5 — public integration baseline.** The reviewed ref uses the
  patched Hermes runtime and a compatible Continuity `>=0.4,<1`. The paired
  source, final-provider-body settlement and installation lifecycle were
  reviewed; owner-controlled deployment is recorded separately.
- **Hermes 0.21.3 — historical, separately ported integration.** Enabled
  dual-plugin replay and lifecycle were accepted on its exact host/plugin
  lane. That is not a claim that main or the 0.20.5 patches work unchanged.
- **Hermes 0.21.5 — maintained owner-controlled integration.** The unchanged
  reviewed Global Hot ref was jointly tested, then installed/enabled with the
  adapted Continuity `75aecd6d` on 2026-10-10. It still requires that lane's
  host contracts and Continuity source service; a complete public 0.21.5
  host/Continuity installation bundle is not provided here.
- **Other versions — not qualified.** Neither a dependency version range nor
  a newer upstream release proves compatibility.

Required contracts: `hermes-continuity:canonical-source.v2`,
`hermes.middleware.v2`, `hermes.transport.v3` and
`hermes.request_overlay.v2`. Missing or incompatible contracts fail visibly.
The exact public baseline's twelve foundation patches are available at
[Continuity's reviewed patch ref](https://github.com/Aryuan026/HermesContinuity/tree/9a98acfe53ab74be5dae0b86c9b0303a9dab96bc/patches);
use the additional indexed patches only with their own declared host lane.

## Highlights

- **Cross-mouth awareness without transcript merging.** A conversation can
  pick up a recent wakeup or another channel's exchange within the same profile.
- **A deliberately small hot field.** Two recent eligible inputs and the
  latest selected assistant outcome provide room tone, not a second history.
- **Present on each supported physical request.** Retry, tool follow-up and
  compatible fallback reuse the frozen turn packet; a new turn reads afresh.
- **Verified source, not text-based identity.** Only classified human and
  scheduled groups are eligible. A prefix or channel label cannot manufacture
  a scheduled provenance proof.
- **Honest final delivery.** Status separates planning/checks, deliberate
  budget removal and settled delivery receipts.

## How it works

1. Ask Continuity's profile-local read-only service for complete dialogue
   groups in the last two hours, excluding the current session's lineage.
2. Select and deduplicate a bounded near-field; freeze it for this logical turn.
3. Adapt it to each supported real-user request carrier. Quoted context has an
   explicit boundary and does not become the current user's instruction.
4. The host owns overlay proofs and the final SDK-body budget decision after
   ordinary provider transforms.
5. Write a delivery receipt only for the same successful, settled, unambiguous
   transport record containing the exact overlay once.

There is no delivery cursor: repeated projection is the feature. There is no
new memory store, search tool, compressor or plugin-local final tokenizer.

## Installation

Use the correct patched **0.20.5** host for the public baseline, initialize the
profile, and install its compatible Continuity first. Pin Global Hot rather
than cloning or installing an arbitrary main:

```bash
hermes plugins install Aryuan026/HermesGlobalHot \
  --ref af605282d3b221e705d1ee47b886f2d054cc3598 --no-enable
hermes plugins doctor hermes-global-hot --with hermes-continuity
hermes plugins enable hermes-continuity
hermes plugins enable hermes-global-hot
```

Joint Doctor loads both plugins in one temporary initialized profile. A
single-plugin Doctor without Continuity cannot prove the required service
binding. Do not substitute the 0.20.5 patch set for a 0.21.x port.

## Configuration and limits

The near-field policy is intentionally fixed:

- Window: **two hours**, with a five-minute future-clock tolerance.
- Inputs: at most the latest **two human/scheduled items**, **240 characters**
  each.
- Outcome: the latest selected assistant response, **220 characters**.
- Total: at most **three quoted items**.
- The current session's compression lineage is excluded.
- Internal, delegated, tool and unknown groups are omitted; ambiguous,
  incomplete or over-cap history blocks the window rather than pretending a
  partial read is complete.

Runtime settings in the reviewed [manifest](https://github.com/Aryuan026/HermesGlobalHot/blob/af605282d3b221e705d1ee47b886f2d054cc3598/plugin.yaml)
bound projection size, cached turns and orphan-attempt lifetime. The reviewed
receipt DB is fixed under the profile's
`plugin-data/<host-owned-plugin-namespace>/global_hot.sqlite3`. It contains
only hashes, IDs, counts, statuses and times, never conversation bodies.
Global Hot does not open `state.db` or import Continuity private modules.

**Two hours is a delivery horizon, not a database deletion policy.** This is
experimental working context, not permanent shared memory. The final host
estimate is a heuristic, not an exact tokenizer guarantee. Unknown context
provenance and unsafe fallback stay native; `codex_app_server`, subagent calls
and ambiguous MoA projection are unsupported.

## Verification

Check out the reviewed Global Hot ref before running its tests. In a Python
environment containing the dependencies of the exact paired host:

```bash
PYTHONPATH=/path/to/patched/hermes \
HERMES_SOURCE_ROOT=/path/to/patched/hermes \
HERMES_CONTINUITY_ROOT=/path/to/compatible/HermesContinuity \
python -B -m unittest discover -s tests -v
```

The paired production-entrypoint gate lives in Continuity:
`tests/test_real_host_entrypoint.py`; set its `HERMES_GLOBAL_HOT_ROOT` too.
Without the real roots, conditional skips are not host proof. Synthetic
provider/transport tests prove wiring, not live cross-mouth effectiveness.

## Maintenance

For each Hermes release, verify the source-service contract, both overlay
orders, retries/fallback, final-budget removal, settlement and joint
install/Doctor/remove. Update this version list with exact host, Continuity
and Global Hot refs and the proven layer; do not widen support by version
number alone.

Source review, local tests, installation/enablement, actual delivery and natural
QQ/WeChat continuity remain distinct. No new runtime result is claimed by this
README update.

## Documentation

- [Reviewed PROGRESS.md](https://github.com/Aryuan026/HermesGlobalHot/blob/af605282d3b221e705d1ee47b886f2d054cc3598/PROGRESS.md):
  dated source and lifecycle evidence; older status belongs to its date.
- [Reviewed PROVENANCE.md](https://github.com/Aryuan026/HermesGlobalHot/blob/af605282d3b221e705d1ee47b886f2d054cc3598/PROVENANCE.md):
  AsherieSystem compiler/anchor lineage and host requirements.
- [Reviewed SECURITY.md](https://github.com/Aryuan026/HermesGlobalHot/blob/af605282d3b221e705d1ee47b886f2d054cc3598/SECURITY.md):
  source, profile and persistence boundaries.
- [PLAN.md](PLAN.md): product scope; its staged release notes are historical,
  not a substitute for the compatibility list above.

## License

[MIT](LICENSE).
