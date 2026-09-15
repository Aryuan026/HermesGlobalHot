# Hermes Global Hot 0.21.0 Wave 6 H13 selection evidence

## Scope

This receipt covers the Global-Hot-only Wave 6 source candidate. It does not
claim installation, deployment, enablement, public 0.21 replay, network-provider
traffic, real QQ/WeChat traffic, or natural MellowIsle/wakeup behavior.

## Exact inputs

- Hermes upstream 0.21.0:
  `29112bef099274229cadff79cdff7bf7b99c4b77`
- accepted Hermes host:
  `13900108780ae712059075200b243aa049c634cf`
- accepted Hermes tree:
  `5e82789d9984f8c338c09bdd0ebb31794af1f0dc`
- Hermes Continuity:
  `8eb44f3e8afe5d134691d258607ee67af518d706`
- Hermes Global Hot predecessor:
  `af605282d3b221e705d1ee47b886f2d054cc3598`
- owner-authorized AsherieSystem donor:
  `ddfb1e9aeb7c6f7797912e959a0970c621875c83`

The Wave 6 candidate identity is the Git revision carrying this file. The
document does not attempt a self-referential commit hash.

## Product delta

- Manifest version advances from `0.3.0` to `0.4.0`.
- The declared Continuity compatibility floor advances from `>=0.4,<1` to
  `>=0.5,<1`, so an older pre-H13 source classifier no longer satisfies the
  public dependency contract. Hermes 0.21 treats this range as advisory; the
  exact assembly pin, not the range alone, is the runtime release authority.
- Production runtime, metadata storage, donor compiler, frozen recent anchor,
  two-hour/latest-two/latest-outcome/240/220/three-item policy, request overlay,
  final-budget rules, and receipt schema are unchanged.
- One exact-host integration test was added.

## Mixed Bot Chat proof

The test creates a disposable Hermes profile and one real SessionDB Bot Chat
containing five complete dialogue groups:

1. a host-proved scheduled wakeup;
2. a host-proved internal notice;
3. a host-proved delegated result;
4. a group with missing origin proof; and
5. scheduled-looking visible text carrying a real human proof.

Both real plugin directories are loaded through production PluginManager
discovery. Continuity reads the complete groups and consumes the accepted H13
classifier. Global Hot requests only `human` and `scheduled`, projects the two
eligible inputs plus the latest assistant outcome, then passes through the real
0.21 request middleware, execution middleware, provider-body filter/capture,
transport settlement, and post hook.

Observed assertions:

- the final provider body contains one Global Hot block;
- the real wakeup is labelled `scheduled_input / scheduled`;
- scheduled-looking text carrying human proof is labelled
  `human_input / human`, not scheduled;
- internal, delegated, and missing-proof bodies are absent;
- exactly one settled provider body is captured;
- one delivery receipt records three selected facts; and
- receipt/check rows contain none of the selected or current message bodies.

## Verification

- Exact accepted-host plus Continuity Global Hot suite: `80/80` Green.
- Adjacent accepted-host H13, service registry, request-overlay, and middleware
  tests: `82 passed, 23 subtests passed`.
- The pre-change Global Hot suite was `79/79` Green against the same exact host
  and Continuity, confirming that the new work closes an evidence/compatibility
  gate rather than replacing a failing production algorithm.

The current public workflow still reconstructs the predecessor 0.20.5 control
and therefore skips the H13 integration test. Public reconstruction of the
complete 0.21 patch series and the official disabled install/Doctor/remove
lifecycle remain Wave 7 work.

## Stop condition

The candidate may proceed to independent exact-head source review. It must not
be described as installed, enabled, deployed, publicly replayed on 0.21, or
naturally observed.
