from __future__ import annotations

import copy
import hashlib
import json
import unittest

from global_hot_compiler import (
    build_global_hot_context_plan,
    compile_global_hot_context,
    resolve_global_hot_context_plan,
)


def material(
    material_id: str,
    text: str,
    *,
    aliases: list[str],
    source_kind: str = "hot_basin",
    currentness: str = "current",
    priority: int = 50,
    order_identity: str | None = None,
    body_authority: str = "exact_body",
) -> dict:
    return {
        "material_id": material_id,
        "canonical_aliases": aliases,
        "source_kind": source_kind,
        "currentness": currentness,
        "priority": priority,
        "order_identity": order_identity or material_id,
        "text": text,
        "body_authority": body_authority,
    }


def body_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GlobalHotContextCompilerTests(unittest.TestCase):
    def test_plan_rejects_nul_join_alias_collision_tamper(self) -> None:
        plan = build_global_hot_context_plan(
            material_rows=[
                material("collision", "正文", aliases=["a\0b", "c"]),
            ],
            source_revision="1" * 64,
        )
        forged = copy.deepcopy(plan)
        forged["material_rows"][0]["canonical_aliases"] = ["a", "b\0c"]

        with self.assertRaises(ValueError):
            resolve_global_hot_context_plan(plan=forged)

    def test_public_digest_distinguishes_nul_join_alias_lists(self) -> None:
        first = compile_global_hot_context(
            material_rows=[material("collision", "正文", aliases=["a\0b", "c"])]
        )
        second = compile_global_hot_context(
            material_rows=[material("collision", "正文", aliases=["a", "b\0c"])]
        )

        self.assertNotEqual(first["plan_digest"], second["plan_digest"])
        self.assertNotEqual(
            first["trace"]["input_material_sha256"],
            second["trace"]["input_material_sha256"],
        )

    def test_same_canonical_body_across_anchor_and_live_hot_renders_once(self) -> None:
        result = compile_global_hot_context(
            material_rows=[
                material(
                    "hot-copy",
                    "同一条鲜活线索",
                    aliases=["shared-1"],
                    priority=100,
                    order_identity="20-copy",
                ),
                material(
                    "hot-primary",
                    "同一条鲜活线索",
                    aliases=["shared-1"],
                    priority=10,
                    order_identity="10-primary",
                ),
                material(
                    "anchor-copy",
                    "同一条鲜活线索",
                    aliases=["shared-1"],
                    source_kind="recent_anchor",
                    priority=80,
                    order_identity="12-anchor",
                ),
                material(
                    "hot-different-alias",
                    "同一条鲜活线索",
                    aliases=["different-identity"],
                    priority=90,
                    order_identity="15-different-alias",
                ),
            ],
        )

        self.assertEqual(
            result["selected_material_ids"],
            ["anchor-copy", "hot-different-alias"],
        )
        self.assertEqual(result["prompt_text"].count("同一条鲜活线索"), 2)
        self.assertEqual(result["trace"]["omission_counts"]["duplicate_exact_body"], 2)

    def test_represented_binding_requires_same_alias_and_normalized_body(self) -> None:
        same_body = "已经在最终 warm prompt 里的正文"
        different_body = "同门牌但仍然鲜活的新细节"
        source_revision = "a" * 64
        rows = [
            material("same", same_body, aliases=["shared-2"]),
            material("different", different_body, aliases=["shared-2"]),
        ]
        plan = build_global_hot_context_plan(
            material_rows=rows,
            source_revision=source_revision,
        )
        for carrier_kind in (
            "final_raw_suffix",
            "current_ephemeral",
            "recent_anchor",
            "warm_prompt",
        ):
            with self.subTest(carrier_kind=carrier_kind):
                result = resolve_global_hot_context_plan(
                    plan=plan,
                    represented_body_bindings=[{
                        "canonical_aliases": ["shared-2"],
                        "body_sha256": body_sha256(same_body),
                        "carrier_kind": carrier_kind,
                        "source_revision": source_revision,
                        "plan_digest": plan["plan_digest"],
                        "physical_selected": True,
                        "relation": "same_canonical_body",
                    }],
                )

                self.assertEqual(result["selected_material_ids"], ["different"])
                self.assertNotIn(same_body, result["prompt_text"])
                self.assertIn(different_body, result["prompt_text"])
                self.assertEqual(
                    result["trace"]["omission_counts"]["represented_exact_body"],
                    1,
                )
                self.assertGreaterEqual(
                    result["trace"]["alias_body_conflict_count"], 1
                )

    def test_old_or_unselected_binding_has_zero_omission_authority(self) -> None:
        text = "本轮仍要出现"
        source_revision = "b" * 64
        plan = build_global_hot_context_plan(
            material_rows=[material("live", text, aliases=["shared-plan"])],
            source_revision=source_revision,
        )
        valid = {
            "canonical_aliases": ["shared-plan"],
            "body_sha256": body_sha256(text),
            "carrier_kind": "warm_prompt",
            "source_revision": source_revision,
            "plan_digest": plan["plan_digest"],
            "physical_selected": True,
            "relation": "same_canonical_body",
        }
        attacks = (
            {**valid, "source_revision": "c" * 64},
            {**valid, "plan_digest": "d" * 64},
            {**valid, "physical_selected": False},
            {**valid, "relation": "different_body"},
        )

        for attack in attacks:
            with self.subTest(attack=attack):
                result = resolve_global_hot_context_plan(
                    plan=plan,
                    represented_body_bindings=[attack],
                )
                self.assertEqual(result["selected_material_ids"], ["live"])
                self.assertIn(text, result["prompt_text"])
                self.assertEqual(
                    result["trace"]["omission_counts"]["represented_exact_body"],
                    0,
                )
                self.assertEqual(result["trace"]["accepted_binding_count"], 0)
                self.assertEqual(result["trace"]["rejected_binding_count"], 1)

    def test_known_references_without_physical_binding_do_not_retire_live_bodies(self) -> None:
        result = compile_global_hot_context(
            material_rows=[
                material(
                    "canonical-source-reference",
                    "",
                    aliases=["shared-3"],
                    source_kind="linker_reference",
                    body_authority="reference_only",
                ),
                material(
                    "checkpoint-reference",
                    "",
                    aliases=["shared-3"],
                    source_kind="linker_reference",
                    body_authority="reference_only",
                    order_identity="checkpoint-reference",
                ),
                material("live", "当前仍鲜活", aliases=["shared-3"]),
                material(
                    "unresolved-a",
                    "未决方向甲",
                    aliases=["shared-3"],
                    currentness="unresolved",
                    order_identity="20-a",
                ),
                material(
                    "unresolved-b",
                    "未决方向乙",
                    aliases=["shared-3"],
                    currentness="unresolved",
                    order_identity="20-b",
                ),
            ],
        )

        self.assertEqual(
            set(result["selected_material_ids"]),
            {"live", "unresolved-a", "unresolved-b"},
        )
        self.assertIn("当前仍鲜活", result["prompt_text"])
        self.assertIn("未决方向甲", result["prompt_text"])
        self.assertIn("未决方向乙", result["prompt_text"])
        self.assertEqual(result["trace"]["omission_counts"]["reference_only"], 2)
        self.assertGreaterEqual(result["trace"]["alias_body_conflict_count"], 1)

    def test_stale_and_revised_rows_have_exact_omission_reasons(self) -> None:
        result = compile_global_hot_context(
            material_rows=[
                material("current", "留下", aliases=["current"]),
                material("stale", "过期", aliases=["stale"], currentness="stale"),
                material("revised", "已修订", aliases=["revised"], currentness="revised"),
            ],
        )

        self.assertEqual(result["selected_material_ids"], ["current"])
        self.assertEqual(result["trace"]["omission_counts"]["stale"], 1)
        self.assertEqual(result["trace"]["omission_counts"]["revised"], 1)
        self.assertNotIn("过期", result["prompt_text"])
        self.assertNotIn("已修订", result["prompt_text"])

    def test_structural_currentness_precedes_caller_priority_under_row_limit(self) -> None:
        rows = [
            material(
                "scene-max",
                "高分现场",
                aliases=["scene"],
                source_kind="scene_fact",
                priority=1_000_000,
            ),
            material(
                "current-low",
                "当前正文",
                aliases=["current"],
                source_kind="current_raw",
                priority=-100,
            ),
            material(
                "unresolved-max",
                "未决正文",
                aliases=["unresolved"],
                currentness="unresolved",
                priority=1_000_000,
            ),
            material(
                "anchor-low",
                "近期锚点",
                aliases=["anchor"],
                source_kind="recent_anchor",
                priority=-100,
            ),
        ]
        result = compile_global_hot_context(material_rows=rows, max_rows=2)

        self.assertEqual(
            result["selected_material_ids"],
            ["current-low", "anchor-low"],
        )
        self.assertNotIn("高分现场", result["prompt_text"])
        self.assertNotIn("未决正文", result["prompt_text"])
        self.assertEqual(result["trace"]["omission_counts"]["row_limit"], 2)

        char_rows = [
            {**rows[1], "text": "当" * 31},
            {**rows[3], "text": "近" * 31},
            {**rows[2], "text": "未" * 31},
        ]
        char_result = compile_global_hot_context(
            material_rows=char_rows,
            max_rows=3,
            max_chars=64,
        )
        self.assertEqual(
            char_result["selected_material_ids"],
            ["current-low", "anchor-low"],
        )
        self.assertEqual(char_result["trace"]["omission_counts"]["char_limit"], 1)

    def test_permutation_is_deterministic_and_bounds_are_honest(self) -> None:
        rows = [
            material(
                f"m-{index}",
                ("私密正文" + str(index)) * 12,
                aliases=[f"/Users/owner/private-{index}"],
                priority=100 - index,
                order_identity=f"order-{index:02d}",
            )
            for index in range(5)
        ]
        first = compile_global_hot_context(
            material_rows=rows,
            max_rows=2,
            max_chars=64,
        )
        second = compile_global_hot_context(
            material_rows=list(reversed(rows)),
            max_rows=2,
            max_chars=64,
        )

        self.assertEqual(first, second)
        self.assertLessEqual(len(first["prompt_text"]), 64)
        self.assertLessEqual(len(first["selected_material_ids"]), 2)
        self.assertTrue(first["trace"]["truncated"])
        self.assertGreater(first["trace"]["omission_counts"]["row_limit"], 0)
        self.assertGreater(first["trace"]["body_truncated_count"], 0)
        public = json.dumps(first["trace"], ensure_ascii=False)
        self.assertNotIn("私密正文", public)
        self.assertNotIn("/Users/owner", public)
        self.assertNotIn("canonical_aliases", public)
        self.assertNotIn("sample", public)
        self.assertNotIn("m-0", public)
        self.assertNotIn("order-00", public)
        self.assertFalse(first["trace"]["body_included"])

    def test_closed_rows_bindings_and_limits_reject_invalid_input(self) -> None:
        valid = material("valid", "正文", aliases=["alias"])
        binding = {
            "canonical_aliases": ["alias"],
            "body_sha256": body_sha256("正文"),
            "carrier_kind": "final_raw_suffix",
            "source_revision": "e" * 64,
            "plan_digest": "f" * 64,
            "physical_selected": True,
            "relation": "same_canonical_body",
        }
        invalid_rows = (
            {**valid, "unknown": True},
            {key: value for key, value in valid.items() if key != "material_id"},
            {**valid, "canonical_aliases": "alias"},
            {**valid, "source_kind": "provider"},
            {**valid, "source_kind": "warm_known"},
            {**valid, "currentness": "maybe"},
            {**valid, "priority": True},
            {**valid, "body_authority": "caller_claimed"},
        )
        for invalid in invalid_rows:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    compile_global_hot_context(material_rows=[invalid])

        for invalid_binding in (
            {**binding, "unknown": True},
            {**binding, "body_sha256": "not-a-digest"},
            {**binding, "carrier_kind": "checkpoint_covered"},
        ):
            with self.subTest(binding=invalid_binding):
                with self.assertRaises(ValueError):
                    plan = build_global_hot_context_plan(
                        material_rows=[valid],
                        source_revision="e" * 64,
                    )
                    resolve_global_hot_context_plan(
                        plan=plan,
                        represented_body_bindings=[invalid_binding],
                    )

        for kwargs in ({"max_rows": 0}, {"max_chars": 63}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    compile_global_hot_context(material_rows=[valid], **kwargs)


if __name__ == "__main__":
    unittest.main()
