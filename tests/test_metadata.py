from __future__ import annotations

import copy
import importlib
import json
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "hermes_global_hot_metadata_tests"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package

GlobalHotMetadataStore = importlib.import_module(
    f"{PACKAGE}.metadata"
).GlobalHotMetadataStore

T0 = "2026-08-30T12:00:00+00:00"


def check_args(**overrides) -> dict:
    value = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "api_request_id": "api-1",
        "status": "projected",
        "reason": "",
        "reference_at": T0,
        "source_revision": "a" * 64,
        "plan_digest": "b" * 64,
        "request_sha256": "c" * 64,
        "bridge_body_sha256": "d" * 64,
        "selected_anchor_ids_sha256": "e" * 64,
        "selected_count": 2,
        "updated_at": T0,
    }
    value.update(overrides)
    return value


def delivery_args(**overrides) -> dict:
    value = {
        "receipt_id": "ghd_" + "1" * 64,
        "session_id": "session-1",
        "turn_id": "turn-1",
        "api_request_id": "api-1",
        "reference_at": T0,
        "source_revision": "a" * 64,
        "plan_digest": "b" * 64,
        "request_sha256": "c" * 64,
        "bridge_body_sha256": "d" * 64,
        "selected_anchor_ids_sha256": "e" * 64,
        "selected_count": 2,
        "delivered_at": T0,
    }
    value.update(overrides)
    return value


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = GlobalHotMetadataStore(Path(self.temp.name) / "hot.sqlite3")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_all_fields_are_closed_and_body_text_is_rejected(self):
        invalid = (
            {"reason": "raw private transcript"},
            {"status": "private transcript"},
            {"request_sha256": "raw private transcript"},
            {"turn_id": "raw private transcript"},
            {"updated_at": "tomorrow-ish"},
            {"selected_count": 4},
            {"selected_anchor_ids_sha256": ""},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    self.store.record_check(**check_args(**override))

        with self.assertRaises(ValueError):
            self.store.record_delivery(
                **delivery_args(plan_digest="raw private transcript")
            )
        self.assertNotIn(
            "raw private transcript",
            json.dumps(self.store.status(), ensure_ascii=False),
        )

    def test_receipt_same_payload_is_idempotent_and_different_payload_conflicts(self):
        payload = delivery_args()
        self.assertTrue(self.store.record_delivery(**payload))
        self.assertFalse(self.store.record_delivery(**copy.deepcopy(payload)))
        with self.assertRaisesRegex(ValueError, "delivery_receipt_conflict"):
            self.store.record_delivery(
                **delivery_args(request_sha256="9" * 64)
            )
        status = self.store.status("session-1")
        self.assertEqual(status["last_delivery"]["request_sha256"], "c" * 64)

    def test_concurrent_same_receipt_has_one_insert_winner(self):
        barrier = threading.Barrier(8)
        results: list[bool] = []
        errors: list[Exception] = []

        def write() -> None:
            try:
                barrier.wait()
                results.append(self.store.record_delivery(**delivery_args()))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=write) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)

    def test_latest_attempt_can_replace_delivery_but_time_cannot_regress(self):
        self.assertTrue(self.store.record_check(**check_args()))
        self.assertTrue(
            self.store.record_check(
                **check_args(
                    status="delivered",
                    updated_at="2026-08-30T12:03:00+00:00",
                )
            )
        )
        self.assertTrue(
            self.store.record_check(
                **check_args(
                    status="native",
                    reason="execution_projection_drift",
                    request_sha256="",
                    bridge_body_sha256="",
                    updated_at="2026-08-30T12:04:00+00:00",
                )
            )
        )
        self.assertFalse(
            self.store.record_check(
                **check_args(
                    status="delivered",
                    updated_at="2026-08-30T11:59:00+00:00",
                )
            )
        )
        last = self.store.status("session-1")["last_check"]
        self.assertEqual(last["status"], "native")
        self.assertEqual(last["updated_at"], "2026-08-30T12:04:00.000000+00:00")

    def test_latest_failed_attempt_does_not_erase_delivery_highwater(self):
        self.assertTrue(self.store.record_delivery(**delivery_args()))
        self.assertTrue(
            self.store.record_check(
                **check_args(
                    status="delivered",
                    updated_at="2026-08-30T12:03:00+00:00",
                )
            )
        )
        self.assertTrue(
            self.store.record_check(
                **check_args(
                    status="receipt_failed",
                    reason="canonical_receipt_unavailable",
                    updated_at="2026-08-30T12:04:00+00:00",
                )
            )
        )

        status = self.store.status("session-1")
        self.assertEqual(status["last_check"]["status"], "receipt_failed")
        self.assertEqual(status["last_delivery"]["status"], "delivered")
        self.assertEqual(status["last_delivery"]["receipt_id"], delivery_args()["receipt_id"])

    def test_owner_sentinel_rejects_foreign_owner_in_both_load_orders(self):
        def claim(path: Path, owner_id: str) -> None:
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hermes_plugin_store_owner (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        owner_id TEXT NOT NULL UNIQUE
                    )
                    """
                )
                connection.execute(
                    "INSERT OR IGNORE INTO hermes_plugin_store_owner VALUES (1, ?)",
                    (owner_id,),
                )
                actual = connection.execute(
                    "SELECT owner_id FROM hermes_plugin_store_owner WHERE singleton = 1"
                ).fetchone()
                if actual is None or actual[0] != owner_id:
                    raise ValueError("plugin_metadata_store_owner_conflict")

        continuity_first = Path(self.temp.name) / "continuity-first.sqlite3"
        claim(continuity_first, "hermes-continuity.v1")
        with self.assertRaisesRegex(ValueError, "owner_conflict"):
            GlobalHotMetadataStore(continuity_first)

        global_hot_first = Path(self.temp.name) / "global-hot-first.sqlite3"
        GlobalHotMetadataStore(global_hot_first)
        with self.assertRaisesRegex(ValueError, "owner_conflict"):
            claim(global_hot_first, "hermes-continuity.v1")

    def test_unclaimed_nonempty_schema_objects_are_rejected(self):
        for kind, statement in (
            ("table", "CREATE TABLE orphan (value TEXT)"),
            ("view", "CREATE VIEW orphan AS SELECT 1 AS value"),
        ):
            with self.subTest(kind=kind):
                path = Path(self.temp.name) / f"unclaimed-{kind}.sqlite3"
                with sqlite3.connect(path) as connection:
                    connection.execute(statement)
                with self.assertRaisesRegex(ValueError, "unclaimed"):
                    GlobalHotMetadataStore(path)

    def test_claimed_store_with_hermes_canonical_table_is_rejected(self):
        path = Path(self.temp.name) / "canonical.sqlite3"
        GlobalHotMetadataStore(path)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE messages (content TEXT)")

        with self.assertRaisesRegex(ValueError, "canonical_conflict"):
            GlobalHotMetadataStore(path)


if __name__ == "__main__":
    unittest.main()
