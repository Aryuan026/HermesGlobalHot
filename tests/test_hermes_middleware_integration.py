from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "hermes_global_hot_middleware_integration"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package

runtime_module = importlib.import_module(f"{PACKAGE}.runtime")
GlobalHotRuntime = runtime_module.GlobalHotRuntime
SOURCE_SERVICE_KEY = runtime_module.SOURCE_SERVICE_KEY
GlobalHotMetadataStore = importlib.import_module(
    f"{PACKAGE}.metadata"
).GlobalHotMetadataStore

CONTINUITY_ROOT_VALUE = os.environ.get("HERMES_CONTINUITY_ROOT", "")
CONTINUITY_ROOT = Path(CONTINUITY_ROOT_VALUE)
CONTINUITY_AVAILABLE = (
    bool(CONTINUITY_ROOT_VALUE) and (CONTINUITY_ROOT / "runtime.py").is_file()
)
if CONTINUITY_AVAILABLE:
    CONTINUITY_PACKAGE = "hermes_continuity_global_hot_integration"
    if CONTINUITY_PACKAGE not in sys.modules:
        continuity_package = types.ModuleType(CONTINUITY_PACKAGE)
        continuity_package.__path__ = [str(CONTINUITY_ROOT)]
        sys.modules[CONTINUITY_PACKAGE] = continuity_package
    continuity_runtime_module = importlib.import_module(f"{CONTINUITY_PACKAGE}.runtime")
    ContinuityRuntime = continuity_runtime_module.ContinuityRuntime

HERMES_ROOT_VALUE = os.environ.get("HERMES_SOURCE_ROOT", "")
HERMES_ROOT = Path(HERMES_ROOT_VALUE)
HERMES_AVAILABLE = (
    bool(HERMES_ROOT_VALUE) and (HERMES_ROOT / "hermes_cli" / "middleware.py").is_file()
)
if HERMES_AVAILABLE:
    sys.path.insert(0, str(HERMES_ROOT))
    from agent import relay_llm
    from hermes_cli import plugins as hermes_plugins
    from hermes_cli.lifecycle import invoke_hook
    from hermes_cli.middleware import (
        TRANSPORT_SCHEMA_VERSION,
        TransportRecord,
        apply_llm_request_middleware,
        run_llm_execution_middleware,
        transport_record_scope,
    )
    from hermes_cli.plugins import (
        PluginContext,
        PluginManager,
        PluginManifest,
    )
if HERMES_AVAILABLE and CONTINUITY_AVAILABLE:
    continuity_adapter_module = importlib.import_module(
        f"{CONTINUITY_PACKAGE}.hermes_adapter"
    )
    ContinuityMetadataStore = continuity_adapter_module.ContinuityMetadataStore


REFERENCE_AT = "2026-08-30T12:00:00+00:00"
CONTINUITY_BLOCK = (
    "<hermes_continuity_context>synthetic upstream</hermes_continuity_context>"
)
DOWNSTREAM_BLOCK = "<synthetic_downstream>additive</synthetic_downstream>"
GLOBAL_HOT_PREFIX = "[GLOBAL HOT QUOTED REFERENCE "


