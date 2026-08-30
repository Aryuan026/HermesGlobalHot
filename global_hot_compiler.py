from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping


_GLOBAL_HOT_MATERIAL_KEYS = {
    "material_id",
    "canonical_aliases",
    "source_kind",
    "currentness",
    "priority",
    "order_identity",
    "text",
    "body_authority",
}
_GLOBAL_HOT_BINDING_KEYS = {
    "canonical_aliases",
    "body_sha256",
    "carrier_kind",
    "source_revision",
    "plan_digest",
    "physical_selected",
    "relation",
}
_GLOBAL_HOT_NORMALIZED_MATERIAL_KEYS = _GLOBAL_HOT_MATERIAL_KEYS | {"body_sha256"}
_GLOBAL_HOT_PLAN_KEYS = {
    "schema",
    "source_revision",
    "plan_digest",
    "material_rows",
}
_GLOBAL_HOT_SOURCE_KINDS = {
    "current_raw",
    "recent_anchor",
    "continuity",
    "hot_basin",
    "agent_state",
    "unfinished_attention",
    "relationship",
    "scene_fact",
    "linker_reference",
}
_GLOBAL_HOT_CURRENTNESS = {"current", "unresolved", "stale", "revised"}
_GLOBAL_HOT_BODY_AUTHORITIES = {"exact_body", "reference_only"}
_GLOBAL_HOT_CARRIER_KINDS = {
    "final_raw_suffix",
    "current_ephemeral",
    "recent_anchor",
    "warm_prompt",
}
_GLOBAL_HOT_BINDING_RELATIONS = {"same_canonical_body", "different_body"}
_GLOBAL_HOT_SOURCE_PRECEDENCE = {
    "current_raw": 0,
    "recent_anchor": 1,
    "continuity": 2,
    "hot_basin": 3,
    "agent_state": 4,
    "unfinished_attention": 5,
    "relationship": 6,
    "scene_fact": 7,
    "linker_reference": 8,
}
_GLOBAL_HOT_MAX_INPUT_ROWS = 128
_GLOBAL_HOT_MAX_BINDINGS = 128
_GLOBAL_HOT_MAX_TEXT_CHARS = 16_384


def _global_hot_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _global_hot_is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _global_hot_normalized_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _global_hot_aliases(value: Any) -> List[str]:
    if not isinstance(value, list) or not value or len(value) > 64:
        raise ValueError("global_hot_canonical_aliases_invalid")
    aliases = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("global_hot_canonical_aliases_invalid")
        alias = item.strip()
        if not alias or len(alias) > 256:
            raise ValueError("global_hot_canonical_aliases_invalid")
        aliases.append(alias)
    if len(set(aliases)) != len(aliases):
        raise ValueError("global_hot_canonical_aliases_invalid")
    return sorted(aliases)


def _normalize_global_hot_material(value: Mapping[str, Any]) -> Dict[str, Any]:
    row = dict(value)
    if set(row) != _GLOBAL_HOT_MATERIAL_KEYS:
        raise ValueError("global_hot_material_schema_invalid")
    material_id = row.get("material_id")
    order_identity = row.get("order_identity")
    source_kind = row.get("source_kind")
    currentness = row.get("currentness")
    priority = row.get("priority")
    body_authority = row.get("body_authority")
    text = row.get("text")
    if (
        not isinstance(material_id, str)
        or not material_id.strip()
        or len(material_id.strip()) > 180
        or not isinstance(order_identity, str)
        or not order_identity.strip()
        or len(order_identity.strip()) > 256
        or source_kind not in _GLOBAL_HOT_SOURCE_KINDS
        or currentness not in _GLOBAL_HOT_CURRENTNESS
        or type(priority) is not int
        or not -1_000_000 <= priority <= 1_000_000
        or body_authority not in _GLOBAL_HOT_BODY_AUTHORITIES
        or not isinstance(text, str)
    ):
        raise ValueError("global_hot_material_value_invalid")
    normalized_text = _global_hot_normalized_text(text)
    if len(normalized_text) > _GLOBAL_HOT_MAX_TEXT_CHARS:
        raise ValueError("global_hot_material_text_invalid")
    if body_authority == "exact_body" and not normalized_text:
        raise ValueError("global_hot_material_text_invalid")
    if body_authority == "reference_only" and normalized_text:
        raise ValueError("global_hot_reference_body_invalid")
    if source_kind == "linker_reference" and body_authority != "reference_only":
        raise ValueError("global_hot_linker_authority_invalid")
    if source_kind != "linker_reference" and body_authority != "exact_body":
        raise ValueError("global_hot_material_authority_invalid")
    return {
        "material_id": material_id.strip(),
        "canonical_aliases": _global_hot_aliases(row.get("canonical_aliases")),
        "source_kind": source_kind,
        "currentness": currentness,
        "priority": priority,
        "order_identity": order_identity.strip(),
        "text": normalized_text,
        "body_authority": body_authority,
        "body_sha256": _global_hot_sha256(normalized_text) if normalized_text else "",
    }


