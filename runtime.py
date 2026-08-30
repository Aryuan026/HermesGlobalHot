"""Hermes request-only runtime for the extracted Global Hot near-field.

The Continuity plugin owns canonical session discovery. This independent
consumer freezes one neutral two-hour window per logical turn, adapts complete
pairs into neutral near-field facts, compiles them with the extracted Global
Hot compiler, and projects only into provider request clones.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .global_hot_compiler import (
    build_global_hot_context_plan,
    resolve_global_hot_context_plan,
)
from .request_projection import (
    GLOBAL_HOT_END_BOUNDARY,
    _last_real_user_index,
    _request_messages,
    _request_sha256,
    _request_text_occurrences,
    project_global_hot_request,
    verify_global_hot_request_projection,
)


SOURCE_SERVICE_KEY = "hermes-continuity:canonical-source.v2"
SOURCE_REQUEST_SCHEMA = "continuity_canonical_window_request.v2"
SOURCE_RESPONSE_SCHEMA = "continuity_canonical_window_response.v2"
SOURCE_TRACE_SCHEMA = "continuity_canonical_window_trace.v2"
SOURCE_HORIZON_SECONDS = 2 * 60 * 60
SOURCE_MAX_SESSIONS = 16
SOURCE_MAX_GROUPS = 64
SOURCE_EXCLUDED_SOURCES = ("subagent", "tool")
GLOBAL_HOT_MAX_ROWS = 3
GLOBAL_HOT_MAX_CHARS = 4_000
GLOBAL_HOT_MARKER_PREFIX = "[GLOBAL HOT QUOTED REFERENCE"
_TRANSPORT_SCHEMA_VERSION = "hermes.transport.v3"
_TRUSTED_CONTEXT_CONFIDENCE = frozenset({"authoritative", "catalog", "cached"})
_LOWER_CONFIDENCE_CONTEXT_MARGIN = 0.90
_ALLOWED_SOURCE_CLASSES = frozenset({"human", "scheduled"})
_CLOSED_SOURCE_CLASSES = frozenset(
    {"human", "scheduled", "internal", "delegated", "tool", "unknown"}
)

_RESPONSE_KEYS = {
    "schema",
    "status",
    "reason",
    "reference_at",
    "horizon_seconds",
    "source_revision",
    "scan_complete",
    "groups",
    "trace",
}
_TRACE_KEYS = {
    "schema",
    "listed_session_count",
    "candidate_session_count",
    "source_session_count",
    "returned_group_count",
    "outside_horizon_session_count",
    "outside_horizon_group_count",
    "current_lineage_excluded_count",
    "policy_excluded_group_count",
    "session_proofs_sha256",
    "group_proofs_sha256",
    "body_included",
}
_GROUP_KEYS = {
    "source_session_id",
    "source",
    "source_class",
    "source_snapshot",
    "group_id",
    "effective_event_at",
    "messages",
}
_MESSAGE_KEYS = {"message_id", "role", "content", "content_hash"}
_STATUS_REASONS = {
    "ready": {""},
    "empty": {
        "no_allowed_groups_in_window",
        "no_complete_groups_in_window",
    },
    "blocked": {
        "session_listing_ambiguous",
        "session_limit_exceeded",
        "candidate_source_ambiguous",
        "candidate_source_unavailable",
        "group_limit_exceeded",
    },
    "failed": {"request_invalid", "host_incompatible", "session_list_failed"},
}
_PROJECTION_BLOCK_REASONS = {
    "request_hash_unavailable",
    "projection_material_invalid",
    "projection_too_large",
    "request_carrier_ambiguous",
    "real_user_carrier_missing",
    "real_user_carrier_ambiguous",
    "projection_namespace_conflict",
    "projection_marker_conflict",
    "bridge_body_conflict",
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reference_at_invalid")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reference_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reference_at_invalid")
    return parsed.astimezone(timezone.utc)


def _utc_reference(clock: Callable[[], str]) -> tuple[str, datetime]:
    parsed = _parse_utc(clock())
    return parsed.isoformat(), parsed


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    attachments = 0
    for item in value:
        if not isinstance(item, Mapping):
            return ""
        kind = str(item.get("type") or "")
        if kind in {"text", "input_text"} or (
            not kind and set(item) == {"text"}
        ):
            text = item.get("text")
            if not isinstance(text, str):
                return ""
            if text.strip():
                parts.append(text.strip())
        elif kind in {
            "image",
            "image_url",
            "input_image",
            "document",
            "input_file",
        } or (not kind and ({"image", "document"} & set(item))):
            attachments += 1
        elif kind in {"tool_result", "tool_use"} or "toolResult" in item:
            continue
        else:
            return ""
    if attachments:
        parts.append(f"[attachment x{attachments}]")
    return "\n".join(parts).strip()


def _attachment_payload(item: Mapping[str, Any], kind: str) -> Any:
    """Extract provider-neutral attachment content, not wrapper syntax."""

    candidates = (
        ("image_url", "image", "source", "data")
        if kind == "image"
        else (
            "file_data",
            "file_id",
            "document",
            "source",
            "data",
        )
    )
    payload: Any = None
    found = False
    for key in candidates:
        if key in item:
            payload = item[key]
            found = True
            break
    if not found:
        return None
    while isinstance(payload, Mapping):
        for key in ("url", "bytes", "file_data", "file_id", "source", "data"):
            if key in payload:
                payload = payload[key]
                break
        else:
            break
    return payload


def _attachment_identity(item: Mapping[str, Any]) -> dict[str, str] | None:
    block_type = str(item.get("type") or "").strip().lower()
    if block_type in {"image", "image_url", "input_image"} or (
        not block_type and "image" in item
    ):
        kind = "image"
    elif block_type == "input_file":
        kind = "file"
    elif block_type == "document" or (not block_type and "document" in item):
        kind = "document"
    else:
        return None
    payload = _attachment_payload(item, kind)
    if payload is None:
        return None
    try:
        digest = _request_sha256({"content": payload})
    except (TypeError, ValueError):
        return None
    return {"kind": kind, "content_sha256": digest}


def _current_identity_content(value: Any) -> Any:
    """Normalize equivalent provider carriers while binding attachment data."""

    if isinstance(value, str):
        return [{"kind": "text", "text": value.strip()}]
    if not isinstance(value, list):
        return {"kind": "invalid", "value": value}
    normalized: list[Any] = []
    for item in value:
        if not isinstance(item, Mapping):
            normalized.append({"kind": "invalid", "value": item})
            continue
        kind = str(item.get("type") or "")
        if kind in {"text", "input_text"} or (
            not kind and set(item) == {"text"}
        ):
            text = item.get("text")
            normalized.append(
                {"kind": "text", "text": text.strip()}
                if isinstance(text, str)
                else {"kind": "invalid", "value": dict(item)}
            )
        else:
            attachment = _attachment_identity(item)
            normalized.append(
                attachment
                if attachment is not None
                else {"kind": "payload", "value": dict(item)}
            )
    return normalized


def _current_message_sha256(message: Mapping[str, Any]) -> str:
    try:
        return _request_sha256(
            {
                "role": "user",
                "content": _current_identity_content(message.get("content")),
            }
        )
    except (TypeError, ValueError):
        return ""


def _text_anchor_present(candidate: str, anchor: str) -> bool:
    return bool(
        candidate == anchor
        or candidate.startswith(anchor + "\n\n")
        or candidate.endswith("\n\n" + anchor)
        or f"\n\n{anchor}\n\n" in candidate
    )


def _identity_anchor_present(candidate: Any, anchor: Any) -> bool:
    if candidate == anchor:
        return True
    if not isinstance(candidate, list) or not isinstance(anchor, list) or not anchor:
        return False
    for start in range(0, len(candidate) - len(anchor) + 1):
        window = candidate[start : start + len(anchor)]
        if window == anchor:
            return True
        if len(window) == len(anchor) == 1:
            candidate_part = window[0]
            anchor_part = anchor[0]
            if (
                isinstance(candidate_part, Mapping)
                and isinstance(anchor_part, Mapping)
                and candidate_part.get("kind") == "text"
                and anchor_part.get("kind") == "text"
                and isinstance(candidate_part.get("text"), str)
                and isinstance(anchor_part.get("text"), str)
                and _text_anchor_present(
                    candidate_part["text"], anchor_part["text"]
                )
            ):
                return True
    return False


def _request_has_current_anchor(
    messages: list[Any], anchor_sha256: str, anchor_identity: Any = None
) -> bool:
    if not anchor_sha256:
        return False
    return any(
        isinstance(message, Mapping)
        and message.get("role") == "user"
        and (
            _current_message_sha256(message) == anchor_sha256
            or (
                anchor_identity is not None
                and _identity_anchor_present(
                    _current_identity_content(message.get("content")),
                    anchor_identity,
                )
            )
        )
        for message in messages
    )


def _safe_fixed_prompt(request: Mapping[str, Any], messages: list[Any]) -> list[dict[str, Any]]:
    leading: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            raise ValueError("request_message_invalid")
        role = str(message.get("role") or "").strip().lower()
        if role not in {"system", "developer"}:
            break
        content = message.get("content")
        if not _text(content):
            raise ValueError("fixed_prompt_invalid")
        leading.append({"role": role, "content": content})

    top_values = [
        value
        for value in (request.get("system"), request.get("instructions"))
        if value is not None and value != ""
    ]
    if len(top_values) > 1 and _text(top_values[0]) != _text(top_values[1]):
        raise ValueError("fixed_prompt_ambiguous")
    if top_values:
        top_text = _text(top_values[0])
        if not top_text:
            raise ValueError("fixed_prompt_invalid")
        leading_text = [_text(row["content"]) for row in leading]
        if leading_text and top_text not in leading_text:
            raise ValueError("fixed_prompt_ambiguous")
        if not leading_text:
            leading.append({"role": "system", "content": top_text})
    return leading


def _reserved_output_tokens(request: Mapping[str, Any], window: int) -> int:
    for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
        value = request.get(key)
        if type(value) is int and 0 < value < window:
            return value
    return min(4096, max(1, window // 8))


def _default_estimator(messages: list[dict[str, Any]]) -> int:
    from agent.model_metadata import estimate_messages_tokens_rough

    return int(estimate_messages_tokens_rough(messages))


def _usable_context_window(tokens: Any, source: Any, confidence: Any) -> int | None:
    """Accept only host-resolved, explicitly non-fallback context windows."""

    if type(tokens) is not int or tokens <= 0:
        return None
    source_value = str(source or "").strip().lower()
    confidence_value = str(confidence or "").strip().lower()
    if (
        not source_value
        or source_value in {"unknown", "fallback", "fallback_unknown"}
        or confidence_value not in _TRUSTED_CONTEXT_CONFIDENCE
    ):
        return None
    if confidence_value == "authoritative":
        return tokens
    return max(1, int(tokens * _LOWER_CONFIDENCE_CONTEXT_MARGIN))


def _source_request(session_id: str, reference_at: str) -> dict[str, Any]:
    return {
        "schema": SOURCE_REQUEST_SCHEMA,
        "current_session_id": session_id,
        "reference_at": reference_at,
        "horizon_seconds": SOURCE_HORIZON_SECONDS,
        "max_sessions": SOURCE_MAX_SESSIONS,
        "max_groups": SOURCE_MAX_GROUPS,
        "excluded_sources": list(SOURCE_EXCLUDED_SOURCES),
        "allowed_source_classes": sorted(_ALLOWED_SOURCE_CLASSES),
    }


def _validate_trace(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _TRACE_KEYS:
        raise ValueError("source_trace_invalid")
    if value.get("schema") != SOURCE_TRACE_SCHEMA or value.get("body_included") is not False:
        raise ValueError("source_trace_invalid")
    for key in _TRACE_KEYS - {
        "schema",
        "session_proofs_sha256",
        "group_proofs_sha256",
        "body_included",
    }:
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError("source_trace_invalid")
    if not _is_sha256(value.get("session_proofs_sha256")) or not _is_sha256(
        value.get("group_proofs_sha256")
    ):
        raise ValueError("source_trace_invalid")


def _validate_message(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MESSAGE_KEYS:
        raise ValueError("source_message_invalid")
    message_id = str(value.get("message_id") or "").strip()
    role = str(value.get("role") or "").strip().lower()
    content_hash = str(value.get("content_hash") or "").strip()
    content = value.get("content")
    if (
        not message_id
        or len(message_id) > 512
        or role not in {"user", "assistant"}
        or not _is_sha256(content_hash)
    ):
        raise ValueError("source_message_invalid")
    try:
        actual_hash = _content_hash(content)
    except (TypeError, ValueError) as exc:
        raise ValueError("source_message_invalid") from exc
    if content_hash != actual_hash or not _text(content):
        raise ValueError("source_message_invalid")
    return {
        "message_id": message_id,
        "role": role,
        "content": content,
        "content_hash": content_hash,
    }


def _validate_group(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _GROUP_KEYS:
        raise ValueError("source_group_invalid")
    source_session_id = str(value.get("source_session_id") or "").strip()
    source = str(value.get("source") or "").strip()
    source_class = value.get("source_class")
    source_snapshot = str(value.get("source_snapshot") or "").strip()
    group_id = str(value.get("group_id") or "").strip()
    if (
        not source_session_id
        or len(source_session_id) > 512
        or not source
        or len(source) > 512
        or not isinstance(source_class, str)
        or source_class not in _CLOSED_SOURCE_CLASSES
        or not _is_sha256(source_snapshot)
        or not group_id
        or len(group_id) > 512
    ):
        raise ValueError("source_group_invalid")
    occurred = _parse_utc(value.get("effective_event_at"))
    raw_messages = value.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError("source_group_invalid")
    messages = [_validate_message(message) for message in raw_messages]
    if [message["role"] for message in messages] != [
        "user",
        "assistant",
    ] or len({message["message_id"] for message in messages}) != len(messages):
        raise ValueError("source_group_invalid")
    return {
        "source_session_id": source_session_id,
        "source": source,
        "source_class": source_class,
        "source_snapshot": source_snapshot,
        "group_id": group_id,
        "effective_event_at": occurred.isoformat(),
        "messages": messages,
    }


def _validated_window(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RESPONSE_KEYS:
        raise ValueError("source_response_invalid")
    status = str(value.get("status") or "")
    reason = str(value.get("reason") or "")
    if (
        value.get("schema") != SOURCE_RESPONSE_SCHEMA
        or status not in _STATUS_REASONS
        or reason not in _STATUS_REASONS[status]
        or value.get("reference_at") != request.get("reference_at")
        or value.get("horizon_seconds") != request.get("horizon_seconds")
        or not _is_sha256(value.get("source_revision"))
        or type(value.get("scan_complete")) is not bool
        or not isinstance(value.get("groups"), list)
    ):
        raise ValueError("source_response_invalid")
    if value["scan_complete"] is not (status in {"ready", "empty"}):
        raise ValueError("source_response_invalid")
    if status != "ready" and value["groups"]:
        raise ValueError("source_response_invalid")
    max_groups = request.get("max_groups")
    if (
        type(max_groups) is not int
        or max_groups < 0
        or len(value["groups"]) > max_groups
    ):
        raise ValueError("source_response_invalid")
    _validate_trace(value.get("trace"))
    groups = [_validate_group(group) for group in value["groups"]]
    excluded_sources = {
        str(source).strip().lower()
        for source in request.get("excluded_sources", [])
        if isinstance(source, str) and source.strip()
    }
    current_session_id = str(request.get("current_session_id") or "").strip()
    if (
        any(
            group["source"].strip().lower() in excluded_sources
            or group["source_session_id"] == current_session_id
            or group["source_class"] not in _ALLOWED_SOURCE_CLASSES
            for group in groups
        )
    ):
        raise ValueError("source_response_invalid")
    if status == "ready" and not groups:
        raise ValueError("source_response_invalid")
    order = [(group["effective_event_at"], group["group_id"]) for group in groups]
    if order != sorted(order) or len(
        {(group["source_session_id"], group["group_id"]) for group in groups}
    ) != len(groups):
        raise ValueError("source_response_invalid")
    if value["trace"].get("returned_group_count") != len(groups):
        raise ValueError("source_trace_invalid")
    return {
        "status": status,
        "reason": reason,
        "reference_at": value["reference_at"],
        "source_revision": value["source_revision"],
        "groups": groups,
    }


def _neutral_alias(kind: str, *parts: str) -> str:
    return f"continuity-{kind}:" + _sha256(list(parts))


def _bounded_fact_text(value: Any, limit: int) -> str:
    normalized = " ".join(str(value or "").replace("\x00", " ").split())
    return normalized[: max(1, int(limit or 1))]


def _anchor_id(turn_id: str, role: str) -> str:
    digest = hashlib.sha256(f"{turn_id}|{role}".encode("utf-8")).hexdigest()[:24]
    return f"ria_{digest}"


def _fact_line(
    *,
    anchor_id: str,
    role: str,
    source_class: str,
    source: str,
    event_at: str,
    text: str,
) -> str:
    return "- " + " | ".join(
        (
            anchor_id,
            f"role={role}",
            f"source_class={source_class}",
            f"source={source}",
            f"event_at={event_at[:32]}",
            f"quoted={text}",
        )
    )


def _anchor_materials(
    groups: list[dict[str, Any]], *, reference: datetime
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    for group in groups:
        messages = group["messages"]
        if [message["role"] for message in messages] != ["user", "assistant"]:
            continue
        occurred = _parse_utc(group["effective_event_at"])
        if (
            occurred > reference + timedelta(minutes=5)
            or reference - occurred > timedelta(seconds=SOURCE_HORIZON_SECONDS)
            or not _bounded_fact_text(_text(messages[0]["content"]), 240)
        ):
            continue
        eligible.append((occurred, group))

    eligible.sort(key=lambda row: (row[0], row[1]["group_id"]), reverse=True)
    selected = eligible[:2]
    rows: list[tuple[dict[str, Any], str, str, dict[str, Any]]] = []
    for _occurred, group in reversed(selected):
        user = group["messages"][0]
        role = (
            "human_input"
            if group["source_class"] == "human"
            else "scheduled_input"
        )
        rows.append(
            (group, role, _bounded_fact_text(_text(user["content"]), 240), user)
        )
    if selected:
        _occurred, latest = selected[0]
        assistant = latest["messages"][1]
        assistant_text = _bounded_fact_text(_text(assistant["content"]), 220)
        if assistant_text:
            rows.append((latest, "assistant_outcome", assistant_text, assistant))

    materials: list[dict[str, Any]] = []
    material_anchors: dict[str, str] = {}
    for index, (group, role, text, message) in enumerate(rows):
        group_key = [group["source_session_id"], group["group_id"]]
        logical_turn_id = "ght_" + _sha256(group_key)[:24]
        id_role = "human" if role.endswith("_input") else role
        anchor_id = _anchor_id(logical_turn_id, id_role)
        record_id = "ghr_" + _sha256(
            [*group_key, group["messages"][0]["message_id"]]
        )[:24]
        fact_line = _fact_line(
            anchor_id=anchor_id,
            role=role,
            source_class=group["source_class"],
            source=group["source"],
            event_at=group["effective_event_at"],
            text=text,
        )
        aliases = [
            anchor_id,
            message["message_id"],
            record_id,
            logical_turn_id,
            _neutral_alias("group", *group_key),
            _neutral_alias("message", *group_key, message["message_id"]),
        ]
        aliases = [
            value
            for value in dict.fromkeys(aliases)
            if value and len(value) <= 256
        ][:64]
        identity_digest = _sha256(
            {
                "aliases": aliases,
                "source_kind": "recent_anchor",
                "body_sha256": hashlib.sha256(fact_line.encode("utf-8")).hexdigest(),
            }
        )
        material_id = f"ghm_{identity_digest}"
        materials.append(
            {
                "material_id": material_id,
                "canonical_aliases": aliases,
                "source_kind": "recent_anchor",
                "currentness": "current",
                "priority": 900 - index,
                "order_identity": f"{index:02d}:{identity_digest}",
                "text": fact_line,
                "body_authority": "exact_body",
            }
        )
        material_anchors[material_id] = anchor_id
    return materials, material_anchors


def _compile_window_material(
    value: Any,
    *,
    request: Mapping[str, Any],
    reference: datetime,
) -> dict[str, Any]:
    window = _validated_window(value, request)
    if window["status"] != "ready":
        return {
            "status": window["status"],
            "reason": window["reason"],
            "source_revision": window["source_revision"],
            "plan_digest": "",
            "bridge_body": "",
            "marker": "",
            "selected_anchor_ids": (),
        }
    materials, material_anchors = _anchor_materials(
        window["groups"], reference=reference
    )
    if not materials:
        return {
            "status": "empty",
            "reason": "no_paired_recent_anchor",
            "source_revision": window["source_revision"],
            "plan_digest": "",
            "bridge_body": "",
            "marker": "",
            "selected_anchor_ids": (),
        }
    plan = build_global_hot_context_plan(
        material_rows=materials,
        source_revision=window["source_revision"],
    )
    compiled = resolve_global_hot_context_plan(
        plan=plan,
        represented_body_bindings=[],
        max_rows=GLOBAL_HOT_MAX_ROWS,
        max_chars=GLOBAL_HOT_MAX_CHARS,
    )
    selected_material_ids = tuple(
        str(value) for value in compiled["selected_material_ids"]
    )
    if not selected_material_ids or not str(compiled.get("prompt_text") or "").strip():
        return {
            "status": "empty",
            "reason": "compiler_selected_empty",
            "source_revision": window["source_revision"],
            "plan_digest": str(plan["plan_digest"]),
            "bridge_body": "",
            "marker": "",
            "selected_anchor_ids": (),
        }
    if not set(selected_material_ids).issubset(material_anchors):
        raise ValueError("compiler_selection_invalid")
    selected_ids = tuple(
        material_anchors[material_id] for material_id in selected_material_ids
    )
    plan_digest = str(plan["plan_digest"])
    marker = (
        f"{GLOBAL_HOT_MARKER_PREFIX} plan_digest={plan_digest} "
        f'source_revision={window["source_revision"]}]'
    )
    return {
        "status": "ready",
        "reason": "",
        "source_revision": window["source_revision"],
        "plan_digest": plan_digest,
        "bridge_body": (
            f'{str(compiled["prompt_text"]).rstrip()}\n{GLOBAL_HOT_END_BOUNDARY}'
        ),
        "marker": marker,
        "selected_anchor_ids": selected_ids,
    }


@dataclass
class _TurnPlan:
    current_sha256: str
    current_identity: Any = None
    reference_at: str = ""
    status: str = "failed"
    reason: str = ""
    source_revision: str = ""
    plan_digest: str = ""
    marker: str = ""
    bridge_body: str = ""
    selected_anchor_ids: tuple[str, ...] = ()
    context_window_tokens: int = 0
    usable_context_window_tokens: int = 0
    context_window_source: str = "unknown"
    context_window_confidence: str = "unknown"
    reserved_output_tokens: int = 0


@dataclass
class _Projection:
    turn_key: tuple[str, str]
    attempt_seq: int
    proof: dict[str, Any]
    carrier_material_sha256: str
    carrier_material_length: int
    carrier_material_kind: str
    provider_key: tuple[str, str, str]
    request_model_sha256: str
    context_window_tokens: int
    usable_context_window_tokens: int
    context_window_source: str
    context_window_confidence: str
    last_touch: float = 0.0


@dataclass
class _TransportStage:
    turn_key: tuple[str, str]
    attempt_seq: int
    request_sha256: str
    transport_record: Any = field(repr=False, compare=False)
    last_touch: float = 0.0


class GlobalHotRuntime:
    """Freeze one source window per turn; project and settle per API attempt."""

    def __init__(
        self,
        source_service: Any,
        metadata_store: Any,
        *,
        source_resolver: Callable[[], Any] | None = None,
        projector: Callable[..., dict[str, Any]] = project_global_hot_request,
        verifier: Callable[..., dict[str, Any]] = verify_global_hot_request_projection,
        estimator: Callable[[list[dict[str, Any]]], int] | None = None,
        clock: Callable[[], str] | None = None,
        max_projection_chars: int = 24_000,
        max_cached_turns: int = 128,
        attempt_ttl_seconds: float = 600.0,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        reader = getattr(source_service, "read_window", None)
        if not callable(reader):
            raise RuntimeError("canonical_source_service_incompatible")
        self.source_resolver = source_resolver or (lambda: source_service)
        self.metadata_store = metadata_store
        self.projector = projector
        self.verifier = verifier
        self.estimator = estimator or _default_estimator
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.max_projection_chars = max(1, int(max_projection_chars))
        self.max_cached_turns = max(1, int(max_cached_turns))
        self.attempt_ttl_seconds = max(1.0, float(attempt_ttl_seconds))
        self.monotonic = monotonic or time.monotonic
        self._lock = threading.RLock()
        self._turns: "OrderedDict[tuple[str, str], _TurnPlan]" = OrderedDict()
        self._compiling: set[tuple[str, str]] = set()
        self._projections: dict[tuple[str, str, str], _Projection] = {}
        self._transport: dict[tuple[str, str, str], _TransportStage] = {}
        self._executing: set[tuple[str, str, str]] = set()
        self._attempt_seq = 0

    def _record_check(
        self,
        *,
        session_id: str,
        turn_id: str,
        status: str,
        plan: _TurnPlan,
        api_request_id: str = "",
        reason: str = "",
        request_sha256: str = "",
        bridge_body_sha256: str = "",
    ) -> None:
        writer = getattr(self.metadata_store, "record_check", None)
        if not callable(writer):
            return
        try:
            writer(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                status=status,
                reason=(reason or plan.reason)[:160],
                reference_at=plan.reference_at,
                source_revision=plan.source_revision,
                plan_digest=plan.plan_digest,
                request_sha256=request_sha256,
                bridge_body_sha256=bridge_body_sha256,
                selected_anchor_ids_sha256=(
                    _sha256(list(plan.selected_anchor_ids))
                    if plan.selected_anchor_ids
                    else ""
                ),
                selected_count=len(plan.selected_anchor_ids),
                updated_at=self.clock(),
            )
        except Exception:
            return

    def _record_native(
        self,
        *,
        session_id: str,
        turn_id: str,
        api_request_id: str,
        plan: _TurnPlan,
        reason: str,
    ) -> None:
        self._record_check(
            session_id=session_id,
            turn_id=turn_id,
            api_request_id=api_request_id,
            status="native",
            reason=reason,
            plan=plan,
        )

    def _trim_locked(
        self, *, protected_turns: tuple[tuple[str, str], ...] = ()
    ) -> bool:
        self._sweep_expired_locked()
        while len(self._turns) > self.max_cached_turns:
            active = {
                value.turn_key
                for value in (*self._projections.values(), *self._transport.values())
            }
            expired = next(
                (
                    key
                    for key in self._turns
                    if key not in active and key not in protected_turns
                ),
                None,
            )
            if expired is None:
                return False
            self._turns.pop(expired, None)
            self._projections = {
                key: value
                for key, value in self._projections.items()
                if value.turn_key != expired
            }
            self._transport = {
                key: value
                for key, value in self._transport.items()
                if value.turn_key != expired
            }
        return True

    def _sweep_expired_locked(self) -> None:
        cutoff = self.monotonic() - self.attempt_ttl_seconds
        expired = {
            key
            for key, value in self._projections.items()
            if value.last_touch <= cutoff and key not in self._executing
        } | {
            key
            for key, value in self._transport.items()
            if value.last_touch <= cutoff and key not in self._executing
        }
        for key in expired:
            self._projections.pop(key, None)
            self._transport.pop(key, None)

    def _attempt_capacity_available_locked(
        self, attempt_key: tuple[str, str, str]
    ) -> bool:
        self._sweep_expired_locked()
        return bool(
            attempt_key in self._projections
            or len(self._projections) < self.max_cached_turns
        )

    def _compile_plan(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str,
        turn_id: str,
        context_window_tokens: Any,
        context_window_source: Any,
        context_window_confidence: Any,
    ) -> _TurnPlan:
        shape = _request_messages(request)
        if shape is None:
            return _TurnPlan("", reason="request_carrier_ambiguous")
        _request_key, messages = shape
        current_index = _last_real_user_index(messages)
        if current_index < 0:
            return _TurnPlan("", reason="real_user_carrier_missing")
        if current_index != len(messages) - 1:
            return _TurnPlan("", reason="first_request_has_provider_tail")
        current_message = messages[current_index]
        if not isinstance(current_message, Mapping) or not _text(
            current_message.get("content")
        ):
            return _TurnPlan("", reason="current_content_invalid")
        current_sha = _current_message_sha256(current_message)
        if not current_sha:
            return _TurnPlan("", reason="current_identity_invalid")
        current_identity = _current_identity_content(current_message.get("content"))
        try:
            _safe_fixed_prompt(request, messages)
            usable_window = _usable_context_window(
                context_window_tokens,
                context_window_source,
                context_window_confidence,
            )
            if usable_window is None:
                raise ValueError("context_window_untrusted")
            window = int(context_window_tokens)
            source_label = str(context_window_source or "unknown")
            confidence_label = str(context_window_confidence or "unknown")
            reserve = _reserved_output_tokens(request, usable_window)
            reference_at, reference = _utc_reference(self.clock)
        except Exception as exc:
            reason = str(exc)
            if reason not in {
                "request_message_invalid",
                "fixed_prompt_invalid",
                "fixed_prompt_ambiguous",
                "context_window_untrusted",
                "reference_at_invalid",
            }:
                reason = "compile_input_invalid"
            return _TurnPlan(current_sha, reason=reason)
        source_request = _source_request(session_id, reference_at)
        try:
            source_service = self.source_resolver()
            reader = getattr(source_service, "read_window", None)
            if not callable(reader):
                raise RuntimeError("canonical_source_service_incompatible")
            source_response = reader(source_request)
            compiled = _compile_window_material(
                source_response,
                request=source_request,
                reference=reference,
            )
        except Exception:
            return _TurnPlan(
                current_sha,
                reference_at=reference_at,
                reason="canonical_source_invalid",
                context_window_tokens=window,
                usable_context_window_tokens=usable_window,
                context_window_source=source_label,
                context_window_confidence=confidence_label,
                reserved_output_tokens=reserve,
            )
        return _TurnPlan(
            current_sha,
            current_identity=current_identity,
            reference_at=reference_at,
            status=compiled["status"],
            reason=compiled["reason"],
            source_revision=compiled["source_revision"],
            plan_digest=compiled["plan_digest"],
            marker=compiled["marker"],
            bridge_body=compiled["bridge_body"],
            selected_anchor_ids=compiled["selected_anchor_ids"],
            context_window_tokens=window,
            usable_context_window_tokens=usable_window,
            context_window_source=source_label,
            context_window_confidence=confidence_label,
            reserved_output_tokens=reserve,
        )

    def _plan_for_request(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str,
        turn_id: str,
        context_window_tokens: Any,
        context_window_source: Any,
        context_window_confidence: Any,
    ) -> _TurnPlan:
        turn_key = (session_id, turn_id)
        shape = _request_messages(request)
        current_sha = ""
        messages: list[Any] = []
        if shape is not None:
            messages = shape[1]
            index = _last_real_user_index(messages)
            if index >= 0 and isinstance(messages[index], Mapping):
                current_sha = _current_message_sha256(messages[index])
        with self._lock:
            existing = self._turns.get(turn_key)
            if existing is not None:
                self._turns.move_to_end(turn_key)
                if not _request_has_current_anchor(
                    messages,
                    existing.current_sha256,
                    existing.current_identity,
                ):
                    return _TurnPlan(current_sha, reason="current_identity_drift")
                return existing
            if turn_key in self._compiling:
                return _TurnPlan(current_sha, reason="turn_compile_in_progress")
            self._compiling.add(turn_key)
        try:
            plan = self._compile_plan(
                request,
                session_id=session_id,
                turn_id=turn_id,
                context_window_tokens=context_window_tokens,
                context_window_source=context_window_source,
                context_window_confidence=context_window_confidence,
            )
        except BaseException:
            with self._lock:
                self._compiling.discard(turn_key)
            raise
        with self._lock:
            self._compiling.discard(turn_key)
            self._turns[turn_key] = plan
            self._turns.move_to_end(turn_key)
            if not self._trim_locked(protected_turns=(turn_key,)):
                if self._turns.get(turn_key) is plan:
                    self._turns.pop(turn_key, None)
                plan = _TurnPlan(current_sha, reason="turn_capacity_exceeded")
        self._record_check(
            session_id=session_id,
            turn_id=turn_id,
            status=plan.status,
            plan=plan,
        )
        return plan

    def _attempt_budget(
        self,
        request: Mapping[str, Any],
        plan: _TurnPlan,
        *,
        context_window_tokens: Any,
        context_window_source: Any,
        context_window_confidence: Any,
    ) -> tuple[int, int, int, str, str] | None:
        try:
            usable_window = _usable_context_window(
                context_window_tokens,
                context_window_source,
                context_window_confidence,
            )
            if usable_window is None:
                return None
            window = int(context_window_tokens)
            source = str(context_window_source or "unknown")
            confidence = str(context_window_confidence or "unknown")
            reserve = _reserved_output_tokens(request, usable_window)
        except Exception:
            return None
        if (
            usable_window - reserve
            < plan.usable_context_window_tokens - plan.reserved_output_tokens
        ):
            return None
        return window, usable_window, reserve, source, confidence

    def _request_fits_context(
        self, request: Mapping[str, Any], *, window: int, reserve: int
    ) -> bool:
        shape = _request_messages(request)
        if shape is None or not all(isinstance(message, Mapping) for message in shape[1]):
            return False
        try:
            rows = [dict(message) for message in shape[1]]
            fixed_prompt = _safe_fixed_prompt(request, shape[1])
            has_leading_prompt = bool(
                rows
                and str(rows[0].get("role") or "").strip().lower()
                in {"system", "developer"}
            )
            if fixed_prompt and not has_leading_prompt:
                rows = [*fixed_prompt, *rows]
            message_tokens = int(self.estimator(rows))
            shadow = {
                key: value
                for key, value in request.items()
                if key not in {"messages", "input", "system", "instructions"}
            }
            non_message_tokens = (len(_json_bytes(shadow)) + 3) // 4
        except Exception:
            return False
        return bool(
            message_tokens >= 0
            and non_message_tokens >= 0
            and message_tokens + non_message_tokens + reserve <= window
        )

    @staticmethod
    def _content_sha256(content: Any) -> str:
        try:
            return _request_sha256({"content": content})
        except (TypeError, ValueError):
            return ""

    @classmethod
    def _carrier_material(cls, content: Any) -> tuple[str, int, str]:
        if isinstance(content, str):
            kind, length = "string", len(content)
        elif isinstance(content, list):
            kind, length = "list", len(content)
        else:
            return "", 0, ""
        digest = cls._content_sha256(content)
        return (digest, length, kind) if digest else ("", 0, "")

    @staticmethod
    def _request_model_sha256(request: Mapping[str, Any]) -> str:
        try:
            return _request_sha256(
                {"present": "model" in request, "model": request.get("model")}
            )
        except (TypeError, ValueError):
            return ""

    def _projection_material_exact(
        self,
        request: Mapping[str, Any],
        projection: _Projection,
        plan: _TurnPlan,
    ) -> bool:
        proof = projection.proof
        shape = _request_messages(request)
        if not isinstance(proof, Mapping) or shape is None:
            return False
        request_key, messages = shape
        carrier_index = proof.get("carrier_index")
        carrier_kind = str(proof.get("carrier_kind") or "")
        if (
            type(carrier_index) is not int
            or not 0 <= carrier_index < len(messages)
            or proof.get("message_count") != len(messages)
            or not carrier_kind.startswith(f"{request_key}:")
        ):
            return False
        message = messages[carrier_index]
        if not isinstance(message, Mapping) or message.get("role") != "user":
            return False
        block = f"{plan.marker}\n{plan.bridge_body}"
        if (
            _request_text_occurrences(request, plan.marker) != 1
            or _request_text_occurrences(request, plan.bridge_body) != 1
            or _request_text_occurrences(request, block) != 1
            or proof.get("bridge_body_sha256")
            != hashlib.sha256(plan.bridge_body.encode("utf-8")).hexdigest()
        ):
            return False
        content = message.get("content")
        if carrier_kind.endswith(":string"):
            if not isinstance(content, str) or content.count(f"{block}\n\n") != 1:
                return False
            length = projection.carrier_material_length
            if projection.carrier_material_kind != "string" or length < 1:
                return False
            return any(
                self._content_sha256(content[start : start + length])
                == projection.carrier_material_sha256
                for start in range(0, len(content) - length + 1)
            )
        if not isinstance(content, list) or projection.carrier_material_kind != "list":
            return False
        block_type = carrier_kind.rsplit(":", 1)[-1]
        expected_block = (
            {"text": block}
            if block_type == "bedrock_text"
            else {"type": block_type, "text": block}
        )
        if sum(item == expected_block for item in content) != 1:
            return False
        length = projection.carrier_material_length
        if length < 1 or len(content) < length:
            return False
        return any(
            self._content_sha256(content[start : start + length])
            == projection.carrier_material_sha256
            for start in range(0, len(content) - length + 1)
        )

    def _scoped_projection_exact(
        self,
        request: Mapping[str, Any],
        projection: _Projection,
        plan: _TurnPlan,
        *,
        provider_key: tuple[str, str, str],
    ) -> bool:
        return bool(
            provider_key == projection.provider_key
            and self._request_model_sha256(request) == projection.request_model_sha256
            and self._projection_material_exact(request, projection, plan)
        )

    def _provider_projection_exact(
        self,
        request: Mapping[str, Any],
        projection: _Projection,
        plan: _TurnPlan,
        *,
        provider_key: tuple[str, str, str],
    ) -> bool:
        """Verify this plugin's block on the captured provider-bound body."""

        if (
            provider_key != projection.provider_key
            or self._request_model_sha256(request)
            != projection.request_model_sha256
            or not self._projection_material_exact(request, projection, plan)
            or _request_text_occurrences(request, GLOBAL_HOT_END_BOUNDARY) != 1
        ):
            return False
        native_request = self._remove_bound_projection(request, projection, plan)
        shape = _request_messages(native_request) if native_request is not None else None
        return bool(
            shape is not None
            and _request_has_current_anchor(
                shape[1],
                plan.current_sha256,
                plan.current_identity,
            )
        )

    def _register_provider_budget_guard(
        self,
        transport_record: Any,
        projection: _Projection,
        plan: _TurnPlan,
        provider_key: tuple[str, str, str],
    ) -> bool:
        register_filter = getattr(
            transport_record, "register_provider_body_filter", None
        )
        if (
            getattr(transport_record, "schema_version", None)
            != _TRANSPORT_SCHEMA_VERSION
            or not callable(register_filter)
        ):
            return False

        def global_hot_budget_guard(
            body: dict[str, Any],
            *,
            estimated_tokens: Any = None,
            estimate_source: Any = None,
            estimate_confidence: Any = None,
        ) -> dict[str, Any]:
            if not self._provider_projection_exact(
                body,
                projection,
                plan,
                provider_key=provider_key,
            ):
                raise ValueError("global_hot_final_body_drift")
            reserve = _reserved_output_tokens(
                body, projection.usable_context_window_tokens
            )
            estimate_valid = bool(
                type(estimated_tokens) is int
                and estimated_tokens >= 0
                and str(estimate_source or "")
                == "hermes.provider_body.rough.v1"
                and str(estimate_confidence or "")
                == "heuristic_with_margin"
            )
            if (
                estimate_valid
                and estimated_tokens + reserve
                <= projection.usable_context_window_tokens
            ):
                return body
            native = self._remove_bound_projection(body, projection, plan)
            if native is None:
                raise ValueError("global_hot_final_budget_unverifiable")
            return native

        try:
            register_filter(global_hot_budget_guard, phase="final_guard")
        except Exception:
            return False
        return True

    def _stage_provider_transport(
        self,
        attempt_key: tuple[str, str, str],
        projection: _Projection,
        plan: _TurnPlan,
        provider_key: tuple[str, str, str],
        transport_record: Any,
        transport_schema_version: str,
    ) -> bool:
        try:
            if (
                transport_schema_version != _TRANSPORT_SCHEMA_VERSION
                or transport_record is None
                or getattr(transport_record, "schema_version", None)
                != _TRANSPORT_SCHEMA_VERSION
                or bool(getattr(transport_record, "ambiguous"))
                or getattr(transport_record, "capture_count") != 1
            ):
                return False
            provider_body = getattr(transport_record, "provider_body")
            estimated_tokens = getattr(
                transport_record, "provider_body_estimated_tokens"
            )
            estimate_source = getattr(
                transport_record, "provider_body_estimate_source"
            )
            estimate_confidence = getattr(
                transport_record, "provider_body_estimate_confidence"
            )
            reserve = (
                _reserved_output_tokens(
                    provider_body, projection.usable_context_window_tokens
                )
                if isinstance(provider_body, Mapping)
                else 0
            )
            if (
                not isinstance(provider_body, Mapping)
                or not self._provider_projection_exact(
                    provider_body,
                    projection,
                    plan,
                    provider_key=provider_key,
                )
                or type(estimated_tokens) is not int
                or estimated_tokens < 0
                or estimate_source != "hermes.provider_body.rough.v1"
                or estimate_confidence != "heuristic_with_margin"
                or estimated_tokens + reserve
                > projection.usable_context_window_tokens
            ):
                return False
            request_digest = _request_sha256(provider_body)
        except Exception:
            return False
        with self._lock:
            if self._projections.get(attempt_key) is not projection:
                return False
            now = self.monotonic()
            projection.last_touch = now
            self._transport[attempt_key] = _TransportStage(
                turn_key=projection.turn_key,
                attempt_seq=projection.attempt_seq,
                request_sha256=request_digest,
                transport_record=transport_record,
                last_touch=now,
            )
        return True

    def _remove_bound_projection(
        self,
        request: Mapping[str, Any],
        projection: _Projection,
        plan: _TurnPlan,
    ) -> dict[str, Any] | None:
        if not self._projection_material_exact(request, projection, plan):
            return None
        shape = _request_messages(request)
        if shape is None:
            return None
        request_key, messages = shape
        carrier_index = int(projection.proof["carrier_index"])
        carrier_kind = str(projection.proof["carrier_kind"])
        message = messages[carrier_index]
        content = message.get("content")
        block = f"{plan.marker}\n{plan.bridge_body}"
        projected_message = dict(message)
        if carrier_kind.endswith(":string"):
            token = f"{block}\n\n"
            position = content.find(token)
            projected_message["content"] = content[:position] + content[position + len(token) :]
        else:
            block_type = carrier_kind.rsplit(":", 1)[-1]
            expected_block = (
                {"text": block}
                if block_type == "bedrock_text"
                else {"type": block_type, "text": block}
            )
            projected_message["content"] = list(content)
            projected_message["content"].remove(expected_block)
        next_messages = list(messages)
        next_messages[carrier_index] = projected_message
        native_request = dict(request)
        native_request[request_key] = next_messages
        return native_request

    def llm_request(
        self,
        *,
        request: Mapping[str, Any],
        original_request: Mapping[str, Any] | None = None,
        session_id: str,
        turn_id: str,
        api_request_id: str,
        model: str = "",
        provider: str = "",
        base_url: str = "",
        api_mode: str = "",
        platform: str = "",
        context_window_tokens: Any = None,
        context_window_source: str = "unknown",
        context_window_confidence: str = "unknown",
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        del original_request
        session_id = str(session_id or "").strip()
        turn_id = str(turn_id or "").strip()
        api_request_id = str(api_request_id or "").strip()
        if (
            not session_id
            or not turn_id
            or not api_request_id
            or api_mode == "codex_app_server"
            or str(platform or "").strip().lower() == "subagent"
            or not isinstance(request, Mapping)
        ):
            return None
        attempt_key = (session_id, turn_id, api_request_id)
        with self._lock:
            self._projections.pop(attempt_key, None)
            self._transport.pop(attempt_key, None)
        plan = self._plan_for_request(
            request,
            session_id=session_id,
            turn_id=turn_id,
            context_window_tokens=context_window_tokens,
            context_window_source=context_window_source,
            context_window_confidence=context_window_confidence,
        )
        if plan.status != "ready" or plan.reason:
            self._record_check(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                status=plan.status,
                reason=plan.reason,
                plan=plan,
            )
            return None
        if not plan.bridge_body:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="projection_material_invalid",
            )
            return None
        provider_key = (str(model or ""), str(provider or ""), str(base_url or ""))
        budget = self._attempt_budget(
            request,
            plan,
            context_window_tokens=context_window_tokens,
            context_window_source=context_window_source,
            context_window_confidence=context_window_confidence,
        )
        if budget is None:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                reason="provider_headroom_unproven",
                plan=plan,
            )
            return None
        window, usable_window, reserve, source, confidence = budget
        shape = _request_messages(request)
        if shape is None:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="request_carrier_ambiguous",
            )
            return None
        carrier_index = _last_real_user_index(shape[1])
        if carrier_index < 0 or not isinstance(shape[1][carrier_index], Mapping):
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="real_user_carrier_missing",
            )
            return None
        carrier_digest, carrier_length, carrier_kind = self._carrier_material(
            shape[1][carrier_index].get("content")
        )
        if not carrier_digest:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="real_user_carrier_ambiguous",
            )
            return None
        projected = self.projector(
            request,
            marker=plan.marker,
            bridge_body=plan.bridge_body,
            max_projection_chars=self.max_projection_chars,
        )
        proof = projected.get("proof") if isinstance(projected, Mapping) else None
        next_request = projected.get("request") if isinstance(projected, Mapping) else None
        if (
            not isinstance(proof, Mapping)
            or proof.get("status") != "projected"
            or not isinstance(next_request, dict)
        ):
            reason = str(proof.get("reason") or "") if isinstance(proof, Mapping) else ""
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason=(
                    reason
                    if reason in _PROJECTION_BLOCK_REASONS
                    else "projection_verification_failed"
                ),
            )
            return None
        verified = self.verifier(
            next_request,
            proof,
            marker=plan.marker,
            bridge_body=plan.bridge_body,
        )
        if verified.get("status") != "verified":
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="projection_verification_failed",
            )
            return None
        if not self._request_fits_context(
            next_request, window=usable_window, reserve=reserve
        ):
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="projected_request_over_context",
            )
            return None
        turn_key = (session_id, turn_id)
        attempt_capacity_exceeded = False
        with self._lock:
            if self._turns.get(turn_key) is not plan:
                plan_evicted = True
            elif not self._attempt_capacity_available_locked(attempt_key):
                plan_evicted = False
                attempt_capacity_exceeded = True
            else:
                plan_evicted = False
                attempt_capacity_exceeded = False
                self._attempt_seq += 1
                self._projections[attempt_key] = _Projection(
                    turn_key=turn_key,
                    attempt_seq=self._attempt_seq,
                    proof=dict(proof),
                    carrier_material_sha256=carrier_digest,
                    carrier_material_length=carrier_length,
                    carrier_material_kind=carrier_kind,
                    provider_key=provider_key,
                    request_model_sha256=self._request_model_sha256(next_request),
                    context_window_tokens=window,
                    usable_context_window_tokens=usable_window,
                    context_window_source=source,
                    context_window_confidence=confidence,
                    last_touch=self.monotonic(),
                )
        if attempt_capacity_exceeded:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="attempt_capacity_exceeded",
            )
            return None
        if plan_evicted:
            self._record_native(
                session_id=session_id,
                turn_id=turn_id,
                api_request_id=api_request_id,
                plan=plan,
                reason="turn_plan_evicted",
            )
            return None
        self._record_check(
            session_id=session_id,
            turn_id=turn_id,
            api_request_id=api_request_id,
            status="projected",
            plan=plan,
            request_sha256=str(proof.get("request_sha256") or ""),
            bridge_body_sha256=str(proof.get("bridge_body_sha256") or ""),
        )
        return {
            "request": next_request,
            "source": "hermes-global-hot",
            "reason": "nearfield_projected",
        }

    def llm_execution(
        self,
        *,
        request: Mapping[str, Any],
        original_request: Mapping[str, Any],
        next_call: Callable[[dict[str, Any]], Any],
        session_id: str,
        turn_id: str,
        api_request_id: str,
        model: str = "",
        provider: str = "",
        base_url: str = "",
        transport_record: Any = None,
        transport_schema_version: str = "",
        context_window_tokens: Any = None,
        context_window_source: str = "unknown",
        context_window_confidence: str = "unknown",
        **_kwargs: Any,
    ) -> Any:
        del original_request
        attempt_key = (
            str(session_id or "").strip(),
            str(turn_id or "").strip(),
            str(api_request_id or "").strip(),
        )
        with self._lock:
            projection = self._projections.get(attempt_key)
            plan = self._turns.get(projection.turn_key) if projection else None
            self._sweep_expired_locked()
            projection_active = bool(
                projection is not None
                and plan is not None
                and self._projections.get(attempt_key) is projection
            )
            if projection_active:
                self._executing.add(attempt_key)
        if projection is None or plan is None:
            return next_call(request)
        if not projection_active:
            native_request = self._remove_bound_projection(request, projection, plan)
            return next_call(native_request if native_request is not None else request)
        supplied = (str(model or ""), str(provider or ""), str(base_url or ""))
        provider_key = supplied if any(supplied) else projection.provider_key
        if "_moa_prepared_request" in request:
            native_request = self._remove_bound_projection(request, projection, plan)
            with self._lock:
                self._executing.discard(attempt_key)
                self._projections.pop(attempt_key, None)
                self._transport.pop(attempt_key, None)
            self._record_native(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                plan=plan,
                reason="execution_projection_drift",
            )
            return next_call(native_request if native_request is not None else request)
        usable_window = _usable_context_window(
            context_window_tokens,
            context_window_source,
            context_window_confidence,
        )
        context_matches = bool(
            usable_window == projection.usable_context_window_tokens
            and context_window_tokens == projection.context_window_tokens
            and str(context_window_source or "unknown")
            == projection.context_window_source
            and str(context_window_confidence or "unknown")
            == projection.context_window_confidence
        )
        if not self._scoped_projection_exact(
            request, projection, plan, provider_key=provider_key
        ):
            native_request = self._remove_bound_projection(request, projection, plan)
            with self._lock:
                self._executing.discard(attempt_key)
                self._projections.pop(attempt_key, None)
                self._transport.pop(attempt_key, None)
            self._record_check(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                status="native",
                reason="execution_projection_drift",
                plan=plan,
            )
            return next_call(native_request if native_request is not None else request)
        transport_ready = bool(
            str(transport_schema_version or "") == _TRANSPORT_SCHEMA_VERSION
            and transport_record is not None
            and context_matches
            and self._register_provider_budget_guard(
                transport_record,
                projection,
                plan,
                provider_key,
            )
        )
        if not transport_ready:
            native_request = self._remove_bound_projection(request, projection, plan)
            with self._lock:
                self._executing.discard(attempt_key)
                self._projections.pop(attempt_key, None)
                self._transport.pop(attempt_key, None)
            self._record_native(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                plan=plan,
                reason="execution_projection_drift",
            )
            return next_call(native_request if native_request is not None else request)
        try:
            response = next_call(request)
        except Exception:
            with self._lock:
                self._executing.discard(attempt_key)
                self._projections.pop(attempt_key, None)
                self._transport.pop(attempt_key, None)
            raise
        if not self._stage_provider_transport(
            attempt_key,
            projection,
            plan,
            provider_key,
            transport_record,
            str(transport_schema_version or ""),
        ):
            with self._lock:
                self._executing.discard(attempt_key)
                self._projections.pop(attempt_key, None)
                self._transport.pop(attempt_key, None)
            self._record_native(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                plan=plan,
                reason="execution_projection_drift",
            )
        with self._lock:
            self._executing.discard(attempt_key)
        return response

    def post_api_request(
        self,
        *,
        session_id: str,
        turn_id: str,
        api_request_id: str,
        transport_record: Any = None,
        transport_schema_version: str = "",
        **_kwargs: Any,
    ) -> None:
        attempt_key = (
            str(session_id or "").strip(),
            str(turn_id or "").strip(),
            str(api_request_id or "").strip(),
        )
        with self._lock:
            self._executing.discard(attempt_key)
            self._sweep_expired_locked()
            stage = self._transport.pop(attempt_key, None)
            projection = self._projections.pop(attempt_key, None)
            plan = self._turns.get(stage.turn_key) if stage else None
            protected = stage.turn_key if stage else projection.turn_key if projection else None
            self._trim_locked(protected_turns=(protected,) if protected else ())
        if stage is None or projection is None or plan is None:
            return None
        try:
            provider_body = getattr(transport_record, "provider_body")
            transport_verified = bool(
                transport_schema_version == _TRANSPORT_SCHEMA_VERSION
                and transport_record is stage.transport_record
                and getattr(transport_record, "schema_version", None)
                == _TRANSPORT_SCHEMA_VERSION
                and not bool(getattr(transport_record, "ambiguous"))
                and getattr(transport_record, "capture_count") == 1
                and bool(getattr(transport_record, "settled"))
                and isinstance(provider_body, Mapping)
                and _request_sha256(provider_body) == stage.request_sha256
                and projection.attempt_seq == stage.attempt_seq
                and self._provider_projection_exact(
                    provider_body,
                    projection,
                    plan,
                    provider_key=projection.provider_key,
                )
            )
        except Exception:
            transport_verified = False
        if not transport_verified:
            self._record_native(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                plan=plan,
                reason="execution_projection_drift",
            )
            return None
        bridge_hash = hashlib.sha256(plan.bridge_body.encode("utf-8")).hexdigest()
        selected_hash = _sha256(list(plan.selected_anchor_ids))
        receipt_id = "ghd_" + _sha256(
            [*attempt_key, stage.attempt_seq, stage.request_sha256, bridge_hash]
        )
        writer = getattr(self.metadata_store, "record_delivery", None)
        receipt_recorded = False
        if callable(writer):
            try:
                receipt_result = writer(
                    receipt_id=receipt_id,
                    session_id=attempt_key[0],
                    turn_id=attempt_key[1],
                    api_request_id=attempt_key[2],
                    reference_at=plan.reference_at,
                    source_revision=plan.source_revision,
                    plan_digest=plan.plan_digest,
                    request_sha256=stage.request_sha256,
                    bridge_body_sha256=bridge_hash,
                    selected_anchor_ids_sha256=selected_hash,
                    selected_count=len(plan.selected_anchor_ids),
                    delivered_at=self.clock(),
                )
                receipt_recorded = type(receipt_result) is bool
            except Exception:
                receipt_recorded = False
        if not receipt_recorded:
            self._record_check(
                session_id=attempt_key[0],
                turn_id=attempt_key[1],
                api_request_id=attempt_key[2],
                status="receipt_failed",
                reason="canonical_receipt_unavailable",
                plan=plan,
                request_sha256=stage.request_sha256,
                bridge_body_sha256=bridge_hash,
            )
            return None
        self._record_check(
            session_id=attempt_key[0],
            turn_id=attempt_key[1],
            api_request_id=attempt_key[2],
            status="delivered",
            plan=plan,
            request_sha256=stage.request_sha256,
            bridge_body_sha256=bridge_hash,
        )
        return None

    def api_request_error(
        self, *, session_id: str, turn_id: str, api_request_id: str, **_kwargs: Any
    ) -> None:
        attempt_key = (
            str(session_id or "").strip(),
            str(turn_id or "").strip(),
            str(api_request_id or "").strip(),
        )
        with self._lock:
            self._executing.discard(attempt_key)
            self._sweep_expired_locked()
            projection = self._projections.pop(attempt_key, None)
            self._transport.pop(attempt_key, None)
            self._trim_locked(
                protected_turns=(projection.turn_key,) if projection else ()
            )
        return None

    def status_command(self, raw_args: str = "", **_kwargs: Any) -> str:
        session_id = str(raw_args or "").strip()
        with self._lock:
            self._sweep_expired_locked()
        reader = getattr(self.metadata_store, "status", None)
        try:
            status = reader(session_id) if callable(reader) else None
        except ValueError:
            status = {
                "schema": "global_hot_status.v1",
                "status": "invalid_session_id",
                "last_check": {},
                "last_delivery": {},
                "stores_message_bodies": False,
                "uses_delivery_cursor": False,
            }
        if status is None:
            status = {
                "schema": "global_hot_status.v1",
                "status": "metadata_unavailable",
                "last_check": {},
                "last_delivery": {},
                "stores_message_bodies": False,
                "uses_delivery_cursor": False,
            }
        return json.dumps(status, ensure_ascii=False, sort_keys=True)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._compiling.clear()
            self._projections.clear()
            self._transport.clear()
            self._executing.clear()