def _continuity_checkpoint(revision: int, body: str) -> dict:
    return {
        "schema": "thread_continuity_checkpoint.v2",
        "revision": revision,
        "recent_bridge": {
            "schema": "thread_continuity_recent_bridge.v1",
            "status": "ready",
            "relation": "represented_in_recent_bridge",
            "source_group_ids": ["synthetic-source-group"],
            "source_group_fingerprints": ["f" * 64],
            "source_slice_fingerprint": "d" * 64,
            "reference_at": REFERENCE_AT,
            "recent_horizon_hours": 72,
            "source_token_limit": 24_000,
            "output_token_limit": 2_048,
            "body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
    }


OLD_CONTINUITY_CHECKPOINT = _continuity_checkpoint(1, "synthetic old bridge")
CANDIDATE_CONTINUITY_CHECKPOINT = _continuity_checkpoint(
    2, "synthetic candidate bridge"
)


def _message(message_id: str, role: str, content: str) -> dict:
    return {
        "message_id": message_id,
        "role": role,
        "content": content,
        "content_hash": runtime_module._content_hash(content),
    }


def _source_response(reference_at: str) -> dict:
    return {
        "schema": "continuity_canonical_window_response.v2",
        "status": "ready",
        "reason": "",
        "reference_at": reference_at,
        "horizon_seconds": 7200,
        "source_revision": "a" * 64,
        "scan_complete": True,
        "groups": [
            {
                "source_session_id": "synthetic-source-session",
                "source": "qqbot",
                "source_class": "human",
                "source_snapshot": "b" * 64,
                "group_id": "synthetic-complete-pair",
                "effective_event_at": "2026-08-30T11:58:00+00:00",
                "messages": [
                    _message("synthetic-user", "user", "synthetic prior human"),
                    _message(
                        "synthetic-assistant",
                        "assistant",
                        "synthetic prior outcome",
                    ),
                ],
            }
        ],
        "trace": {
            "schema": "continuity_canonical_window_trace.v2",
            "listed_session_count": 1,
            "candidate_session_count": 1,
            "source_session_count": 1,
            "returned_group_count": 1,
            "outside_horizon_session_count": 0,
            "outside_horizon_group_count": 0,
            "current_lineage_excluded_count": 1,
            "policy_excluded_group_count": 0,
            "session_proofs_sha256": "c" * 64,
            "group_proofs_sha256": "d" * 64,
            "body_included": False,
        },
    }


class _Source:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def read_window(self, request: dict) -> dict:
        self.requests.append(copy.deepcopy(request))
        return _source_response(request["reference_at"])


class _Metadata:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.deliveries: list[dict] = []

    def record_check(self, **kwargs) -> None:
        self.checks.append(copy.deepcopy(kwargs))

    def record_delivery(self, **kwargs) -> bool:
        self.deliveries.append(copy.deepcopy(kwargs))
        return True


class _ContinuityMetadata:
    def __init__(self) -> None:
        self.receipts: list[dict] = []

    def record_receipt(self, **kwargs) -> None:
        self.receipts.append(copy.deepcopy(kwargs))


class _ContinuityAdapter:
    def __init__(self) -> None:
        self.metadata_store = _ContinuityMetadata()
        self.cas_calls: list[dict] = []

    def read_bundle(self, session_id: str) -> dict:
        return {
            "source": {
                "status": "ready",
                "groups": [],
                "source_snapshot": "e" * 64,
                "scan_complete": True,
                "stats": {
                    "full_prefix": True,
                    "compacted_prefix_group_ids": [],
                },
            },
            "continuity": {
                "status": "ready",
                "state": {
                    "revision": 1,
                    "checkpoint": copy.deepcopy(OLD_CONTINUITY_CHECKPOINT),
                },
            },
        }

    def compare_and_swap_checkpoint(self, session_id: str, **kwargs) -> dict:
        self.cas_calls.append({"session_id": session_id, **copy.deepcopy(kwargs)})
        return {"ok": True, "status": "applied"}

    def settle_checkpoint_delivery(self, session_id: str, **kwargs) -> dict:
        self.cas_calls.append(
            {
                "session_id": session_id,
                "expected_revision": kwargs["expected_revision"],
                "expected_source_snapshot": kwargs["expected_source_snapshot"],
                "checkpoint_candidate": copy.deepcopy(
                    kwargs["checkpoint_candidate"]
                ),
            }
        )
        self.metadata_store.record_receipt(
            receipt_id=kwargs["receipt_id"],
            session_id=session_id,
            kind="delivery",
            status="delivered_checkpoint_applied",
            source_ids=kwargs.get("source_ids", ()),
            hashes=kwargs.get("hashes", {}),
            counts=kwargs.get("counts", {}),
        )
        return {"ok": True, "status": "applied", "receipt_recorded": True}


class _ContinuityCompiler:
    async def __call__(self, _bundle, **_kwargs) -> dict:
        return {
            "status": "ready",
            "checkpoint_candidate": copy.deepcopy(
                CANDIDATE_CONTINUITY_CHECKPOINT
            ),
            "expected_revision": 1,
            "expected_pre_turn_source_snapshot": "e" * 64,
        }


class _Llm:
    async def acomplete(self, *_args, **_kwargs):
        raise AssertionError("the synthetic compiler must not call the provider")


def _ctx(manager, plugin_id: str):
    return PluginContext(
        PluginManifest(name=plugin_id, key=plugin_id),
        manager,
    )


def _request() -> dict:
    return {
        "model": "test-model",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "synthetic fixed prompt"},
            {"role": "user", "content": "synthetic current turn"},
        ],
    }