def _normalize_global_hot_binding(value: Mapping[str, Any]) -> Dict[str, Any]:
    row = dict(value)
    if (
        set(row) != _GLOBAL_HOT_BINDING_KEYS
        or not _global_hot_is_sha256(row.get("body_sha256"))
        or not _global_hot_is_sha256(row.get("source_revision"))
        or not _global_hot_is_sha256(row.get("plan_digest"))
        or row.get("carrier_kind") not in _GLOBAL_HOT_CARRIER_KINDS
        or type(row.get("physical_selected")) is not bool
        or row.get("relation") not in _GLOBAL_HOT_BINDING_RELATIONS
    ):
        raise ValueError("global_hot_body_binding_invalid")
    return {
        "canonical_aliases": _global_hot_aliases(row.get("canonical_aliases")),
        "body_sha256": row.get("body_sha256"),
        "carrier_kind": row.get("carrier_kind"),
        "source_revision": row.get("source_revision"),
        "plan_digest": row.get("plan_digest"),
        "physical_selected": row.get("physical_selected"),
        "relation": row.get("relation"),
    }


def _global_hot_digest(rows: List[str]) -> str:
    return _global_hot_sha256(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    )


def _global_hot_structure_rank(row: Mapping[str, Any]) -> int:
    source_kind = row.get("source_kind")
    if source_kind == "current_raw":
        return 0
    if source_kind == "recent_anchor":
        return 1
    if row.get("currentness") == "unresolved":
        return 2
    if source_kind in {"unfinished_attention", "scene_fact"}:
        return 3
    if source_kind in {"relationship", "agent_state"}:
        return 4
    return 5


