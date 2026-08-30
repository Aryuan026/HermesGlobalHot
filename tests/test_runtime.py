from __future__ import annotations

import copy
import importlib
import json
import sys
import threading
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "hermes_global_hot_runtime_tests"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package

runtime_module = importlib.import_module(f"{PACKAGE}.runtime")
GlobalHotRuntime = runtime_module.GlobalHotRuntime

UTC = timezone.utc
REFERENCE = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def message(message_id: str, role: str, content: object) -> dict:
    return {
        "message_id": message_id,
        "role": role,
        "content": copy.deepcopy(content),
        "content_hash": runtime_module._content_hash(content),
    }


def group(
    group_id: str,
    occurred: datetime,
    user_text: str,
    assistant_text: str,
    *,
    session_id: str | None = None,
    source: str = "qqbot",
    source_class: str = "human",
) -> dict:
    source_session_id = session_id or f"session-{group_id}"
    return {
        "source_session_id": source_session_id,
        "source": source,
        "source_class": source_class,
        "source_snapshot": runtime_module._sha256([source_session_id, group_id]),
        "group_id": group_id,
        "effective_event_at": iso(occurred),
        "messages": [
            message(f"{group_id}-user", "user", user_text),
            message(f"{group_id}-assistant", "assistant", assistant_text),
        ],
    }


def trace(group_count: int, *, policy_excluded_group_count: int = 0) -> dict:
    return {
        "schema": "continuity_canonical_window_trace.v2",
        "listed_session_count": group_count,
        "candidate_session_count": group_count,
        "source_session_count": group_count,
        "returned_group_count": group_count,
        "outside_horizon_session_count": 0,
        "outside_horizon_group_count": 0,
        "current_lineage_excluded_count": 1,
        "policy_excluded_group_count": policy_excluded_group_count,
        "session_proofs_sha256": "c" * 64,
        "group_proofs_sha256": "d" * 64,
        "body_included": False,
    }


def response(
    groups: list[dict],
    *,
    status: str = "ready",
    reason: str = "",
    revision: str = "a" * 64,
) -> dict:
    ready_groups = copy.deepcopy(groups) if status == "ready" else []
    return {
        "schema": "continuity_canonical_window_response.v2",
        "status": status,
        "reason": reason,
        "reference_at": iso(REFERENCE),
        "horizon_seconds": 7200,
        "source_revision": revision,
        "scan_complete": status in {"ready", "empty"},
        "groups": ready_groups,
        "trace": trace(len(ready_groups)),
    }


class FakeSource:
    def __init__(self, value: dict) -> None:
        self.value = copy.deepcopy(value)
        self.requests: list[dict] = []

    def read_window(self, request: dict) -> dict:
        self.requests.append(copy.deepcopy(request))
        value = copy.deepcopy(self.value)
        value["reference_at"] = request["reference_at"]
        return value


class FakeMetadata:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.deliveries: list[dict] = []

    def record_check(self, **kwargs) -> None:
        self.checks.append(copy.deepcopy(kwargs))

    def record_delivery(self, **kwargs) -> bool:
        self.deliveries.append(copy.deepcopy(kwargs))
        return True

    def status(self, session_id: str = "") -> dict:
        return {
            "schema": "global_hot_status.v1",
            "status": self.checks[-1]["status"] if self.checks else "no_check",
            "last_check": self.checks[-1] if self.checks else {},
            "last_delivery": self.deliveries[-1] if self.deliveries else {},
            "stores_message_bodies": False,
            "uses_delivery_cursor": False,
        }


class FakeTransportRecord:
    schema_version = "hermes.transport.v3"
    _PRIVATE_KEYS = {
        "_moa_prepared_request",
        "__bedrock_region__",
        "__bedrock_converse__",
    }

    def __init__(self) -> None:
        self.middleware_verified_request: dict | None = None
        self.provider_body: dict | None = None
        self.capture_count = 0
        self.ambiguous = False
        self.settled = False
        self.provider_body_estimated_tokens: int | None = None
        self.provider_body_estimate_source = "unknown"
        self.provider_body_estimate_confidence = "unknown"
        self._filters = []

    def register_provider_body_filter(self, callback, *, phase="transform") -> None:
        self._filters.append((phase, callback))

    @staticmethod
    def _estimate(payload: dict) -> dict:
        return {
            "estimated_tokens": max(1, len(repr(payload)) // 4) + 64,
            "estimate_source": "hermes.provider_body.rough.v1",
            "estimate_confidence": "heuristic_with_margin",
        }

    def filter_provider_body(self, payload: dict) -> dict:
        if "_moa_prepared_request" in payload:
            return payload
        current = self._snapshot(payload)
        filters = sorted(self._filters, key=lambda item: item[0] == "final_guard")
        for _phase, callback in filters:
            try:
                current = callback(current, **self._estimate(current))
            except Exception:
                self.ambiguous = True
        estimate = self._estimate(current)
        self.provider_body_estimated_tokens = estimate["estimated_tokens"]
        self.provider_body_estimate_source = estimate["estimate_source"]
        self.provider_body_estimate_confidence = estimate["estimate_confidence"]
        return current

    def _snapshot(self, payload: dict) -> dict:
        return copy.deepcopy(
            {
                key: value
                for key, value in payload.items()
                if key not in self._PRIVATE_KEYS
            }
        )

    def mark_middleware_verified(self, payload: dict) -> None:
        if "_moa_prepared_request" in payload:
            self.ambiguous = True
            self.settled = False
            return
        self.middleware_verified_request = self._snapshot(payload)

    def capture_provider_body(self, payload: dict) -> None:
        self.capture_count += 1
        if self.capture_count != 1:
            self.ambiguous = True
            self.settled = False
            return
        self.provider_body = self._snapshot(payload)

    def settle(self) -> None:
        self.settled = bool(
            not self.ambiguous
            and self.middleware_verified_request is not None
            and self.provider_body is not None
            and self.capture_count == 1
        )


def provider_request(text: str = "current mouth") -> dict:
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": text}],
        "max_tokens": 512,
    }


