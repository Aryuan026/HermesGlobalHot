# Hermes Global Hot

**让同一个 Hermes 的不同会话共享一点近期动静：刚刚聊了什么、定时唤醒做了什么，能回到眼前这轮对话里。**

这是一个实验性的跨会话工作上下文插件，不是长期记忆库，也不合并各会话的原始历史。
它从 [Continuity](https://github.com/Aryuan026/HermesContinuity) 取得已验证来源，
把最近两小时内很少量的完整对话引用递送给当前请求。
简单区分：**Continuity 接同一段对话的过去，Global Hot 接其他会话的近期动静。**

## 支持版本与当前状态

核对日期：**2026-10-23**。插件版本为 **0.3.0**；下文使用已审查提交
[af60528](https://github.com/Aryuan026/HermesGlobalHot/commit/af605282d3b221e705d1ee47b886f2d054cc3598)，
**不是直接安装 main**。公开主线落后于这个集成提交，本次文档调整不包含它的运行时代码。

| Hermes 版本 | 对应代码与使用条件 | 状态 |
| --- | --- | --- |
| **0.20.5** | 上述 Global Hot 固定提交＋已补丁宿主＋兼容的 Continuity | 公开集成基线；来源、递送结算与安装生命周期已有验证 |
| **0.21.3** | 单独移植的历史宿主／双插件装配线 | 已有阶段验收，不能按 0.20.5 补丁直接安装 |
| **0.21.5** | 同一 Global Hot 提交＋[Continuity 75aecd6](https://github.com/Aryuan026/HermesContinuity/commit/75aecd6d6544f3dcb313c42bf917c4a015a31cea) ＋对应已补丁宿主 | 已验证的固定配对；本仓不提供完整公开宿主安装包 |
| **0.22.0** | 仅开始本机宿主插件底座迁移 | **尚未取得本插件运行支持** |

其他版本未验证。`Continuity >=0.4,<1` 是**插件依赖范围**，不是 Hermes 宿主版本范围；
同名版本号或新上游发布都不能替代配对验证。

## 最近维护了什么

- **不只认“来自哪个频道”**：只选择已验证的人类／定时输入；内部通知、委派和来源
  不明的组不进入热场，不靠消息前缀授予身份。
- **双插件能共存**：载体归属、重试／fallback 和最终预算由宿主公共 overlay 接缝负责，
  两个插件不互相覆盖，也不各造一套投影器。
- **看最终递送，不把“准备好了”算成功**：只在最终 provider body 与成功结算对齐后
  写无正文回执；这些是固定集成提交的能力，不是本次文档新增的功能。

## 宿主前提

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
