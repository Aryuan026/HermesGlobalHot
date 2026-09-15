"""Global Hot H13 selection proof against the accepted Hermes 0.21 host.

The test starts from real SessionDB rows, loads both public plugins through
PluginManager discovery, and captures the final provider body.  It does not
call a network provider or write outside a disposable Hermes profile.
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


GLOBAL_HOT_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT_VALUE = os.environ.get("HERMES_SOURCE_ROOT", "").strip()
CONTINUITY_ROOT_VALUE = os.environ.get("HERMES_CONTINUITY_ROOT", "").strip()
HERMES_ROOT = Path(HERMES_ROOT_VALUE)
CONTINUITY_ROOT = Path(CONTINUITY_ROOT_VALUE)
MESSAGE_ORIGIN_PATH = HERMES_ROOT / "agent" / "message_origin.py"
CONTINUITY_MANIFEST_PATH = CONTINUITY_ROOT / "plugin.yaml"
HOST_AVAILABLE = (
    bool(HERMES_ROOT_VALUE and CONTINUITY_ROOT_VALUE)
    and MESSAGE_ORIGIN_PATH.is_file()
    and (HERMES_ROOT / "hermes_cli" / "middleware.py").is_file()
    and (CONTINUITY_ROOT / "hermes_adapter.py").is_file()
    and CONTINUITY_MANIFEST_PATH.is_file()
    and "def classify_message_origin_group"
    in MESSAGE_ORIGIN_PATH.read_text(encoding="utf-8")
    and "version: 0.5.0" in CONTINUITY_MANIFEST_PATH.read_text(encoding="utf-8")
)

if HOST_AVAILABLE:
    sys.path.insert(0, str(HERMES_ROOT))
    from agent import relay_llm
    from agent.message_origin import (
        GATEWAY_INTERNAL,
        GATEWAY_USER,
        GATEWAY_WAKEUP,
        SUBAGENT,
        build_message_origin_proof,
    )
    from hermes_cli import config as hermes_config
    from hermes_cli import plugins
    from hermes_cli.lifecycle import invoke_hook
    from hermes_cli.middleware import (
        TRANSPORT_SCHEMA_VERSION,
        TransportRecord,
        apply_llm_request_middleware,
        run_llm_execution_middleware,
        transport_record_scope,
    )
    from hermes_state import SessionDB


GLOBAL_HOT_PREFIX = "[GLOBAL HOT QUOTED REFERENCE "


@unittest.skipUnless(
    HOST_AVAILABLE,
    "set HERMES_SOURCE_ROOT and HERMES_CONTINUITY_ROOT to accepted 0.21 trees",
)
class RealHost021GlobalHotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name) / ".hermes"
        plugin_dir = self.home / "plugins"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "hermes-continuity").symlink_to(
            CONTINUITY_ROOT, target_is_directory=True
        )
        (plugin_dir / "hermes-global-hot").symlink_to(
            GLOBAL_HOT_ROOT, target_is_directory=True
        )
        (self.home / "config.yaml").write_text(
            "plugins:\n  enabled:\n    - hermes-continuity\n    - hermes-global-hot\n",
            encoding="utf-8",
        )
        self.env = patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        self.env.start()
        hermes_config._config_cache = None
        plugins._reset_plugin_managers_for_tests()

        self.session_db = SessionDB(self.home / "state.db")
        self.session_db.create_session("current-mouth", "qqbot")
        self.session_db.create_session("mixed-bot-chat", "qqbot")
        base = time.time()
        rows = (
            (
                "actual wakeup input",
                "actual wakeup outcome",
                build_message_origin_proof(GATEWAY_WAKEUP),
                base - 90,
            ),
            (
                "internal notice must stay out",
                "internal outcome must stay out",
                build_message_origin_proof(GATEWAY_INTERNAL),
                base - 70,
            ),
            (
                "delegated result must stay out",
                "delegated outcome must stay out",
                build_message_origin_proof(SUBAGENT),
                base - 50,
            ),
            (
                "unknown webhook must stay out",
                "unknown outcome must stay out",
                None,
                base - 40,
            ),
            (
                "scheduled-looking text with human proof",
                "latest human outcome",
                build_message_origin_proof(GATEWAY_USER),
                base - 30,
            ),
        )
        for index, (user_text, assistant_text, origin, timestamp) in enumerate(rows):
            self.session_db.append_message(
                "mixed-bot-chat",
                "user",
                user_text,
                timestamp=timestamp,
                platform_message_id=f"mixed-user-{index}",
                origin_proof=origin,
            )
            self.session_db.append_message(
                "mixed-bot-chat",
                "assistant",
                assistant_text,
                timestamp=timestamp + 1,
                platform_message_id=f"mixed-assistant-{index}",
                origin_proof=origin,
            )

    def tearDown(self) -> None:
        plugins._reset_plugin_managers_for_tests()
        hermes_config._config_cache = None
        self.session_db.close()
        self.env.stop()
        self.tempdir.cleanup()

    def test_mixed_bot_chat_h13_classes_reach_final_provider_body(self) -> None:
        plugins.discover_plugins()
        manager = plugins.get_plugin_manager()
        loaded = {row["name"]: row for row in manager.list_plugins()}
        self.assertTrue(loaded["hermes-continuity"]["enabled"])
        self.assertIsNone(loaded["hermes-continuity"]["error"])
        self.assertTrue(loaded["hermes-global-hot"]["enabled"])
        self.assertIsNone(loaded["hermes-global-hot"]["error"])

        context = {
            "session_id": "current-mouth",
            "turn_id": "mixed-turn",
            "api_request_id": "mixed-api",
            "model": "test-model",
            "provider": "openai",
            "base_url": "https://provider.invalid",
            "api_mode": "chat_completions",
            "platform": "qqbot",
            "context_window_tokens": 32_000,
            "context_window_source": "config",
            "context_window_confidence": "authoritative",
        }
        request = {
            "model": "test-model",
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": "fixed prompt"},
                {"role": "user", "content": "current mouth input"},
            ],
        }
        projected = apply_llm_request_middleware(request, **context)
        provider_bodies: list[dict] = []
        record = TransportRecord()

        def terminal(provider_request):
            record.mark_middleware_verified(provider_request)
            provider_body = {**copy.deepcopy(provider_request), "stream": True}
            with transport_record_scope(record):
                return relay_llm.call_provider_body(
                    lambda **body: (
                        provider_bodies.append(copy.deepcopy(body)) or {"ok": True}
                    ),
                    provider_body,
                )

        result = run_llm_execution_middleware(
            projected.payload,
            terminal,
            original_request=projected.original_payload,
            transport_record=record,
            **context,
        )
        record.settle()
        invoke_hook(
            "post_api_request",
            transport_record=record,
            transport_schema_version=TRANSPORT_SCHEMA_VERSION,
            **context,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(provider_bodies), 1)
        self.assertTrue(record.settled)
        self.assertFalse(record.ambiguous)
        rendered = json.dumps(provider_bodies[0], ensure_ascii=False)
        self.assertEqual(rendered.count(GLOBAL_HOT_PREFIX), 1)
        self.assertRegex(
            rendered,
            r"role=scheduled_input \| source_class=scheduled .*"
            r"quoted=actual wakeup input",
        )
        self.assertRegex(
            rendered,
            r"role=human_input \| source_class=human .*"
            r"quoted=scheduled-looking text with human proof",
        )
        self.assertNotIn("role=scheduled_input | source_class=human", rendered)
        for excluded in (
            "internal notice must stay out",
            "internal outcome must stay out",
            "delegated result must stay out",
            "delegated outcome must stay out",
            "unknown webhook must stay out",
            "unknown outcome must stay out",
        ):
            self.assertNotIn(excluded, rendered)

        paths = list((self.home / "plugin-data").glob("*/global_hot.sqlite3"))
        self.assertEqual(len(paths), 1)
        with sqlite3.connect(paths[0]) as connection:
            connection.row_factory = sqlite3.Row
            receipts = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM global_hot_delivery_receipts"
                )
            ]
            checks = [
                dict(row)
                for row in connection.execute("SELECT * FROM global_hot_checks")
            ]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["selected_count"], 3)
        self.assertEqual(checks[-1]["status"], "delivered")
        body_free = json.dumps({"receipts": receipts, "checks": checks})
        for body in (
            "actual wakeup input",
            "scheduled-looking text with human proof",
            "latest human outcome",
            "current mouth input",
        ):
            self.assertNotIn(body, body_free)


if __name__ == "__main__":
    unittest.main()
