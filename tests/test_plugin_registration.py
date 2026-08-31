from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "hermes_global_hot_registration_tests"
ENTRY_NAME = f"{PACKAGE}.entry"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package
entry_spec = importlib.util.spec_from_file_location(
    ENTRY_NAME, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
assert entry_spec is not None and entry_spec.loader is not None
plugin = importlib.util.module_from_spec(entry_spec)
sys.modules[ENTRY_NAME] = plugin
entry_spec.loader.exec_module(plugin)


class FakeSource:
    def read_window(self, request):
        raise AssertionError("registration must not read the source")


class FakeContext:
    def __init__(self, data_dir: Path, *, service=..., configs=None) -> None:
        self.state = types.SimpleNamespace(data_dir=data_dir)
        self.service = FakeSource() if service is ... else service
        self.configs = dict(configs or {})
        self.config_reads: list[str] = []
        self.service_lookups: list[str] = []
        self.middleware: list[tuple[str, object]] = []
        self.hooks: list[tuple[str, object]] = []
        self.commands: list[tuple[str, object, dict]] = []
        self.unload: list[object] = []

    def get_config(self, key, default=None):
        self.config_reads.append(key)
        return self.configs.get(key, default)

    def get_service(self, name, default=None):
        self.service_lookups.append(name)
        return self.service if self.service is not None else default

    def register_middleware(self, name, callback):
        self.middleware.append((name, callback))

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))

    def register_command(self, name, handler, **kwargs):
        self.commands.append((name, handler, kwargs))
        return object()

    def on_unload(self, callback):
        self.unload.append(callback)


def host_modules(schema: str = "hermes.middleware.v2") -> dict[str, types.ModuleType]:
    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    middleware = types.ModuleType("hermes_cli.middleware")
    middleware.MIDDLEWARE_SCHEMA_VERSION = schema
    middleware.TRANSPORT_SCHEMA_VERSION = "hermes.transport.v3"
    request_overlay = types.ModuleType("hermes_cli.request_overlay")
    request_overlay.REQUEST_OVERLAY_SCHEMA_VERSION = "hermes.request_overlay.v2"
    return {
        "hermes_cli": hermes_cli,
        "hermes_cli.middleware": middleware,
        "hermes_cli.request_overlay": request_overlay,
    }


class PluginRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "profile"
        self.data_dir = self.home / "plugin-data" / "hermes-global-hot"
        self.ctx = FakeContext(self.data_dir)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_registers_exact_service_middleware_hooks_and_slash_command(self):
        with patch.dict(sys.modules, host_modules()):
            plugin.register(self.ctx)

        self.assertEqual(
            self.ctx.service_lookups,
            ["hermes-continuity:canonical-source.v2"],
        )
        self.assertEqual(
            [name for name, _callback in self.ctx.middleware],
            ["llm_request", "llm_execution"],
        )
        self.assertEqual(
            [name for name, _callback in self.ctx.hooks],
            ["post_api_request", "api_request_error"],
        )
        self.assertEqual([row[0] for row in self.ctx.commands], ["global-hot-status"])
        self.assertEqual(len(self.ctx.unload), 1)
        status = json.loads(self.ctx.commands[0][1](""))
        self.assertEqual(status["status"], "no_check")
        self.assertFalse(status["stores_message_bodies"])
        self.assertFalse(status["uses_delivery_cursor"])
        self.assertTrue((self.data_dir / "global_hot.sqlite3").exists())
        replacement = FakeSource()
        self.ctx.service = replacement
        runtime = self.ctx.middleware[0][1].__self__
        self.assertIs(runtime.source_resolver(), replacement)
        self.assertEqual(
            self.ctx.service_lookups,
            [
                "hermes-continuity:canonical-source.v2",
                "hermes-continuity:canonical-source.v2",
            ],
        )

    def test_missing_service_fails_before_metadata_or_registration(self):
        self.ctx.service = None
        with patch.dict(sys.modules, host_modules()):
            with self.assertRaisesRegex(RuntimeError, "canonical-source.v2"):
                plugin.register(self.ctx)

        self.assertFalse((self.data_dir / "global_hot.sqlite3").exists())
        self.assertEqual(self.ctx.middleware, [])
        self.assertEqual(self.ctx.hooks, [])
        self.assertEqual(self.ctx.commands, [])

    def test_wrong_middleware_schema_or_missing_seam_fails_visibly(self):
        with patch.dict(sys.modules, host_modules("hermes.middleware.v1")):
            with self.assertRaisesRegex(RuntimeError, "hermes.middleware.v2"):
                plugin.register(self.ctx)
        self.ctx.get_service = None
        with patch.dict(sys.modules, host_modules()):
            with self.assertRaisesRegex(RuntimeError, "get_service"):
                plugin.register(self.ctx)
        self.assertEqual(self.ctx.service_lookups, [])

    def test_wrong_or_missing_transport_schema_fails_visibly(self):
        modules = host_modules()
        modules["hermes_cli.middleware"].TRANSPORT_SCHEMA_VERSION = (
            "hermes.transport.v0"
        )
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "hermes.transport.v3"):
                plugin.register(self.ctx)

        modules = host_modules()
        del modules["hermes_cli.middleware"].TRANSPORT_SCHEMA_VERSION
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "hermes.transport.v3"):
                plugin.register(self.ctx)

    def test_request_overlay_v1_fails_before_metadata_or_registration(self):
        modules = host_modules()
        modules["hermes_cli.request_overlay"].REQUEST_OVERLAY_SCHEMA_VERSION = (
            "hermes.request_overlay.v1"
        )
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "hermes.request_overlay.v2"):
                plugin.register(self.ctx)

        self.assertFalse((self.data_dir / "global_hot.sqlite3").exists())
        self.assertEqual(self.ctx.middleware, [])
        self.assertEqual(self.ctx.hooks, [])

    def test_manifest_has_no_model_tool_or_cursor_configuration(self):
        manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertNotIn("provides_commands", manifest)
        self.assertIn('version_range: ">=0.4,<1"', manifest)
        self.assertNotIn("provides_tools", manifest)
        self.assertNotIn("lookback_hours", manifest)
        self.assertNotIn("max_messages", manifest)
        self.assertNotIn("cursor", manifest)
        self.assertNotIn("metadata_db", manifest)
        self.assertIn("attempt_ttl_seconds:", manifest)
        self.assertIn("type: float", manifest)
        self.assertIn("hard cap for frozen turn plans and live request attempts", manifest)

    def test_legacy_metadata_setting_cannot_escape_profile_realm(self):
        outside = Path(self.temp.name) / "outside.sqlite3"
        ctx = FakeContext(self.data_dir, configs={"metadata_db": str(outside)})
        with patch.dict(sys.modules, host_modules()):
            plugin.register(ctx)

        self.assertNotIn("metadata_db", ctx.config_reads)
        self.assertFalse(outside.exists())
        self.assertTrue((self.data_dir / "global_hot.sqlite3").exists())


