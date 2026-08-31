# Provenance

Hermes Global Hot is an owner-authorized extraction from the private
AsherieSystem revision
`ddfb1e9aeb7c6f7797912e959a0970c621875c83`. A sealed Graphify guide at
`0adda1b` was used for navigation; every relevant Global Hot donor file checked
against it was byte-identical to the requested `ddfb1e9` source.

The Hermes compatibility lineage is:

- upstream Hermes 0.20.5: `fcbd1076a93841fa88855acce810e342a5b78101`;
- reviewed owner overlay: `c7c36f36ccee592a96f90e8acd9c6401808a02ad`;
- generic host seams: `201fe7756c57c35aaed9af8e9886e10ff4d25cfe`,
  `b7fac683859f5997b4cc63a951078b99c209abbc`,
  `22dd21241f3628e0d25b808012f07874d45310d4`,
  `20b7b9a3b4f66871686503f222e39f4c55a058a5`,
  `81f8fa21167b1fcd3929b27ee172b6cf7a94ec21`,
  `5e1b05f04b193ade4eb16fb28f29198b0ee672a3`,
  `7a5c6ca23b544d73fb37a3a1c7d8b08d1a82938c`,
  `7c183e81832c81e29f6d095a15bb7c8cd080ee5c`,
  `113b4ab5285f92a1013c6a494eb33260a7f70140`,
  `969cf5bdbc3a110e475c02ed8e4ee84f64be32ed`, and
  `ccd7bf350ca54a44b7351904e079f5ffdb64eec0`;
- Hermes Continuity service contract: `hermes-continuity:canonical-source.v2`,
  plugin version `>=0.4,<1`, exact paired candidate
  `559512c549db14fc64d73419f76e0682b7375429`.

## Extraction matrix

| Decision | AsherieSystem donor | Hermes Global Hot target | Treatment |
| --- | --- | --- | --- |
| Retain | `services/home/app/hot_context/assembly.py`: `_GLOBAL_HOT_*`, `_global_hot_sha256`, plan/build/resolve helpers through `compile_global_hot_context` | `global_hot_compiler.py` | Mechanically extracted the pure compiler: immutable source revision and plan digest, closed material/binding schemas, reference-only output, currentness classification, alias/exact-body dedupe, structural order, hard bounds, body-free trace, and same-plan physical binding authority. |
| Retain | `services/home/tests/test_global_hot_context_compiler.py` | `tests/test_global_hot_compiler.py` | Ported the ten donor compiler tests with only the import path changed. |
| Retain | `services/home/app/recent_interaction_anchor.py` | `recent_interaction_anchor.py` | Byte-identical frozen donor/reference file: two-hour bound, latest two human turns, latest assistant outcome, 240/220 character limits, stable IDs, quoted-data boundary, and body-free selection/delivery trace. It is not the Hermes production adapter. |
| Retain | donor recent-anchor tests | `tests/test_recent_interaction_anchor_core.py` | Retained pure donor selection/rendering evidence. Home labels are allowed here because this layer proves provenance rather than defining the Hermes provider protocol. |
| Adapt | donor selection limits and anchor identity | `runtime.py` neutral candidate adapter/renderer | Preserves the two-hour/latest-two-input/latest-outcome/240/220/three-item behavior while replacing Home source predicates and visible labels with `human_input`, `scheduled_input`, `assistant_outcome`, closed `source_class`, and the actual Hermes source. |
| Adapt | Home Global Hot owner projection, continuity sidecar binding, mouth snapshot, transport reconciliation, and post-LLM receipts | `runtime.py`, `metadata.py`, `__init__.py`, plus Hermes `hermes.request_overlay.v1` | Replaced Home surfaces with a Continuity source service, per-turn freeze, shared host request carrier/proof, and body-free SQLite delivery ledger. H11 deletes the plugin-local projector while preserving the donor compiler and frozen anchor unchanged. |
| Adapt | Home/Bridge/mobile/cron/wakeup source labels | neutral Continuity complete dialogue groups | Continuity supplies a closed source class. Human dialogue and durably verified scheduled cron/wakeup dialogue are eligible; internal, delegated, tool, and unknown groups are rejected. |
| Do not port | `HotContextStore`, `UpstreamContextMergeStore`, JSON ownership, export/recall ranking, retrieval, legacy segment cutover, Warm/Cold/search tools | none | Hermes and Continuity retain their own storage/search responsibilities; this repository owns no durable message corpus. |
| Do not port | Home `PromptAssembly`, runtime `main`, service startup, cache/window scanners, gateway/mobile/chatbox surfaces | none | Those are AsherieSystem host owners, not portable Hermes plugin contracts. |

## Deliberate host adaptation

Global Hot does not import Continuity implementation modules. The neutral
service supplies stable complete groups, content hashes, and a closed source
classification, and filters the consumer-requested source classes before
returning bodies. This plugin maps accepted groups through a Hermes-neutral
near-field adapter into the unchanged donor compiler material schema. The
frozen donor anchor remains executable provenance but no longer controls
production eligibility or model-visible labels.

Each logical turn freezes one canonical source revision and donor plan. Every
physical provider request independently adapts that plan to its actual user
carrier. The receipt hashes the final provider body captured by Hermes after
preflight, Relay rewriting, ordinary provider-body transforms, and the final
budget guard. No source body, rendered prompt, or request body is written to
Global Hot metadata.