def _global_hot_conflict_trace(
    materials: List[Dict[str, Any]], bindings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    alias_bodies: Dict[str, set[str]] = {}
    for row in materials:
        for alias in row["canonical_aliases"]:
            alias_bodies.setdefault(alias, set()).add(row["body_sha256"])
    for row in bindings:
        for alias in row["canonical_aliases"]:
            alias_bodies.setdefault(alias, set()).add(row["body_sha256"])
    conflicts = [
        f"{_global_hot_sha256(alias)}:{','.join(sorted(bodies))}"
        for alias, bodies in alias_bodies.items()
        if len(bodies) > 1
    ]
    conflicts.sort()
    return {
        "alias_body_conflict_count": len(conflicts),
        "alias_body_conflict_sha256": _global_hot_digest(conflicts),
    }


def _dedupe_global_hot_materials(
    rows: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], int]:
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    alias_sets = [set(row["canonical_aliases"]) for row in rows]
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if (
                rows[left]["body_sha256"] == rows[right]["body_sha256"]
                and alias_sets[left] & alias_sets[right]
            ):
                union(left, right)
    components: Dict[int, List[Dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        components.setdefault(find(index), []).append(row)
    winners = [
        min(
            component,
            key=lambda row: (
                _global_hot_structure_rank(row),
                -row["priority"],
                row["order_identity"],
                _GLOBAL_HOT_SOURCE_PRECEDENCE[row["source_kind"]],
                row["material_id"],
            ),
        )
        for component in components.values()
    ]
    return winners, len(rows) - len(winners)


def _global_hot_material_digest_rows(materials: List[Dict[str, Any]]) -> List[str]:
    return sorted(
        json.dumps(
            {
                "material_id_sha256": _global_hot_sha256(row["material_id"]),
                "alias_sha256": _global_hot_digest(row["canonical_aliases"]),
                "source_kind": row["source_kind"],
                "currentness": row["currentness"],
                "priority": row["priority"],
                "order_identity_sha256": _global_hot_sha256(row["order_identity"]),
                "body_sha256": row["body_sha256"],
                "body_authority": row["body_authority"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in materials
    )


def _global_hot_plan_digest(
    *, source_revision: str, materials: List[Dict[str, Any]]
) -> str:
    return _global_hot_sha256(
        json.dumps(
            {
                "schema": "global_hot_context_plan.v1",
                "source_revision": source_revision,
                "material_rows_sha256": _global_hot_digest(
                    _global_hot_material_digest_rows(materials)
                ),
                "material_count": len(materials),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _normalize_global_hot_material_rows(
    material_rows: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(material_rows, list) or len(material_rows) > _GLOBAL_HOT_MAX_INPUT_ROWS:
        raise ValueError("global_hot_compile_bounds_invalid")
    materials: List[Dict[str, Any]] = []
    for row in material_rows:
        if not isinstance(row, Mapping):
            raise ValueError("global_hot_material_schema_invalid")
        materials.append(_normalize_global_hot_material(row))
    material_ids = [row["material_id"] for row in materials]
    if len(set(material_ids)) != len(material_ids):
        raise ValueError("global_hot_material_id_conflict")
    return sorted(materials, key=lambda row: row["material_id"])


def build_global_hot_context_plan(
    *,
    material_rows: List[Mapping[str, Any]],
    source_revision: str,
) -> Dict[str, Any]:
    """Build a private immutable plan before physical prompt carriers are selected."""

    if not _global_hot_is_sha256(source_revision):
        raise ValueError("global_hot_source_revision_invalid")
    materials = _normalize_global_hot_material_rows(material_rows)
    return {
        "schema": "global_hot_context_plan.v1",
        "source_revision": source_revision,
        "plan_digest": _global_hot_plan_digest(
            source_revision=source_revision,
            materials=materials,
        ),
        "material_rows": materials,
    }


def _read_global_hot_context_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise ValueError("global_hot_plan_invalid")
    value = dict(plan)
    source_revision = value.get("source_revision")
    plan_digest = value.get("plan_digest")
    rows = value.get("material_rows")
    if (
        set(value) != _GLOBAL_HOT_PLAN_KEYS
        or value.get("schema") != "global_hot_context_plan.v1"
        or not _global_hot_is_sha256(source_revision)
        or not _global_hot_is_sha256(plan_digest)
        or not isinstance(rows, list)
        or len(rows) > _GLOBAL_HOT_MAX_INPUT_ROWS
    ):
        raise ValueError("global_hot_plan_invalid")
    materials: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _GLOBAL_HOT_NORMALIZED_MATERIAL_KEYS:
            raise ValueError("global_hot_plan_invalid")
        original = {key: row.get(key) for key in _GLOBAL_HOT_MATERIAL_KEYS}
        normalized = _normalize_global_hot_material(original)
        if normalized != dict(row):
            raise ValueError("global_hot_plan_invalid")
        materials.append(normalized)
    material_ids = [row["material_id"] for row in materials]
    if (
        len(set(material_ids)) != len(material_ids)
        or materials != sorted(materials, key=lambda row: row["material_id"])
        or _global_hot_plan_digest(
            source_revision=source_revision,
            materials=materials,
        )
        != plan_digest
    ):
        raise ValueError("global_hot_plan_invalid")
    return {
        "source_revision": source_revision,
        "plan_digest": plan_digest,
        "material_rows": materials,
    }


def resolve_global_hot_context_plan(
    *,
    plan: Mapping[str, Any],
    represented_body_bindings: List[Mapping[str, Any]] | None = None,
    max_rows: int = 12,
    max_chars: int = 4_000,
) -> Dict[str, Any]:
    """Resolve one private plan against exact, physically selected prompt bindings."""

    if (
        type(max_rows) is not int
        or not 1 <= max_rows <= 64
        or type(max_chars) is not int
        or not 64 <= max_chars <= 32_768
    ):
        raise ValueError("global_hot_compile_bounds_invalid")
    normalized_plan = _read_global_hot_context_plan(plan)
    materials = normalized_plan["material_rows"]
    source_revision = normalized_plan["source_revision"]
    plan_digest = normalized_plan["plan_digest"]
    binding_rows = [] if represented_body_bindings is None else represented_body_bindings
    if not isinstance(binding_rows, list) or len(binding_rows) > _GLOBAL_HOT_MAX_BINDINGS:
        raise ValueError("global_hot_binding_bounds_invalid")
    bindings: List[Dict[str, Any]] = []
    for row in binding_rows:
        if not isinstance(row, Mapping):
            raise ValueError("global_hot_body_binding_invalid")
        bindings.append(_normalize_global_hot_binding(row))
    accepted_bindings = [
        row
        for row in bindings
        if row["source_revision"] == source_revision
        and row["plan_digest"] == plan_digest
        and row["physical_selected"] is True
        and row["relation"] == "same_canonical_body"
    ]

    omission_counts = {
        "stale": 0,
        "revised": 0,
        "reference_only": 0,
        "represented_exact_body": 0,
        "duplicate_exact_body": 0,
        "row_limit": 0,
        "char_limit": 0,
    }
    eligible: List[Dict[str, Any]] = []
    for row in materials:
        if row["currentness"] in {"stale", "revised"}:
            omission_counts[row["currentness"]] += 1
            continue
        if row["body_authority"] == "reference_only":
            omission_counts["reference_only"] += 1
            continue
        aliases = set(row["canonical_aliases"])
        if any(
            aliases & set(binding["canonical_aliases"])
            and row["body_sha256"] == binding["body_sha256"]
            for binding in accepted_bindings
        ):
            omission_counts["represented_exact_body"] += 1
            continue
        eligible.append(row)

    deduped, duplicate_count = _dedupe_global_hot_materials(eligible)
    omission_counts["duplicate_exact_body"] = duplicate_count
    ranked = sorted(
        deduped,
        key=lambda row: (
            _global_hot_structure_rank(row),
            -row["priority"],
            row["order_identity"],
            _GLOBAL_HOT_SOURCE_PRECEDENCE[row["source_kind"]],
            row["material_id"],
        ),
    )
    bounded = ranked[:max_rows]
    omission_counts["row_limit"] = len(ranked) - len(bounded)

    prompt_parts: List[str] = []
    selected_ids: List[str] = []
    body_truncated_count = 0
    for index, row in enumerate(bounded):
        separator = "\n\n" if prompt_parts else ""
        remaining = max_chars - len("".join(prompt_parts)) - len(separator)
        if remaining <= 0:
            omission_counts["char_limit"] += len(bounded) - index
            break
        text = row["text"]
        if len(text) <= remaining:
            prompt_parts.extend([separator, text])
            selected_ids.append(row["material_id"])
            continue
        rendered = text[: max(0, remaining - 1)] + "…"
        prompt_parts.extend([separator, rendered[:remaining]])
        selected_ids.append(row["material_id"])
        body_truncated_count += 1
        omission_counts["char_limit"] += len(bounded) - index - 1
        break
    prompt_text = "".join(prompt_parts)
    omitted_count = sum(omission_counts.values())
    conflict_trace = _global_hot_conflict_trace(eligible, accepted_bindings)
    return {
        "schema": "global_hot_context_compilation.v1",
        "source_revision": source_revision,
        "plan_digest": plan_digest,
        "prompt_text": prompt_text,
        "selected_material_ids": selected_ids,
        "trace": {
            "schema": "global_hot_context_compilation_trace.v1",
            "input_count": len(materials),
            "normalized_count": len(materials),
            "represented_binding_count": len(bindings),
            "accepted_binding_count": len(accepted_bindings),
            "rejected_binding_count": len(bindings) - len(accepted_bindings),
            "eligible_count": len(eligible),
            "selected_count": len(selected_ids),
            "omitted_count": omitted_count,
            "omission_counts": omission_counts,
            **conflict_trace,
            "input_material_sha256": _global_hot_digest(
                _global_hot_material_digest_rows(materials)
            ),
            "selected_material_sha256": _global_hot_digest(selected_ids),
            "rendered_char_count": len(prompt_text),
            "max_rows": max_rows,
            "max_chars": max_chars,
            "truncated": bool(
                omission_counts["row_limit"]
                or omission_counts["char_limit"]
                or body_truncated_count
            ),
            "body_truncated_count": body_truncated_count,
            "body_included": False,
        },
    }


def compile_global_hot_context(
    *,
    material_rows: List[Mapping[str, Any]],
    represented_body_bindings: List[Mapping[str, Any]] | None = None,
    max_rows: int = 12,
    max_chars: int = 4_000,
) -> Dict[str, Any]:
    """Compatibility wrapper for compile-only callers with no physical binding proof."""

    if represented_body_bindings:
        raise ValueError("global_hot_plan_binding_required")
    plan = build_global_hot_context_plan(
        material_rows=material_rows,
        source_revision=_global_hot_sha256("global_hot_compile_only_revision.v1"),
    )
    return resolve_global_hot_context_plan(
        plan=plan,
        represented_body_bindings=[],
        max_rows=max_rows,
        max_chars=max_chars,
    )
