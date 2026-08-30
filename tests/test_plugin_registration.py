from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
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
        self.service_lookups: list[str] = []
        self.middleware: list[tuple[str, object]] = []
        self.hooks: list[tuple[str, object]] = []
        self.commands: list[tuple[str, object, dict]] = []
        self.unload: list[object] = []

    def get_config(self, key, default=None):
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
    return {"hermes_cli": hermes_cli, "hermes_cli.middleware": middleware}


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

    def test_manifest_has_no_model_tool_or_cursor_configuration(self):
        manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertNotIn("provides_commands", manifest)
        self.assertIn('version_range: ">=0.4,<1"', manifest)
        self.assertNotIn("provides_tools", manifest)
        self.assertNotIn("lookback_hours", manifest)
        self.assertNotIn("max_messages", manifest)
        self.assertNotIn("cursor", manifest)
        self.assertIn("attempt_ttl_seconds:", manifest)
        self.assertIn("type: float", manifest)
        self.assertIn("hard cap for frozen turn plans and live request attempts", manifest)

    def test_metadata_path_cannot_alias_default_state_by_symlink_or_hardlink(self):
        self.home.mkdir(parents=True)
        state_path = self.home / "state.db"
        state_path.write_bytes(b"Hermes state placeholder")
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                alias = self.data_dir / f"{kind}.sqlite3"
                alias.parent.mkdir(parents=True, exist_ok=True)
                if kind == "symlink":
                    alias.symlink_to(state_path)
                else:
                    os.link(state_path, alias)
                ctx = FakeContext(
                    self.data_dir,
                    configs={"metadata_db": str(alias)},
                )
                with patch.dict(sys.modules, host_modules()):
                    with self.assertRaisesRegex(RuntimeError, "state.db"):
                        plugin.register(ctx)
                self.assertEqual(ctx.middleware, [])

    def test_foreign_claimed_custom_metadata_path_fails_before_registration(self):
        path = Path(self.temp.name) / "shared.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE hermes_plugin_store_owner (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    owner_id TEXT NOT NULL UNIQUE
                )
                """
            )
            connection.execute(
                "INSERT INTO hermes_plugin_store_owner VALUES (1, ?)",
                ("hermes-continuity.v1",),
            )
        ctx = FakeContext(
            self.data_dir,
            configs={"metadata_db": str(path)},
        )

        with patch.dict(sys.modules, host_modules()):
            with self.assertRaisesRegex(ValueError, "owner_conflict"):
                plugin.register(ctx)

        self.assertEqual(ctx.middleware, [])
        self.assertEqual(ctx.hooks, [])


if __name__ == "__main__":
    unittest.main()