def _tool_followup_request() -> dict:
    return {
        "model": "test-model",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "synthetic fixed prompt"},
            {"role": "user", "content": "synthetic current turn"},
            {"role": "assistant", "content": "synthetic tool call"},
            {"role": "tool", "content": "synthetic tool result"},
        ],
    }


def _context(
    *,
    turn_id: str = "turn-1",
    api_request_id: str = "api-1",
    context_window_tokens: int = 32_000,
) -> dict:
    return {
        "session_id": "current-session",
        "turn_id": turn_id,
        "api_request_id": api_request_id,
        "model": "test-model",
        "provider": "openai",
        "base_url": "https://provider.invalid",
        "api_mode": "chat_completions",
        "platform": "cli",
        "context_window_tokens": context_window_tokens,
        "context_window_source": "config",
        "context_window_confidence": "authoritative",
    }


@unittest.skipUnless(HERMES_AVAILABLE, "set HERMES_SOURCE_ROOT to a Hermes 0.20.5 tree")
class HermesMiddlewareIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.manager = PluginManager(scope_key=self.temp.name)
        self.manager._discovered = True
        self.manager_patch = mock.patch.object(
            hermes_plugins,
            "get_plugin_manager",
            return_value=self.manager,
        )
        self.manager_patch.start()

        self.source = _Source()
        self.metadata = _Metadata()
        self.provider_ctx = _ctx(self.manager, "hermes-continuity")
        self.consumer_ctx = _ctx(self.manager, "hermes-global-hot")
        self.provider_ctx.register_service("canonical-source.v2", self.source)
        resolved = self.consumer_ctx.get_service(SOURCE_SERVICE_KEY)
        self.assertIs(resolved, self.source)
        self.runtime = GlobalHotRuntime(
            resolved,
            self.metadata,
            source_resolver=lambda: self.consumer_ctx.get_service(SOURCE_SERVICE_KEY),
            clock=lambda: REFERENCE_AT,
            estimator=lambda messages: len(json.dumps(messages)) // 4,
        )

        self.callback_order: list[str] = []
        upstream_ctx = _ctx(self.manager, "synthetic-continuity")
        downstream_ctx = _ctx(self.manager, "synthetic-downstream")
        upstream_ctx.register_middleware("llm_request", self._upstream)
        self.consumer_ctx.register_middleware("llm_request", self.runtime.llm_request)
        downstream_ctx.register_middleware("llm_request", self._downstream)
        self.consumer_ctx.register_middleware(
            "llm_execution", self.runtime.llm_execution
        )
        self.consumer_ctx.register_hook(
            "post_api_request", self.runtime.post_api_request
        )
        self.consumer_ctx.register_hook(
            "api_request_error", self.runtime.api_request_error
        )
        self.transport_records: dict[str, object] = {}

    def tearDown(self) -> None:
        self.manager.unload()
        self.manager_patch.stop()
        self.temp.cleanup()

    def _upstream(
        self,
        *,
        request,
        original_request,
        middleware_schema_version,
        **_kwargs,
    ):
        self.callback_order.append("continuity")
        self.assertEqual(middleware_schema_version, "hermes.middleware.v2")
        self.assertNotIn(CONTINUITY_BLOCK, json.dumps(original_request))
        messages = request["messages"]
        index = next(
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "user"
        )
        messages[index] = {
            **messages[index],
            "content": f"{CONTINUITY_BLOCK}\n\n{messages[index]['content']}",
        }
        return {"request": request, "source": "synthetic-continuity"}

    def _downstream(
        self,
        *,
        request,
        original_request,
        middleware_schema_version,
        **_kwargs,
    ):
        self.callback_order.append("downstream")
        self.assertEqual(middleware_schema_version, "hermes.middleware.v2")
        self.assertNotIn(GLOBAL_HOT_PREFIX, json.dumps(original_request))
        messages = request["messages"]
        index = next(
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "user"
        )
        messages[index] = {
            **messages[index],
            "content": f"{messages[index]['content']}\n\n{DOWNSTREAM_BLOCK}",
        }
        return {"request": request, "source": "synthetic-downstream"}

    def _project(self, request: dict, **context_overrides):
        context = _context(**context_overrides)
        result = apply_llm_request_middleware(request, **context)
        self.assertEqual(
            result.trace,
            [
                {"source": "synthetic-continuity"},
                {
                    "source": "hermes-global-hot",
                    "reason": "nearfield_projected",
                },
                {"source": "synthetic-downstream"},
            ],
        )
        return context, result

    def assert_blocks_once(self, request: dict) -> None:
        text = json.dumps(request, ensure_ascii=False)
        self.assertEqual(text.count(CONTINUITY_BLOCK), 1)
        self.assertEqual(text.count(GLOBAL_HOT_PREFIX), 1)
        self.assertEqual(text.count(DOWNSTREAM_BLOCK), 1)

    def _execute(self, projected, context, provider, *, provider_transform=None):
        record = TransportRecord()

        def terminal(request):
            record.mark_middleware_verified(request)
            provider_body = (
                provider_transform(copy.deepcopy(request))
                if provider_transform is not None
                else request
            )
            with transport_record_scope(record):
                return relay_llm.call_provider_body(
                    lambda **body: provider(body),
                    provider_body,
                )

        response = run_llm_execution_middleware(
            projected.payload,
            terminal,
            original_request=projected.original_payload,
            transport_record=record,
            **context,
        )
        record.settle()
        self.transport_records[context["api_request_id"]] = record
        return response

    def _post(self, context, *, record=None):
        record = record or self.transport_records[context["api_request_id"]]
        invoke_hook(
            "post_api_request",
            transport_record=record,
            transport_schema_version=TRANSPORT_SCHEMA_VERSION,
            **context,
        )

    def test_sequential_projection_execution_and_post_receipt(self) -> None:
        original = _request()
        original_roles = [message["role"] for message in original["messages"]]
        context, projected = self._project(original)

        self.assertEqual(self.callback_order, ["continuity", "downstream"])
        self.assertEqual(projected.original_payload, original)
        self.assertEqual(
            [message["role"] for message in projected.payload["messages"]],
            original_roles,
        )
        self.assert_blocks_once(projected.payload)

        provider_requests: list[dict] = []
        response = self._execute(
            projected,
            context,
            lambda request: (
                provider_requests.append(copy.deepcopy(request)) or {"ok": True}
            ),
            provider_transform=lambda request: {**request, "stream": True},
        )

        self.assertEqual(response, {"ok": True})
        self.assertEqual(len(provider_requests), 1)
        self.assert_blocks_once(provider_requests[0])
        provider_text = json.dumps(provider_requests[0], ensure_ascii=False)
        for forbidden in (
            "Aji_outcome",
            "home_gateway",
            "Home canonical",
            "home_canonical_conversation_cache",
            "asherie_mobile",
            "asheriebridge",
            "asheriehome",
        ):
            self.assertNotIn(forbidden, provider_text)
        self.assertEqual(self.metadata.deliveries, [])

        self._post(context)
        self._post(context)
        self.assertEqual(len(self.metadata.deliveries), 1)
        record = self.transport_records[context["api_request_id"]]
        self.assertEqual(
            self.metadata.deliveries[0]["request_sha256"],
            runtime_module._request_sha256(record.provider_body),
        )
        metadata_text = json.dumps(
            {"checks": self.metadata.checks, "deliveries": self.metadata.deliveries}
        )
        for body in (
            "synthetic prior human",
            "synthetic prior outcome",
            "synthetic current turn",
            CONTINUITY_BLOCK,
            DOWNSTREAM_BLOCK,
        ):
            self.assertNotIn(body, metadata_text)

    def test_retry_error_tool_followup_and_next_turn_source_reads(self) -> None:
        _first_context, first = self._project(_request())
        self.assert_blocks_once(first.payload)
        invoke_hook("api_request_error", **_context())

        _retry_context, retry = self._project(_request())
        self.assert_blocks_once(retry.payload)
        self.assertEqual(len(self.source.requests), 1)

        _tool_context, tool_followup = self._project(
            _tool_followup_request(), api_request_id="api-2"
        )
        self.assert_blocks_once(tool_followup.payload)
        self.assertEqual(
            [message["role"] for message in tool_followup.payload["messages"]],
            ["system", "user", "assistant", "tool"],
        )
        self.assertEqual(len(self.source.requests), 1)

        _next_context, next_turn = self._project(
            _request(), turn_id="turn-2", api_request_id="api-3"
        )
        self.assert_blocks_once(next_turn.payload)
        self.assertEqual(len(self.source.requests), 2)
        self.assertTrue(
            all("cursor" not in request for request in self.source.requests)
        )
        self.assertEqual(self.metadata.deliveries, [])

    def test_drift_and_missing_post_never_create_receipt(self) -> None:
        no_post_context, no_post = self._project(_request())
        provider_requests: list[dict] = []
        self._execute(
            no_post,
            no_post_context,
            lambda request: (
                provider_requests.append(copy.deepcopy(request)) or {"ok": True}
            ),
        )
        self.assertEqual(len(provider_requests), 1)
        self.assertEqual(self.metadata.deliveries, [])

        drift_context, drift = self._project(_request(), api_request_id="api-2")
        drifted = copy.deepcopy(drift.payload)
        plan = self.runtime._turns[("current-session", "turn-1")]
        drifted["messages"][1]["content"] = drifted["messages"][1]["content"].replace(
            plan.bridge_body, "synthetic drift"
        )
        drift_result = types.SimpleNamespace(
            payload=drifted,
            original_payload=drift.original_payload,
        )
        self._execute(
            drift_result,
            drift_context,
            lambda request: (
                provider_requests.append(copy.deepcopy(request)) or {"ok": True}
            ),
        )
        self._post(drift_context)

        self.assertEqual(len(provider_requests), 2)
        self.assertEqual(self.metadata.deliveries, [])
        self.assertEqual(self.metadata.checks[-1]["status"], "native")
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "execution_projection_drift"
        )

    def test_real_moa_transport_fails_open_without_delivery(self) -> None:
        context, projected = self._project(_request())
        moa_payload = copy.deepcopy(projected.payload)
        moa_payload["_moa_prepared_request"] = {"prepared": True}
        moa_result = types.SimpleNamespace(
            payload=moa_payload,
            original_payload=projected.original_payload,
        )
        provider_requests: list[dict] = []

        response = self._execute(
            moa_result,
            context,
            lambda request: (
                provider_requests.append(copy.deepcopy(request)) or {"ok": True}
            ),
        )
        record = self.transport_records[context["api_request_id"]]
        self._post(context)

        self.assertEqual(response, {"ok": True})
        self.assertEqual(len(provider_requests), 1)
        self.assertNotIn(GLOBAL_HOT_PREFIX, json.dumps(provider_requests[0]))
        self.assertIn(CONTINUITY_BLOCK, json.dumps(provider_requests[0]))
        self.assertTrue(record.ambiguous)
        self.assertFalse(record.settled)
        self.assertEqual(self.metadata.deliveries, [])
        self.assertEqual(self.metadata.checks[-1]["status"], "native")
        self.assertEqual(
            self.metadata.checks[-1]["reason"], "execution_projection_drift"
        )

    def test_final_guard_runs_after_late_expansion_in_both_execution_orders(self):
        late_ctx = _ctx(self.manager, "synthetic-late-transform")

        def late_execution(*, request, next_call, transport_record, **_kwargs):
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

            transport_record.register_provider_body_filter(expand)
            return next_call(request)

        late_ctx.register_middleware("llm_execution", late_execution)
        global_hot_callback, late_callback = self.manager._middleware[
            "llm_execution"
        ]
        global_hot_owner, late_owner = self.manager._middleware_owners[
            "llm_execution"
        ]

        for index, order in enumerate(("transform_first", "guard_first"), start=1):
            with self.subTest(order=order):
                if order == "transform_first":
                    callbacks = [late_callback, global_hot_callback]
                    owners = [late_owner, global_hot_owner]
                    expected_phases = ("transform", "final_guard")
                else:
                    callbacks = [global_hot_callback, late_callback]
                    owners = [global_hot_owner, late_owner]
                    expected_phases = ("final_guard", "transform")
                self.manager._middleware["llm_execution"] = callbacks
                self.manager._middleware_owners["llm_execution"] = owners

                context, projected = self._project(
                    _request(),
                    turn_id=f"turn-guard-{index}",
                    api_request_id=f"api-guard-{index}",
                    context_window_tokens=2_000,
                )
                provider_requests: list[dict] = []
                self._execute(
                    projected,
                    context,
                    lambda request: (
                        provider_requests.append(copy.deepcopy(request))
                        or {"ok": True}
                    ),
                )
                record = self.transport_records[context["api_request_id"]]
                self._post(context, record=record)

                self.assertEqual(len(provider_requests), 1)
                rendered = json.dumps(provider_requests[0], ensure_ascii=False)
                self.assertIn("[LATE]", rendered)
                self.assertIn(CONTINUITY_BLOCK, rendered)
                self.assertIn(DOWNSTREAM_BLOCK, rendered)
                self.assertNotIn(GLOBAL_HOT_PREFIX, rendered)
                self.assertEqual(record.provider_body_filter_phases, expected_phases)
                self.assertEqual(record.capture_count, 1)
                self.assertTrue(record.settled)
                self.assertFalse(record.ambiguous)
                self.assertEqual(self.metadata.deliveries, [])
                self.assertEqual(self.metadata.checks[-1]["status"], "native")

    def test_qualified_service_constructs_runtime_and_owner_unload_removes_it(
        self,
    ) -> None:
        self.assertIs(self.runtime.source_resolver(), self.source)
        self.assertIs(self.consumer_ctx.get_service(SOURCE_SERVICE_KEY), self.source)

        self.assertTrue(self.manager.unload("hermes-continuity"))
        self.assertIsNone(self.consumer_ctx.get_service(SOURCE_SERVICE_KEY))

        unavailable = apply_llm_request_middleware(
            _request(), **_context(turn_id="turn-2", api_request_id="api-2")
        )
        self.assertNotIn(GLOBAL_HOT_PREFIX, json.dumps(unavailable.payload))
        self.assertEqual(self.metadata.checks[-1]["reason"], "canonical_source_invalid")

        replacement = _Source()
        self.provider_ctx.register_service("canonical-source.v2", replacement)
        recovered = apply_llm_request_middleware(
            _request(), **_context(turn_id="turn-3", api_request_id="api-3")
        )
        self.assertEqual(json.dumps(recovered.payload).count(GLOBAL_HOT_PREFIX), 1)
        self.assertEqual(len(replacement.requests), 1)


