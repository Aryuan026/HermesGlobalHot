"""Strict body-free Global Hot check and delivery metadata."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+~=-]{0,511}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_RE = re.compile(r"^ghd_[0-9a-f]{64}$")
_CHECK_REASONS = {
    "ready": {""},
    "empty": {
        "no_complete_groups_in_window",
        "no_allowed_groups_in_window",
        "no_paired_recent_anchor",
        "compiler_selected_empty",
    },
    "blocked": {
        "session_listing_ambiguous",
        "session_limit_exceeded",
        "candidate_source_ambiguous",
        "candidate_source_unavailable",
        "group_limit_exceeded",
    },
    "failed": {
        "request_invalid",
        "host_incompatible",
        "session_list_failed",
        "request_carrier_ambiguous",
        "real_user_carrier_missing",
        "first_request_has_provider_tail",
        "current_content_invalid",
        "current_identity_invalid",
        "fixed_prompt_invalid",
        "fixed_prompt_ambiguous",
        "request_message_invalid",
        "context_window_untrusted",
        "reference_at_invalid",
        "compile_input_invalid",
        "canonical_source_invalid",
        "current_identity_drift",
        "turn_compile_in_progress",
        "turn_capacity_exceeded",
    },
    "projected": {""},
    "native": {
        "provider_headroom_unproven",
        "request_carrier_ambiguous",
        "real_user_carrier_missing",
        "real_user_carrier_ambiguous",
        "request_hash_unavailable",
        "projection_material_invalid",
        "projection_too_large",
        "projection_namespace_conflict",
        "projection_marker_conflict",
        "bridge_body_conflict",
        "projection_verification_failed",
        "turn_plan_evicted",
        "execution_projection_drift",
        "final_provider_budget_removed",
        "final_provider_estimate_unproven",
        "attempt_capacity_exceeded",
    },
    "receipt_failed": {"canonical_receipt_unavailable"},
    "delivered": {""},
}


def _code(value: Any, *, optional: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("metadata_code_invalid")
    text = value.strip()
    if optional and not text:
        return ""
    if not _CODE_RE.fullmatch(text):
        raise ValueError("metadata_code_invalid")
    return text


def _sha(value: Any, *, optional: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("metadata_sha256_invalid")
    text = value.strip()
    if optional and not text:
        return ""
    if not _SHA_RE.fullmatch(text):
        raise ValueError("metadata_sha256_invalid")
    return text


def _utc_time(value: Any, *, optional: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("metadata_time_invalid")
    text = value.strip()
    if optional and not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("metadata_time_invalid") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise ValueError("metadata_time_invalid")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _count(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 3:
        raise ValueError("metadata_count_invalid")
    return value


def _session_hash(session_id: str) -> str:
    session = _code(session_id)
    return hashlib.sha256(session.encode("utf-8")).hexdigest()


class GlobalHotMetadataStore:
    """Small profile-local SQLite ledger with no transcript-body columns."""

    _OWNER_ID = "hermes-global-hot.v1"
    _HERMES_CANONICAL_TABLES = frozenset(
        {
            "schema_version",
            "system_prompts",
            "sessions",
            "messages",
            "session_model_usage",
            "state_meta",
            "gateway_routing",
            "gateway_hygiene_state",
            "compression_locks",
            "session_turn_leases",
            "async_delegations",
        }
    )

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            schema_objects = {
                str(row[0]): str(row[1])
                for row in conn.execute(
                    "SELECT name, type FROM sqlite_master"
                )
                if not str(row[0]).startswith("sqlite_")
            }
            tables = {
                name for name, object_type in schema_objects.items()
                if object_type == "table"
            }
            if tables & self._HERMES_CANONICAL_TABLES:
                raise ValueError("plugin_metadata_store_canonical_conflict")
            if "hermes_plugin_store_owner" in tables:
                try:
                    owner = conn.execute(
                        "SELECT owner_id FROM hermes_plugin_store_owner "
                        "WHERE singleton = 1"
                    ).fetchone()
                except sqlite3.Error as exc:
                    raise ValueError("plugin_metadata_store_owner_conflict") from exc
                if owner is None or owner["owner_id"] != self._OWNER_ID:
                    raise ValueError("plugin_metadata_store_owner_conflict")
            elif schema_objects:
                raise ValueError("plugin_metadata_store_unclaimed")
            else:
                conn.execute(
                    """
                    CREATE TABLE hermes_plugin_store_owner (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        owner_id TEXT NOT NULL UNIQUE
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO hermes_plugin_store_owner VALUES (1, ?)",
                    (self._OWNER_ID,),
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_hot_checks (
                    session_sha256 TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    api_request_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    reference_at TEXT NOT NULL DEFAULT '',
                    source_revision TEXT NOT NULL DEFAULT '',
                    plan_digest TEXT NOT NULL DEFAULT '',
                    request_sha256 TEXT NOT NULL DEFAULT '',
                    bridge_body_sha256 TEXT NOT NULL DEFAULT '',
                    selected_anchor_ids_sha256 TEXT NOT NULL DEFAULT '',
                    selected_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_sha256, turn_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS global_hot_checks_updated "
                "ON global_hot_checks(updated_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_hot_delivery_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    session_sha256 TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    api_request_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reference_at TEXT NOT NULL,
                    source_revision TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    bridge_body_sha256 TEXT NOT NULL,
                    selected_anchor_ids_sha256 TEXT NOT NULL,
                    selected_count INTEGER NOT NULL,
                    delivered_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS global_hot_receipts_delivered "
                "ON global_hot_delivery_receipts(delivered_at DESC)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _check_row(
        *,
        session_id: str,
        turn_id: str,
        status: str,
        updated_at: str,
        api_request_id: str,
        reason: str,
        reference_at: str,
        source_revision: str,
        plan_digest: str,
        request_sha256: str,
        bridge_body_sha256: str,
        selected_anchor_ids_sha256: str,
        selected_count: int,
    ) -> dict[str, Any]:
        if status not in _CHECK_REASONS or reason not in _CHECK_REASONS[status]:
            raise ValueError("metadata_check_state_invalid")
        count = _count(selected_count)
        selected_hash = _sha(selected_anchor_ids_sha256, optional=count == 0)
        if bool(selected_hash) is not bool(count):
            raise ValueError("metadata_selection_invalid")
        row = {
            "session_sha256": _session_hash(session_id),
            "turn_id": _code(turn_id),
            "api_request_id": _code(api_request_id, optional=True),
            "status": status,
            "reason": reason,
            "reference_at": _utc_time(reference_at, optional=True),
            "source_revision": _sha(source_revision, optional=True),
            "plan_digest": _sha(plan_digest, optional=True),
            "request_sha256": _sha(request_sha256, optional=True),
            "bridge_body_sha256": _sha(bridge_body_sha256, optional=True),
            "selected_anchor_ids_sha256": selected_hash,
            "selected_count": count,
            "updated_at": _utc_time(updated_at),
        }
        if status in {"projected", "delivered"} and not all(
            row[key]
            for key in (
                "api_request_id",
                "reference_at",
                "source_revision",
                "plan_digest",
                "request_sha256",
                "bridge_body_sha256",
                "selected_anchor_ids_sha256",
            )
        ):
            raise ValueError("metadata_check_proof_invalid")
        return row

    def record_check(
        self,
        *,
        session_id: str,
        turn_id: str,
        status: str,
        updated_at: str,
        api_request_id: str = "",
        reason: str = "",
        reference_at: str = "",
        source_revision: str = "",
        plan_digest: str = "",
        request_sha256: str = "",
        bridge_body_sha256: str = "",
        selected_anchor_ids_sha256: str = "",
        selected_count: int = 0,
    ) -> bool:
        row = self._check_row(
            session_id=session_id,
            turn_id=turn_id,
            status=status,
            updated_at=updated_at,
            api_request_id=api_request_id,
            reason=reason,
            reference_at=reference_at,
            source_revision=source_revision,
            plan_digest=plan_digest,
            request_sha256=request_sha256,
            bridge_body_sha256=bridge_body_sha256,
            selected_anchor_ids_sha256=selected_anchor_ids_sha256,
            selected_count=selected_count,
        )
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT updated_at FROM global_hot_checks
                WHERE session_sha256 = ? AND turn_id = ?
                """,
                (row["session_sha256"], row["turn_id"]),
            ).fetchone()
            if existing and row["updated_at"] < str(existing["updated_at"]):
                return False
            columns = tuple(row)
            values = tuple(row[column] for column in columns)
            conn.execute(
                f"""
                INSERT INTO global_hot_checks ({', '.join(columns)})
                VALUES ({', '.join('?' for _ in columns)})
                ON CONFLICT(session_sha256, turn_id) DO UPDATE SET
                    api_request_id = excluded.api_request_id,
                    status = excluded.status,
                    reason = excluded.reason,
                    reference_at = excluded.reference_at,
                    source_revision = excluded.source_revision,
                    plan_digest = excluded.plan_digest,
                    request_sha256 = excluded.request_sha256,
                    bridge_body_sha256 = excluded.bridge_body_sha256,
                    selected_anchor_ids_sha256 = excluded.selected_anchor_ids_sha256,
                    selected_count = excluded.selected_count,
                    updated_at = excluded.updated_at
                """,
                values,
            )
        return True

    @staticmethod
    def _delivery_row(
        *,
        receipt_id: str,
        session_id: str,
        turn_id: str,
        api_request_id: str,
        reference_at: str,
        source_revision: str,
        plan_digest: str,
        request_sha256: str,
        bridge_body_sha256: str,
        selected_anchor_ids_sha256: str,
        selected_count: int,
        delivered_at: str,
    ) -> dict[str, Any]:
        if not isinstance(receipt_id, str) or not _RECEIPT_RE.fullmatch(receipt_id):
            raise ValueError("metadata_receipt_id_invalid")
        count = _count(selected_count, minimum=1)
        return {
            "receipt_id": receipt_id,
            "session_sha256": _session_hash(session_id),
            "turn_id": _code(turn_id),
            "api_request_id": _code(api_request_id),
            "status": "delivered",
            "reference_at": _utc_time(reference_at),
            "source_revision": _sha(source_revision),
            "plan_digest": _sha(plan_digest),
            "request_sha256": _sha(request_sha256),
            "bridge_body_sha256": _sha(bridge_body_sha256),
            "selected_anchor_ids_sha256": _sha(selected_anchor_ids_sha256),
            "selected_count": count,
            "delivered_at": _utc_time(delivered_at),
        }

    def record_delivery(
        self,
        *,
        receipt_id: str,
        session_id: str,
        turn_id: str,
        api_request_id: str,
        reference_at: str,
        source_revision: str,
        plan_digest: str,
        request_sha256: str,
        bridge_body_sha256: str,
        selected_anchor_ids_sha256: str,
        selected_count: int,
        delivered_at: str,
    ) -> bool:
        row = self._delivery_row(
            receipt_id=receipt_id,
            session_id=session_id,
            turn_id=turn_id,
            api_request_id=api_request_id,
            reference_at=reference_at,
            source_revision=source_revision,
            plan_digest=plan_digest,
            request_sha256=request_sha256,
            bridge_body_sha256=bridge_body_sha256,
            selected_anchor_ids_sha256=selected_anchor_ids_sha256,
            selected_count=selected_count,
            delivered_at=delivered_at,
        )
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM global_hot_delivery_receipts WHERE receipt_id = ?",
                (row["receipt_id"],),
            ).fetchone()
            if existing is not None:
                if dict(existing) != row:
                    raise ValueError("delivery_receipt_conflict")
                return False
            columns = tuple(row)
            conn.execute(
                f"""
                INSERT INTO global_hot_delivery_receipts ({', '.join(columns)})
                VALUES ({', '.join('?' for _ in columns)})
                """,
                tuple(row[column] for column in columns),
            )
        return True

    def status(self, session_id: str = "") -> dict[str, Any]:
        session_sha = _session_hash(session_id) if session_id else ""
        where = "WHERE session_sha256 = ?" if session_sha else ""
        params = (session_sha,) if session_sha else ()
        with self._lock, self._connect() as conn:
            check = conn.execute(
                f"SELECT * FROM global_hot_checks {where} ORDER BY updated_at DESC LIMIT 1",
                params,
            ).fetchone()
            receipt = conn.execute(
                f"SELECT * FROM global_hot_delivery_receipts {where} ORDER BY delivered_at DESC LIMIT 1",
                params,
            ).fetchone()
        return {
            "schema": "global_hot_status.v1",
            "status": str(check["status"]) if check else "no_check",
            "last_check": dict(check) if check else {},
            "last_delivery": dict(receipt) if receipt else {},
            "stores_message_bodies": False,
            "uses_delivery_cursor": False,
        }