class HermesPluginManagerIntegrationTests(unittest.TestCase):
    def _source_root(self) -> str:
        source_root = os.environ.get("HERMES_SOURCE_ROOT", "").strip()
        if not source_root:
            self.skipTest("set HERMES_SOURCE_ROOT to run against a Hermes checkout")
        return source_root

    def test_real_managers_keep_receipt_realms_profile_local(self):
        source_root = self._source_root()
        sys.path.insert(0, source_root)
        try:
            from hermes_constants import (
                reset_hermes_home_override,
                set_hermes_home_override,
            )
            from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

            with tempfile.TemporaryDirectory() as temp_dir:
                homes = [
                    Path(temp_dir) / "profile-a",
                    Path(temp_dir) / "profile-b",
                ]
                managers = []
                sources = []
                paths = []
                try:
                    for home in homes:
                        manager = PluginManager(scope_key=str(home))
                        source = FakeSource()
                        token = set_hermes_home_override(home)
                        try:
                            PluginContext(
                                PluginManifest(
                                    name="hermes-continuity",
                                    key="hermes-continuity",
                                ),
                                manager,
                            ).register_service("canonical-source.v2", source)
                            plugin.register(
                                PluginContext(
                                    PluginManifest(
                                        name="hermes-global-hot",
                                        key="hermes-global-hot",
                                        path=str(ROOT),
                                    ),
                                    manager,
                                )
                            )
                        finally:
                            reset_hermes_home_override(token)
                        managers.append(manager)
                        sources.append(
                            manager._get_plugin_service(
                                "hermes-continuity:canonical-source.v2"
                            )
                        )
                        matches = list(
                            (home / "plugin-data").glob("*/global_hot.sqlite3")
                        )
                        self.assertEqual(len(matches), 1)
                        paths.append(matches[0])

                    self.assertIsNot(sources[0], sources[1])
                    self.assertNotEqual(paths[0], paths[1])
                    plugin.GlobalHotMetadataStore(paths[0]).record_check(
                        session_id="session-a",
                        turn_id="turn-a",
                        status="native",
                        reason="provider_headroom_unproven",
                        updated_at="2026-08-31T12:00:00+00:00",
                    )
                    self.assertEqual(
                        plugin.GlobalHotMetadataStore(paths[0]).status("session-a")[
                            "status"
                        ],
                        "native",
                    )
                    self.assertEqual(
                        plugin.GlobalHotMetadataStore(paths[1]).status()["status"],
                        "no_check",
                    )
                finally:
                    for manager in managers:
                        manager.unload()
        finally:
            sys.path.remove(source_root)


if __name__ == "__main__":
    unittest.main()