@unittest.skipUnless(
    HERMES_AVAILABLE and CONTINUITY_AVAILABLE,
    "set HERMES_SOURCE_ROOT and HERMES_CONTINUITY_ROOT to real source trees",
)
class DualRuntimeMiddlewareIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.manager = PluginManager(scope_key=self.temp.name)
        self.manager._discovered = True
        self.manager_patch = mock.patch.object(
            hermes_plugins,
            "get_plugin_manager",
            return_value=self.manager,
        )
        self.manager_patch.start()

        self.adapter = _ContinuityAdapter()
        self.continuity = ContinuityRuntime(
            self.adapter,
            _Llm(),
            compiler=_ContinuityCompiler(),
            clock=lambda: REFERENCE_AT,
            estimator=lambda messages: len(json.dumps(messages)) // 4,
        )
        self.source = _Source()
        self.global_hot_metadata = _Metadata()
        continuity_ctx = _ctx(self.manager, "hermes-continuity")
        global_hot_ctx = _ctx(self.manager, "hermes-global-hot")
        continuity_ctx.register_service("canonical-source.v2", self.source)
        source_service = global_hot_ctx.get_service(SOURCE_SERVICE_KEY)
        self.global_hot = GlobalHotRuntime(
            source_service,
            self.global_hot_metadata,
            clock=lambda: REFERENCE_AT,
            estimator=lambda messages: len(json.dumps(messages)) // 4,
        )

        continuity_ctx.register_middleware("llm_request", self.continuity.llm_request)
        global_hot_ctx.register_middleware("llm_request", self.global_hot.llm_request)
        continuity_ctx.register_middleware(
            "llm_execution", self.continuity.llm_execution
        )
        global_hot_ctx.register_middleware(
            "llm_execution", self.global_hot.llm_execution
        )
        continuity_ctx.register_hook(
            "post_api_request", self.continuity.post_api_request
        )
        global_hot_ctx.register_hook(
            "post_api_request", self.global_hot.post_api_request
        )

    def tearDown(self) -> None:
        self.manager.unload()
        self.manager_patch.stop()
        self.temp.cleanup()

    def test_real_metadata_stores_reject_shared_path_in_both_load_orders(self):
        for first in ("continuity", "global_hot"):
            with self.subTest(first=first):
                path = Path(self.temp.name) / f"{first}-first.sqlite3"
                if first == "continuity":
                    ContinuityMetadataStore(path)
                    with self.assertRaisesRegex(ValueError, "owner_conflict"):
                        GlobalHotMetadataStore(path)
                    forbidden = {
                        "global_hot_checks",
                        "global_hot_delivery_receipts",
                    }
                else:
                    GlobalHotMetadataStore(path)
                    with self.assertRaisesRegex(ValueError, "owner_conflict"):
                        ContinuityMetadataStore(path)
                    forbidden = {"continuity_checkpoints", "continuity_receipts"}
                with sqlite3.connect(path) as connection:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        )
                    }
                self.assertTrue(tables.isdisjoint(forbidden))

    def test_two_real_runtime_wrappers_stage_and_settle_one_provider_call(self) -> None:
        context = _context()
        projected = apply_llm_request_middleware(_request(), **context)
        self.assertEqual(
            projected.trace,
            [
                {"source": "hermes-continuity", "reason": "bridge_projected"},
                {
                    "source": "hermes-global-hot",
                    "reason": "nearfield_projected",
                },
            ],
        )
        rendered = json.dumps(projected.payload, ensure_ascii=False)
        self.assertEqual(
            rendered.count(continuity_runtime_module.CONTINUITY_MARKER_NAMESPACE),
            1,
        )
        self.assertEqual(rendered.count(GLOBAL_HOT_PREFIX), 1)

        provider_requests: list[dict] = []
        record = TransportRecord()

        def terminal(request):
            record.mark_middleware_verified(request)
            provider_body = {**copy.deepcopy(request), "stream": True}
            with transport_record_scope(record):
                return relay_llm.call_provider_body(
                    lambda **body: (
                        provider_requests.append(copy.deepcopy(body))
                        or {"ok": True}
                    ),
                    provider_body,
                )

        response = run_llm_execution_middleware(
            projected.payload,
            terminal,
            original_request=projected.original_payload,
            transport_record=record,
            **context,
        )
        record.settle()

        attempt_key = ("current-session", "turn-1", "api-1")
        self.assertEqual(response, {"ok": True})
        self.assertEqual(len(provider_requests), 1)
        provider_rendered = json.dumps(provider_requests[0], ensure_ascii=False)
        self.assertEqual(
            provider_rendered.count(
                continuity_runtime_module.CONTINUITY_MARKER_NAMESPACE
            ),
            1,
        )
        self.assertEqual(provider_rendered.count(GLOBAL_HOT_PREFIX), 1)
        self.assertIn(attempt_key, self.continuity._transport)
        self.assertIn(attempt_key, self.global_hot._transport)
        self.assertEqual(self.adapter.cas_calls, [])
        self.assertEqual(self.adapter.metadata_store.receipts, [])
        self.assertEqual(self.global_hot_metadata.deliveries, [])

        invoke_hook(
            "post_api_request",
            transport_record=record,
            transport_schema_version=TRANSPORT_SCHEMA_VERSION,
            **context,
        )
        invoke_hook(
            "post_api_request",
            transport_record=record,
            transport_schema_version=TRANSPORT_SCHEMA_VERSION,
            **context,
        )
        self.assertEqual(len(self.adapter.cas_calls), 1)
        self.assertEqual(len(self.adapter.metadata_store.receipts), 1)
        self.assertEqual(len(self.global_hot_metadata.deliveries), 1)
        self.assertEqual(
            self.adapter.metadata_store.receipts[0]["hashes"]["request_sha256"],
            continuity_runtime_module._request_sha256(record.provider_body),
        )
        self.assertEqual(
            self.global_hot_metadata.deliveries[0]["request_sha256"],
            runtime_module._request_sha256(record.provider_body),
        )

        body_free = json.dumps(
            {
                "continuity": self.adapter.metadata_store.receipts,
                "global_hot": self.global_hot_metadata.deliveries,
            },
            ensure_ascii=False,
        )
        for body in (
            "synthetic candidate bridge",
            "synthetic prior human",
            "synthetic prior outcome",
            "synthetic current turn",
        ):
            self.assertNotIn(body, body_free)

    def test_global_hot_drift_does_not_poison_continuity_transport(self) -> None:
        context = _context()
        projected = apply_llm_request_middleware(_request(), **context)
        plan = self.global_hot._turns[("current-session", "turn-1")]
        drifted = copy.deepcopy(projected.payload)
        drifted["messages"][1]["content"] = drifted["messages"][1][
            "content"
        ].replace(plan.bridge_body, "synthetic global-hot drift")

        record = TransportRecord()
        provider_requests: list[dict] = []

        def terminal(request):
            record.mark_middleware_verified(request)
            with transport_record_scope(record):
                return relay_llm.call_provider_body(
                    lambda **body: (
                        provider_requests.append(copy.deepcopy(body))
                        or {"ok": True}
                    ),
                    request,
                )

        response = run_llm_execution_middleware(
            drifted,
            terminal,
            original_request=projected.original_payload,
            transport_record=record,
            **context,
        )
        record.settle()

        attempt_key = ("current-session", "turn-1", "api-1")
        self.assertEqual(response, {"ok": True})
        self.assertEqual(len(provider_requests), 1)
        self.assertFalse(record.ambiguous)
        self.assertIn(attempt_key, self.continuity._transport)
        self.assertNotIn(attempt_key, self.global_hot._transport)

        invoke_hook(
            "post_api_request",
            transport_record=record,
            transport_schema_version=TRANSPORT_SCHEMA_VERSION,
            **context,
        )
        self.assertEqual(len(self.adapter.cas_calls), 1)
        self.assertEqual(len(self.adapter.metadata_store.receipts), 1)
        self.assertEqual(self.global_hot_metadata.deliveries, [])


if __name__ == "__main__":
    unittest.main()