def make_runtime(
    source: FakeSource,
    metadata: FakeMetadata | None = None,
    **kwargs,
) -> GlobalHotRuntime:
    kwargs.setdefault("clock", lambda: iso(REFERENCE))
    kwargs.setdefault(
        "estimator",
        lambda rows: max(1, len(json.dumps(rows, ensure_ascii=False)) // 4),
    )
    return GlobalHotRuntime(
        source,
        metadata or FakeMetadata(),
        **kwargs,
    )


def project(
    runtime: GlobalHotRuntime,
    *,
    session_id: str = "current-session",
    turn_id: str = "turn-1",
    api_request_id: str = "api-1",
    request: dict | None = None,
    context_window_tokens: int | None = 32_000,
    context_window_source: str = "config",
    context_window_confidence: str = "authoritative",
):
    return runtime.llm_request(
        request=request or provider_request(),
        session_id=session_id,
        turn_id=turn_id,
        api_request_id=api_request_id,
        model="test-model",
        provider="openai",
        base_url="https://provider.invalid",
        context_window_tokens=context_window_tokens,
        context_window_source=context_window_source,
        context_window_confidence=context_window_confidence,
    )


def execute_attempt(
    runtime: GlobalHotRuntime,
    request: dict,
    *,
    session_id: str = "current-session",
    turn_id: str = "turn-1",
    api_request_id: str = "api-1",
    provider_transform=None,
    capture: bool = True,
    settle: bool = True,
    record: FakeTransportRecord | None = None,
    schema: str = "hermes.transport.v3",
    before_provider=None,
    context_window_tokens: int | None = 32_000,
    context_window_source: str = "config",
    context_window_confidence: str = "authoritative",
):
    sent: list[dict] = []
    record = record or FakeTransportRecord()

    def terminal(payload):
        record.mark_middleware_verified(payload)
        provider_body = (
            provider_transform(copy.deepcopy(payload))
            if provider_transform is not None
            else payload
        )
        if before_provider is not None:
            before_provider(record)
        if capture:
            provider_body = record.filter_provider_body(provider_body)
            record.capture_provider_body(provider_body)
        sent.append(copy.deepcopy(provider_body))
        return {"ok": True}

    result = runtime.llm_execution(
        request=request,
        original_request=provider_request(),
        next_call=terminal,
        session_id=session_id,
        turn_id=turn_id,
        api_request_id=api_request_id,
        model="test-model",
        provider="openai",
        base_url="https://provider.invalid",
        transport_record=record,
        transport_schema_version=schema,
        context_window_tokens=context_window_tokens,
        context_window_source=context_window_source,
        context_window_confidence=context_window_confidence,
    )
    if settle:
        record.settle()
    return result, sent, record


def post_attempt(
    runtime: GlobalHotRuntime,
    record: FakeTransportRecord,
    *,
    session_id: str = "current-session",
    turn_id: str = "turn-1",
    api_request_id: str = "api-1",
    schema: str = "hermes.transport.v3",
):
    return runtime.post_api_request(
        session_id=session_id,
        turn_id=turn_id,
        api_request_id=api_request_id,
        transport_record=record,
        transport_schema_version=schema,
    )


class GlobalHotSourceAndCompilerTests(unittest.TestCase):
    def test_closed_source_request_then_neutral_adapter_and_compiler(self):
        source = FakeSource(
            response(
                [
                    group(
                        "oldest",
                        REFERENCE - timedelta(minutes=55),
                        "old human",
                        "old answer",
                    ),
                    group(
                        "middle",
                        REFERENCE - timedelta(minutes=25),
                        "middle human",
                        "middle answer",
                    ),
                    group(
                        "latest",
                        REFERENCE - timedelta(minutes=5),
                        "latest human",
                        "latest answer",
                    ),
                ]
            )
        )
        runtime = make_runtime(source)
        with mock.patch.object(
            runtime_module,
            "build_global_hot_context_plan",
            wraps=runtime_module.build_global_hot_context_plan,
        ) as build, mock.patch.object(
            runtime_module,
            "resolve_global_hot_context_plan",
            wraps=runtime_module.resolve_global_hot_context_plan,
        ) as resolve:
            result = project(runtime)

        self.assertIsNotNone(result)
        self.assertEqual(
            source.requests,
            [
                {
                    "schema": "continuity_canonical_window_request.v2",
                    "current_session_id": "current-session",
                    "reference_at": iso(REFERENCE),
                    "horizon_seconds": 7200,
                    "max_sessions": 16,
                    "max_groups": 64,
                    "excluded_sources": ["subagent", "tool"],
                    "allowed_source_classes": ["human", "scheduled"],
                }
            ],
        )
        self.assertEqual(build.call_count, 1)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(resolve.call_args.kwargs["max_rows"], 3)
        self.assertEqual(resolve.call_args.kwargs["max_chars"], 4000)
        rendered = result["request"]["messages"][0]["content"]
        self.assertNotIn("old human", rendered)
        self.assertIn("middle human", rendered)
        self.assertIn("latest human", rendered)
        self.assertNotIn("middle answer", rendered)
        self.assertIn("latest answer", rendered)
        self.assertEqual(rendered.count("| role=human_input |"), 2)
        self.assertEqual(rendered.count("| role=assistant_outcome |"), 1)
        self.assertEqual(rendered.count("| source_class=human |"), 3)
        plan = runtime._turns[("current-session", "turn-1")]
        self.assertIn(plan.plan_digest, plan.marker)
        self.assertIn(plan.source_revision, plan.marker)
        self.assertTrue(plan.marker.startswith("[GLOBAL HOT QUOTED REFERENCE "))
        self.assertTrue(
            plan.bridge_body.endswith("[END GLOBAL HOT QUOTED REFERENCE]")
        )

    def test_scheduled_pairs_use_neutral_roles_and_preserve_source(self):
        source = FakeSource(
            response(
                [
                    group(
                        "cron-pair",
                        REFERENCE - timedelta(minutes=20),
                        "cron human input",
                        "cron outcome",
                        source="cron",
                        source_class="scheduled",
                    ),
                    group(
                        "wake-pair",
                        REFERENCE - timedelta(minutes=2),
                        "wake human input",
                        "wake outcome",
                        source="wakeup",
                        source_class="scheduled",
                    ),
                ]
            )
        )
        result = project(make_runtime(source))

        rendered = result["request"]["messages"][0]["content"]
        self.assertIn("source=cron", rendered)
        self.assertIn("source=wakeup", rendered)
        self.assertEqual(rendered.count("| role=scheduled_input |"), 2)
        self.assertEqual(rendered.count("| role=assistant_outcome |"), 1)
        self.assertEqual(rendered.count("| source_class=scheduled |"), 3)
        self.assertIn("cron human input", rendered)
        self.assertIn("wake outcome", rendered)

    def test_multimodal_text_and_attachment_are_provider_neutral(self):
        value = group(
            "multimodal",
            REFERENCE - timedelta(minutes=1),
            "placeholder",
            "placeholder",
        )
        value["messages"] = [
            message(
                "multimodal-user",
                "user",
                [
                    {"type": "input_text", "text": "visible human text"},
                    {"type": "input_image", "image_url": "data:image/png;base64,AA"},
                ],
            ),
            message(
                "multimodal-assistant",
                "assistant",
                [{"type": "text", "text": "visible assistant text"}],
            ),
        ]

        rendered = project(make_runtime(FakeSource(response([value]))))["request"][
            "messages"
        ][0]["content"]

        self.assertIn("quoted=visible human text [attachment x1]", rendered)
        self.assertIn("quoted=visible assistant text", rendered)
        self.assertNotIn("{'type':", rendered)

    def test_projected_provider_body_has_no_private_surface_vocabulary(self):
        runtime = make_runtime(
            FakeSource(
                response(
                    [
                        group(
                            "neutral",
                            REFERENCE - timedelta(minutes=1),
                            "visible input",
                            "visible outcome",
                            source="web",
                        )
                    ]
                )
            )
        )
        projected = project(runtime)["request"]
        _result, sent, record = execute_attempt(runtime, projected)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0], record.provider_body)

        for provider_body in (sent[0], record.provider_body):
            rendered = json.dumps(provider_body, ensure_ascii=False)
            for forbidden in (
                "Aji_outcome",
                "home_gateway",
                "Home canonical",
                "home_canonical_conversation_cache",
                "asherie_mobile",
                "asheriebridge",
                "asheriehome",
            ):
                self.assertNotIn(forbidden, rendered)

    def test_source_terminal_states_are_cached_and_never_projected(self):
        cases = (
            ("empty", "no_complete_groups_in_window"),
            ("empty", "no_allowed_groups_in_window"),
            ("blocked", "candidate_source_ambiguous"),
            ("failed", "session_list_failed"),
        )
        for status, reason in cases:
            with self.subTest(status=status):
                source = FakeSource(response([], status=status, reason=reason))
                metadata = FakeMetadata()
                runtime = make_runtime(source, metadata)
                self.assertIsNone(project(runtime, api_request_id="api-1"))
                self.assertIsNone(project(runtime, api_request_id="api-2"))
                self.assertEqual(len(source.requests), 1)
                self.assertEqual(metadata.checks[-1]["status"], status)
                self.assertEqual(metadata.checks[-1]["reason"], reason)
                self.assertNotIn("content", json.dumps(metadata.checks))

    def test_invalid_closed_schema_or_body_hash_blocks_whole_window(self):
        valid = response(
            [
                group(
                    "only",
                    REFERENCE - timedelta(minutes=1),
                    "private human",
                    "private answer",
                )
            ]
        )
        invalid_values = []
        unknown_field = copy.deepcopy(valid)
        unknown_field["consumer_hint"] = "not allowed"
        invalid_values.append(unknown_field)
        forged_hash = copy.deepcopy(valid)
        forged_hash["groups"][0]["messages"][0]["content_hash"] = "f" * 64
        invalid_values.append(forged_hash)

        for value in invalid_values:
            with self.subTest(keys=list(value)):
                source = FakeSource(value)
                metadata = FakeMetadata()
                runtime = make_runtime(source, metadata)
                self.assertIsNone(project(runtime))
                self.assertEqual(metadata.checks[-1]["status"], "failed")
                self.assertEqual(
                    metadata.checks[-1]["reason"], "canonical_source_invalid"
                )
                self.assertNotIn("private human", json.dumps(metadata.checks))

    def test_closed_source_rejects_unpaired_excluded_class_current_and_over_limit_groups(self):
        assistant_only = group(
            "assistant-only",
            REFERENCE - timedelta(minutes=4),
            "hidden human",
            "orphan assistant",
        )
        assistant_only["messages"] = [assistant_only["messages"][1]]
        invalid = (
            [assistant_only],
            [
                group(
                    "excluded",
                    REFERENCE - timedelta(minutes=3),
                    "delegated private human",
                    "delegated private answer",
                    source="subagent",
                )
            ],
            [
                group(
                    "internal",
                    REFERENCE - timedelta(minutes=3),
                    "internal human-shaped input",
                    "internal outcome",
                    source="qqbot",
                    source_class="internal",
                )
            ],
            [
                group(
                    "current",
                    REFERENCE - timedelta(minutes=2),
                    "current session human",
                    "current session answer",
                    session_id="current-session",
                )
            ],
            [
                group(
                    f"group-{index:03d}",
                    REFERENCE - timedelta(minutes=1),
                    f"human {index}",
                    f"answer {index}",
                )
                for index in range(65)
            ],
        )

        for groups in invalid:
            with self.subTest(group_count=len(groups)):
                metadata = FakeMetadata()
                self.assertIsNone(project(make_runtime(FakeSource(response(groups)), metadata)))
                self.assertEqual(metadata.checks[-1]["status"], "failed")
                self.assertEqual(
                    metadata.checks[-1]["reason"], "canonical_source_invalid"
                )

    def test_owner_source_class_accepts_scheduled_and_rejects_unknown_values(self):
        scheduled = group(
            "scheduled",
            REFERENCE - timedelta(minutes=1),
            "scheduled input",
            "scheduled outcome",
            source="custom-owner-label",
            source_class="scheduled",
        )
        self.assertIsNotNone(project(make_runtime(FakeSource(response([scheduled])))))

        for source_class in (
            "delegated",
            "tool",
            "unknown",
            "owner-invented",
            "HUMAN",
            " human",
            None,
        ):
            with self.subTest(source_class=source_class):
                invalid = group(
                    "excluded-class",
                    REFERENCE - timedelta(minutes=1),
                    "hidden input",
                    "hidden outcome",
                    source="qqbot",
                    source_class=source_class,
                )
                metadata = FakeMetadata()
                self.assertIsNone(
                    project(make_runtime(FakeSource(response([invalid])), metadata))
                )
                self.assertEqual(
                    metadata.checks[-1]["reason"], "canonical_source_invalid"
                )

    def test_neutral_adapter_future_tolerance_keeps_five_minutes_not_later(self):
        at_boundary = FakeSource(
            response(
                [
                    group(
                        "future-edge",
                        REFERENCE + timedelta(minutes=5),
                        "edge human",
                        "edge answer",
                    )
                ]
            )
        )
        later = FakeSource(
            response(
                [
                    group(
                        "future-late",
                        REFERENCE + timedelta(minutes=5, seconds=1),
                        "late human",
                        "late answer",
                    )
                ]
            )
        )

        self.assertIsNotNone(project(make_runtime(at_boundary)))
        self.assertIsNone(project(make_runtime(later)))


class GlobalHotScopedExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeSource(
            response(
                [
                    group(
                        "recent",
                        REFERENCE - timedelta(minutes=1),
                        "recent human",
                        "recent answer",
                    )
                ]
            )
        )
        self.metadata = FakeMetadata()
        self.runtime = make_runtime(self.source, self.metadata)

    def execute(self, request: dict) -> list[dict]:
        _result, sent, self.record = execute_attempt(self.runtime, request)
        return sent

    def test_string_downstream_additive_block_is_preserved_and_settles(self):
        projected = project(self.runtime)["request"]
        projected["messages"][0]["content"] += "\n\n<other-middleware>keep</other-middleware>"
        projected["other_proof"] = {"status": "keep"}

        sent = self.execute(projected)
        post_attempt(self.runtime, self.record)

        self.assertEqual(sent, [projected])
        self.assertEqual(sent[0]["other_proof"], {"status": "keep"})
        self.assertIn("<other-middleware>keep", sent[0]["messages"][0]["content"])
        self.assertEqual(len(self.metadata.deliveries), 1)

    def test_list_upstream_and_downstream_blocks_are_preserved_and_settle(self):
        continuity = {
            "type": "text",
            "text": "<hermes_continuity_context>upstream</hermes_continuity_context>",
        }
        current = {"type": "text", "text": "current mouth"}
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}
        original = {
            "model": "test-model",
            "messages": [{"role": "user", "content": [continuity, current, image]}],
            "max_tokens": 512,
        }
        projected = project(self.runtime, request=original)["request"]
        downstream = {"type": "text", "text": "<other-plugin>downstream</other-plugin>"}
        projected["messages"][0]["content"].append(downstream)

        sent = self.execute(projected)
        post_attempt(self.runtime, self.record)

        parts = sent[0]["messages"][0]["content"]
        self.assertIn(continuity, parts)
        self.assertEqual(parts[-1], downstream)
        self.assertEqual(parts[1:4], [continuity, current, image])
        self.assertEqual(len(self.metadata.deliveries), 1)

    def test_original_carrier_replacement_fails_proof_and_never_settles(self):
        projected = project(self.runtime)["request"]
        plan = self.runtime._turns[("current-session", "turn-1")]
        projected["messages"][0]["content"] = (
            f"{plan.marker}\n{plan.bridge_body}\n\nreplaced current body"
        )

        sent = self.execute(projected)
        post_attempt(self.runtime, self.record)

        self.assertEqual(sent, [projected])
        self.assertIn("replaced current body", sent[0]["messages"][0]["content"])
        self.assertFalse(self.record.ambiguous)
        self.assertEqual(self.metadata.deliveries, [])
        self.assertEqual(self.metadata.checks[-1]["status"], "native")
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "execution_projection_drift"
        )

    def test_delivery_hashes_the_captured_final_provider_body(self):
        projected = project(self.runtime)["request"]

        def relay(payload):
            payload["stream"] = True
            payload["provider_only"] = {"keep": "final"}
            return payload

        _result, sent, record = execute_attempt(
            self.runtime,
            projected,
            provider_transform=relay,
        )
        post_attempt(self.runtime, record)

        self.assertEqual(sent[0], record.provider_body)
        self.assertEqual(len(self.metadata.deliveries), 1)
        self.assertEqual(
            self.metadata.deliveries[0]["request_sha256"],
            runtime_module._request_sha256(record.provider_body),
        )
        self.assertNotEqual(
            self.metadata.deliveries[0]["request_sha256"],
            runtime_module._request_sha256(projected),
        )

    def test_final_budget_guard_runs_after_expanding_transforms_in_both_orders(self):
        for order in ("transform_first", "guard_first"):
            with self.subTest(order=order):
                metadata = FakeMetadata()
                runtime = make_runtime(
                    self.source,
                    metadata,
                    estimator=lambda rows: 100,
                )
                projected = project(
                    runtime,
                    context_window_tokens=2_000,
                )["request"]
                record = FakeTransportRecord()

                def expand(body, **_estimate):
                    body["tools"] = [
                        {
                            "type": "function",
                            "function": {
                                "name": "late",
                                "description": "[LATE]" + ("x" * 20_000),
                            },
                        }
                    ]
                    return body

                def register_transform(target):
                    target.register_provider_body_filter(expand)

                before_provider = None
                if order == "transform_first":
                    register_transform(record)
                else:
                    before_provider = register_transform

                _result, sent, record = execute_attempt(
                    runtime,
                    projected,
                    record=record,
                    before_provider=before_provider,
                    context_window_tokens=2_000,
                )
                post_attempt(runtime, record)

                rendered = json.dumps(sent[0], ensure_ascii=False)
                self.assertIn("[LATE]", rendered)
                self.assertIn("current mouth", rendered)
                self.assertNotIn(runtime_module.GLOBAL_HOT_MARKER_PREFIX, rendered)
                self.assertNotIn(runtime_module.GLOBAL_HOT_END_BOUNDARY, rendered)
                self.assertEqual(metadata.deliveries, [])
                self.assertEqual(metadata.checks[-1]["status"], "native")

    def test_final_provider_body_requires_marker_body_end_and_current_anchor(self):
        def alter_marker(payload, plan):
            payload["messages"][0]["content"] = payload["messages"][0][
                "content"
            ].replace(plan.marker, "[GLOBAL HOT ALTERED]")

        def alter_body(payload, plan):
            payload["messages"][0]["content"] = payload["messages"][0][
                "content"
            ].replace(plan.bridge_body, "altered body")

        def duplicate_end(payload, _plan):
            payload["messages"][0]["content"] += (
                "\n" + runtime_module.GLOBAL_HOT_END_BOUNDARY
            )

        def alter_anchor(payload, _plan):
            payload["messages"][0]["content"] = payload["messages"][0][
                "content"
            ].replace("current mouth", "different current mouth")

        for transform in (alter_marker, alter_body, duplicate_end, alter_anchor):
            with self.subTest(transform=transform.__name__):
                metadata = FakeMetadata()
                runtime = make_runtime(self.source, metadata)
                projected = project(runtime)["request"]
                plan = runtime._turns[("current-session", "turn-1")]

                _result, _sent, record = execute_attempt(
                    runtime,
                    projected,
                    provider_transform=lambda payload, fn=transform, bound=plan: (
                        fn(payload, bound) or payload
                    ),
                )
                post_attempt(runtime, record)

                self.assertEqual(metadata.deliveries, [])
                self.assertEqual(metadata.checks[-1]["status"], "native")
                self.assertEqual(
                    metadata.checks[-1]["reason"], "execution_projection_drift"
                )

    def test_moa_transport_is_native_and_never_records_delivery(self):
        projected = project(self.runtime)["request"]
        projected["_moa_prepared_request"] = {"prepared": True}

        _result, sent, record = execute_attempt(self.runtime, projected)
        post_attempt(self.runtime, record)

        self.assertIn("_moa_prepared_request", sent[0])
        self.assertNotIn(runtime_module.GLOBAL_HOT_MARKER_PREFIX, repr(sent[0]))
        self.assertTrue(record.ambiguous)
        self.assertFalse(record.settled)
        self.assertEqual(self.metadata.deliveries, [])
        self.assertEqual(self.metadata.checks[-1]["status"], "native")

    def test_post_requires_same_settled_single_capture_transport_record(self):
        cases = (
            "wrong_record",
            "wrong_schema",
            "unsettled",
            "ambiguous",
            "second_capture",
            "mutated_body",
        )
        for case in cases:
            with self.subTest(case=case):
                metadata = FakeMetadata()
                runtime = make_runtime(self.source, metadata)
                projected = project(runtime)["request"]
                _result, _sent, record = execute_attempt(
                    runtime,
                    projected,
                    settle=case != "unsettled",
                )
                post_record = record
                post_schema = "hermes.transport.v3"
                if case == "wrong_record":
                    post_record = FakeTransportRecord()
                    post_record.mark_middleware_verified(projected)
                    post_record.capture_provider_body(projected)
                    post_record.settle()
                elif case == "wrong_schema":
                    post_schema = "hermes.transport.v0"
                elif case == "ambiguous":
                    record.ambiguous = True
                    record.settled = True
                elif case == "second_capture":
                    record.capture_provider_body(projected)
                    record.settle()
                elif case == "mutated_body":
                    record.provider_body["provider_mutation"] = True

                post_attempt(runtime, post_record, schema=post_schema)

                self.assertEqual(metadata.deliveries, [])
                self.assertEqual(metadata.checks[-1]["status"], "native")


class GlobalHotAttemptLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeSource(
            response(
                [
                    group(
                        "recent",
                        REFERENCE - timedelta(minutes=1),
                        "recent human",
                        "recent answer",
                    )
                ]
            )
        )
        self.metadata = FakeMetadata()
        self.runtime = make_runtime(self.source, self.metadata)

    def test_same_turn_retry_and_tool_followup_reuse_freeze_next_turn_rereads(self):
        first = project(self.runtime, api_request_id="api-1")
        retry = project(self.runtime, api_request_id="api-1")
        tool_followup = {
            "model": "test-model",
            "messages": [
                {"role": "user", "content": "current mouth"},
                {"role": "assistant", "content": "calling tool"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-1",
                            "content": "tool output",
                        }
                    ],
                },
            ],
            "max_tokens": 512,
        }
        followup = project(
            self.runtime,
            api_request_id="api-2",
            request=tool_followup,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(retry)
        self.assertIsNotNone(followup)
        self.assertEqual(len(self.source.requests), 1)
        self.assertEqual(
            first["request"]["messages"][0]["content"],
            retry["request"]["messages"][0]["content"],
        )
        self.assertEqual(followup["request"]["messages"][-1], tool_followup["messages"][-1])

        next_turn = project(
            self.runtime,
            turn_id="turn-2",
            api_request_id="api-3",
        )
        self.assertIsNotNone(next_turn)
        self.assertEqual(len(self.source.requests), 2)
        self.assertEqual(
            self.source.requests[0]["reference_at"],
            self.source.requests[1]["reference_at"],
        )
        self.assertIn("recent human", next_turn["request"]["messages"][0]["content"])

    def test_provider_neutral_carrier_fallback_reuses_semantic_turn_anchor(self):
        first = project(self.runtime, api_request_id="api-1")
        fallback_request = {
            "model": "test-model",
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "current mouth"}],
                }
            ],
            "max_output_tokens": 512,
        }
        fallback = project(
            self.runtime,
            api_request_id="api-2",
            request=fallback_request,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(fallback)
        self.assertEqual(len(self.source.requests), 1)
        parts = fallback["request"]["input"][0]["content"]
        self.assertTrue(parts[0]["text"].startswith("[GLOBAL HOT QUOTED REFERENCE "))
        self.assertEqual(parts[1:], fallback_request["input"][0]["content"])

    def test_attachment_payload_is_part_of_frozen_current_identity(self):
        fixtures = {
            "image_url": lambda payload: {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": payload}}
                        ],
                    }
                ],
                "max_tokens": 512,
            },
            "input_image": lambda payload: {
                "model": "test-model",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": payload}],
                    }
                ],
                "max_output_tokens": 512,
            },
            "bedrock_image": lambda payload: {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "png",
                                    "source": {"bytes": payload.encode("utf-8")},
                                }
                            }
                        ],
                    }
                ],
                "max_tokens": 512,
            },
            "document": lambda payload: {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {"bytes": payload.encode("utf-8")},
                            }
                        ],
                    }
                ],
                "max_tokens": 512,
            },
            "input_file": lambda payload: {
                "model": "test-model",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "file_data": payload.encode("utf-8"),
                            }
                        ],
                    }
                ],
                "max_output_tokens": 512,
            },
        }

        for kind, build in fixtures.items():
            with self.subTest(kind=kind):
                source = FakeSource(self.source.value)
                metadata = FakeMetadata()
                runtime = make_runtime(source, metadata, estimator=lambda rows: 100)

                first = project(runtime, request=build("payload-a"), api_request_id="a1")
                same = project(runtime, request=build("payload-a"), api_request_id="a2")
                changed = project(
                    runtime,
                    request=build("payload-b"),
                    api_request_id="a3",
                )

                self.assertIsNotNone(first)
                self.assertIsNotNone(same)
                self.assertIsNone(changed)
                self.assertEqual(metadata.checks[-1]["reason"], "current_identity_drift")
                self.assertEqual(len(source.requests), 1)

    def test_equivalent_image_wrappers_reuse_one_frozen_identity(self):
        payload = "same-image-payload"
        requests = (
            {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": payload}}
                        ],
                    }
                ],
                "max_tokens": 512,
            },
            {
                "model": "test-model",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": payload}],
                    }
                ],
                "max_output_tokens": 512,
            },
            {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "data": payload},
                            }
                        ],
                    }
                ],
                "max_tokens": 512,
            },
            {
                "model": "test-model",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "png",
                                    "source": {"bytes": payload},
                                }
                            }
                        ],
                    }
                ],
                "max_tokens": 512,
            },
        )

        for index, request in enumerate(requests, start=1):
            self.assertIsNotNone(
                project(
                    self.runtime,
                    request=request,
                    api_request_id=f"image-{index}",
                )
            )
        self.assertEqual(len(self.source.requests), 1)

    def test_visible_same_turn_continuation_projects_latest_user_and_keeps_anchor(self):
        first = project(self.runtime, api_request_id="api-1")
        continuation = {
            "model": "test-model",
            "messages": [
                {"role": "user", "content": "current mouth"},
                {"role": "assistant", "content": "I will continue."},
                {"role": "user", "content": "Continue and finish the task."},
            ],
            "max_tokens": 512,
        }
        followup = project(
            self.runtime,
            api_request_id="api-2",
            request=continuation,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(followup)
        self.assertEqual(len(self.source.requests), 1)
        self.assertEqual(
            followup["request"]["messages"][0], continuation["messages"][0]
        )
        latest = followup["request"]["messages"][-1]["content"]
        self.assertIn("[END GLOBAL HOT QUOTED REFERENCE]\n\nContinue", latest)

    def test_same_turn_without_frozen_anchor_records_visible_drift(self):
        self.assertIsNotNone(project(self.runtime, api_request_id="api-1"))
        self.assertIsNone(
            project(
                self.runtime,
                api_request_id="api-2",
                request=provider_request("replacement user only"),
            )
        )
        self.assertEqual(self.metadata.checks[-1]["status"], "failed")
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "current_identity_drift"
        )

    def test_new_turn_resolves_current_continuity_service_after_reload(self):
        active = [self.source]
        runtime = make_runtime(
            self.source,
            self.metadata,
            source_resolver=lambda: active[0],
        )
        self.assertIsNotNone(project(runtime, turn_id="turn-1", api_request_id="api-1"))

        active[0] = None
        self.assertIsNone(project(runtime, turn_id="turn-2", api_request_id="api-2"))
        self.assertEqual(self.metadata.checks[-1]["reason"], "canonical_source_invalid")

        replacement = FakeSource(self.source.value)
        active[0] = replacement
        self.assertIsNotNone(project(runtime, turn_id="turn-3", api_request_id="api-3"))
        self.assertEqual(len(self.source.requests), 1)
        self.assertEqual(len(replacement.requests), 1)

    def test_api_error_clears_attempt_without_delivery_receipt(self):
        projected = project(self.runtime)["request"]
        _result, _sent, record = execute_attempt(self.runtime, projected)
        self.runtime.api_request_error(
            session_id="current-session",
            turn_id="turn-1",
            api_request_id="api-1",
        )
        post_attempt(self.runtime, record)

        self.assertEqual(self.metadata.deliveries, [])
        self.assertNotIn(
            ("current-session", "turn-1", "api-1"), self.runtime._projections
        )
        self.assertNotIn(
            ("current-session", "turn-1", "api-1"), self.runtime._transport
        )

    def test_same_turn_missing_hooks_are_hard_capped(self):
        runtime = make_runtime(
            self.source,
            self.metadata,
            max_cached_turns=3,
        )

        projected_count = sum(
            project(runtime, api_request_id=f"api-{index}") is not None
            for index in range(5)
        )

        self.assertEqual(projected_count, 3)
        self.assertEqual(len(runtime._projections), 3)
        self.assertEqual(len(runtime._transport), 0)
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "attempt_capacity_exceeded"
        )

    def test_expired_projection_is_revoked_at_execution_and_late_post_is_noop(self):
        now = [0.0]
        runtime = make_runtime(
            self.source,
            self.metadata,
            max_cached_turns=8,
            attempt_ttl_seconds=10,
            monotonic=lambda: now[0],
        )
        projected = project(runtime)["request"]
        now[0] = 11.0

        _result, sent, record = execute_attempt(runtime, projected)
        post_attempt(runtime, record)

        self.assertEqual(sent, [provider_request()])
        self.assertEqual(self.metadata.deliveries, [])
        self.assertNotIn(
            ("current-session", "turn-1", "api-1"), runtime._projections
        )

    def test_late_post_directly_sweeps_expired_staged_attempt(self):
        now = [0.0]
        runtime = make_runtime(
            self.source,
            self.metadata,
            attempt_ttl_seconds=10,
            monotonic=lambda: now[0],
        )
        projected = project(runtime)["request"]
        _result, _sent, record = execute_attempt(runtime, projected)
        now[0] = 11.0

        post_attempt(runtime, record)

        self.assertEqual(self.metadata.deliveries, [])
        self.assertNotIn(
            ("current-session", "turn-1", "api-1"), runtime._transport
        )

    def test_executing_attempt_is_protected_from_ttl_sweep(self):
        now = [0.0]
        runtime = make_runtime(
            self.source,
            self.metadata,
            attempt_ttl_seconds=10,
            monotonic=lambda: now[0],
        )
        projected = project(runtime)["request"]
        attempt_key = ("current-session", "turn-1", "api-1")

        def sweep_while_executing(_record):
            now[0] = 11.0
            runtime.status_command()
            self.assertIn(attempt_key, runtime._projections)
            self.assertIn(attempt_key, runtime._executing)

        _result, _sent, record = execute_attempt(
            runtime,
            projected,
            before_provider=sweep_while_executing,
        )
        self.assertNotIn(attempt_key, runtime._executing)
        post_attempt(runtime, record)
        self.assertEqual(len(self.metadata.deliveries), 1)

    def test_subagent_and_codex_app_server_do_not_read_or_record(self):
        common = {
            "request": provider_request(),
            "session_id": "current-session",
            "turn_id": "turn-1",
            "api_request_id": "api-1",
        }
        self.assertIsNone(self.runtime.llm_request(**common, platform="subagent"))
        self.assertIsNone(
            self.runtime.llm_request(
                **{**common, "api_request_id": "api-2"},
                api_mode="codex_app_server",
            )
        )
        self.assertEqual(self.source.requests, [])
        self.assertEqual(self.metadata.checks, [])
        self.assertEqual(self.metadata.deliveries, [])

    def test_provider_fallback_requires_equal_or_greater_headroom(self):
        runtime = GlobalHotRuntime(
            self.source,
            self.metadata,
            clock=lambda: iso(REFERENCE),
            estimator=lambda rows: 100,
        )

        def invoke(model: str, api_request_id: str, tokens: int):
            wire = {**provider_request(), "model": model}
            return runtime.llm_request(
                request=wire,
                session_id="current-session",
                turn_id="turn-1",
                api_request_id=api_request_id,
                model=model,
                provider="openai",
                context_window_tokens=tokens,
                context_window_source="config",
                context_window_confidence="authoritative",
            )

        first = invoke("primary", "api-1", 32_000)
        self.assertIsNotNone(first)

        blocked = invoke("small", "api-2", 8_000)
        self.assertIsNone(blocked)
        self.assertEqual(self.metadata.checks[-1]["reason"], "provider_headroom_unproven")

        allowed = invoke("large", "api-3", 64_000)
        self.assertIsNotNone(allowed)
        self.assertEqual(len(self.source.requests), 1)

    def test_untrusted_host_context_stays_native_without_source_read(self):
        for tokens, source, confidence in (
            (None, "unknown", "unknown"),
            (256_000, "fallback", "fallback"),
            (256_000, "unknown", "catalog"),
        ):
            with self.subTest(tokens=tokens, source=source, confidence=confidence):
                source_service = FakeSource(self.source.value)
                metadata = FakeMetadata()
                runtime = make_runtime(source_service, metadata)
                self.assertIsNone(
                    project(
                        runtime,
                        context_window_tokens=tokens,
                        context_window_source=source,
                        context_window_confidence=confidence,
                    )
                )
                self.assertEqual(source_service.requests, [])
                self.assertEqual(
                    metadata.checks[-1]["reason"], "context_window_untrusted"
                )

    def test_catalog_context_uses_conservative_window(self):
        self.assertIsNotNone(
            project(
                self.runtime,
                context_window_tokens=10_000,
                context_window_source="model_catalog",
                context_window_confidence="catalog",
            )
        )
        plan = self.runtime._turns[("current-session", "turn-1")]
        self.assertEqual(plan.context_window_tokens, 10_000)
        self.assertEqual(plan.usable_context_window_tokens, 9_000)
        self.assertEqual(plan.context_window_confidence, "catalog")

    def test_lru_hard_cap_fails_new_active_turn_closed(self):
        runtime = GlobalHotRuntime(
            self.source,
            self.metadata,
            clock=lambda: iso(REFERENCE),
            estimator=lambda rows: 100,
            max_cached_turns=1,
        )
        self.assertIsNotNone(
            project(runtime, turn_id="turn-1", api_request_id="api-1")
        )
        self.assertIsNone(
            project(runtime, turn_id="turn-2", api_request_id="api-2")
        )
        self.assertEqual(len(runtime._turns), 1)
        self.assertEqual(self.metadata.checks[-1]["reason"], "turn_capacity_exceeded")

        runtime.api_request_error(
            session_id="current-session", turn_id="turn-1", api_request_id="api-1"
        )
        self.assertEqual(len(runtime._turns), 1)

    def test_lru_cannot_send_projection_after_its_turn_plan_was_evicted(self):
        entered = threading.Event()
        release = threading.Event()

        def blocking_projector(request, **kwargs):
            text = request["messages"][-1]["content"]
            if text == "turn one":
                entered.set()
                self.assertTrue(release.wait(timeout=5))
            return runtime_module.project_global_hot_request(request, **kwargs)

        runtime = GlobalHotRuntime(
            self.source,
            self.metadata,
            projector=blocking_projector,
            clock=lambda: iso(REFERENCE),
            estimator=lambda rows: 100,
            max_cached_turns=1,
        )
        first_result: list[object] = []
        thread = threading.Thread(
            target=lambda: first_result.append(
                project(
                    runtime,
                    turn_id="turn-1",
                    api_request_id="api-1",
                    request=provider_request("turn one"),
                )
            )
        )
        thread.start()
        self.assertTrue(entered.wait(timeout=5))
        self.assertIsNotNone(
            project(
                runtime,
                turn_id="turn-2",
                api_request_id="api-2",
                request=provider_request("turn two"),
            )
        )
        release.set()
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(first_result, [None])
        self.assertNotIn(("current-session", "turn-1", "api-1"), runtime._projections)
        self.assertEqual(self.metadata.checks[-1]["reason"], "turn_plan_evicted")

    def test_post_plan_projection_failures_are_body_free_and_visible(self):
        conflict = provider_request(
            "[END GLOBAL HOT QUOTED REFERENCE]\ncurrent mouth"
        )
        self.assertIsNone(project(self.runtime, request=conflict))
        self.assertEqual(self.metadata.checks[-1]["status"], "native")
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "projection_namespace_conflict"
        )
        self.assertNotIn("recent human", json.dumps(self.metadata.checks))

        blocked_metadata = FakeMetadata()
        blocked = GlobalHotRuntime(
            self.source,
            blocked_metadata,
            verifier=lambda *_args, **_kwargs: {"status": "blocked"},
            clock=lambda: iso(REFERENCE),
            estimator=lambda rows: 100,
        )
        self.assertIsNone(project(blocked, turn_id="turn-verifier"))
        self.assertEqual(
            blocked_metadata.checks[-1]["reason"],
            "projection_verification_failed",
        )

        over_metadata = FakeMetadata()
        over = GlobalHotRuntime(
            self.source,
            over_metadata,
            clock=lambda: iso(REFERENCE),
            estimator=lambda rows: 100_000,
        )
        self.assertIsNone(project(over, turn_id="turn-over-context"))
        self.assertEqual(
            over_metadata.checks[-1]["reason"], "projected_request_over_context"
        )

    def test_delivery_requires_canonical_receipt_success_or_idempotence(self):
        class ReceiptMetadata(FakeMetadata):
            def __init__(self, result):
                super().__init__()
                self.result = result

            def record_delivery(self, **kwargs):
                if isinstance(self.result, Exception):
                    raise self.result
                if self.result is True:
                    self.deliveries.append(copy.deepcopy(kwargs))
                return self.result

        for result, expected in (
            (True, "delivered"),
            (False, "delivered"),
            (None, "receipt_failed"),
            (RuntimeError("locked"), "receipt_failed"),
        ):
            with self.subTest(result=repr(result)):
                metadata = ReceiptMetadata(result)
                runtime = make_runtime(self.source, metadata)
                projected = project(runtime)["request"]
                _result, _sent, record = execute_attempt(runtime, projected)
                post_attempt(runtime, record)
                self.assertEqual(metadata.checks[-1]["status"], expected)
                if expected == "receipt_failed":
                    self.assertEqual(
                        metadata.checks[-1]["reason"],
                        "canonical_receipt_unavailable",
                    )


if __name__ == "__main__":
    unittest.main()
