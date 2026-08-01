from __future__ import annotations

import ast
import re
from pathlib import Path

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS, RedBattlePlanId

EXPECTED_RED_BATTLE_PLAN_IDS = (
    "battle-001-cascade-cerulean-rival",
    "battle-002-cascade-misty",
    "battle-003-vermilion-rocket-thief",
    "battle-004-vermilion-route-6-jr-trainer-f",
    "battle-005-vermilion-route-6-jr-trainer-m",
    "battle-006-ss-anne-rival",
    "battle-007-lavender-route-9-trainer-0",
    "battle-008-lavender-route-9-trainer-8",
    "battle-009-lavender-rock-tunnel-1f-trainer-3",
    "battle-010-lavender-rock-tunnel-b1f-trainer-7",
    "battle-011-lavender-rock-tunnel-b1f-trainer-5",
    "battle-012-lavender-rock-tunnel-b1f-trainer-3",
    "battle-013-lavender-rock-tunnel-b1f-trainer-4",
    "battle-014-lavender-rock-tunnel-b1f-trainer-0",
    "battle-015-lavender-rock-tunnel-b1f-trainer-1",
    "battle-016-lavender-rock-tunnel-1f-trainer-4",
    "battle-017-lavender-rock-tunnel-1f-trainer-5",
    "battle-018-celadon-route-8-lass",
    "battle-019-hideout-game-corner-guard",
    "battle-020-hideout-lift-key-rocket",
    "battle-021-hideout-b4-door-guard-2",
    "battle-022-hideout-b4-door-guard-1",
    "battle-023-hideout-giovanni",
    "battle-024-tower-rival",
    "battle-025-tower-4f-channeler",
    "battle-026-tower-5f-channeler",
    "battle-027-tower-6f-channeler-19",
    "battle-028-tower-6f-channeler-21",
    "battle-029-tower-6f-channeler-20",
    "battle-030-tower-7f-rocket-19",
    "battle-031-tower-7f-rocket-20",
    "battle-032-tower-7f-rocket-21",
    "battle-033-fuchsia-route-12-fisher",
    "battle-034-fuchsia-route-12-rocker",
    "battle-035-fuchsia-route-13-bird-keeper-1",
    "battle-036-fuchsia-route-13-jr-trainer-f-1",
    "battle-037-koga-juggler-3",
    "battle-038-koga-tamer-2",
    "battle-039-koga-juggler-4",
    "battle-040-koga-leader",
    "battle-041-erika-celadon-gym-lass",
    "battle-042-erika-celadon-gym-cooltrainer",
    "battle-043-erika-leader",
    "battle-044-silph-5f-rocket",
    "battle-045-silph-3f-rocket",
    "battle-046-silph-7f-rival",
    "battle-047-silph-11f-rocket",
    "battle-048-silph-11f-giovanni",
    "battle-064-dojo-blackbelt-set-5",
    "battle-065-dojo-blackbelt-set-3",
    "battle-066-dojo-blackbelt-set-4",
    "battle-067-dojo-blackbelt-set-2",
    "battle-068-dojo-karate-master",
    "battle-049-sabrina-leader",
    "battle-050-blaine-leader",
    "battle-051-giovanni-hiker-set-8",
    "battle-052-giovanni-blackbelt-set-6",
    "battle-053-giovanni-cooltrainer-set-9",
    "battle-054-giovanni-tamer-set-3",
    "battle-055-giovanni-cooltrainer-set-10",
    "battle-056-giovanni-cooltrainer-set-1",
    "battle-057-giovanni-leader",
    "battle-058-victory-road-route-22-rival",
    "battle-059-league-lorelei",
    "battle-060-league-bruno",
    "battle-061-league-agatha",
    "battle-062-league-lance",
    "battle-063-league-champion",
)

_ROUTE_MODULES = (
    "cascade.py",
    "vermilion.py",
    "ss_anne.py",
    "lavender.py",
    "celadon.py",
    "hideout.py",
    "tower.py",
    "fuchsia.py",
    "koga.py",
    "erika.py",
    "silph.py",
    "dojo.py",
    "sabrina.py",
    "blaine.py",
    "giovanni.py",
    "victory_road.py",
    "lorelei.py",
    "bruno.py",
    "agatha.py",
    "lance.py",
    "champion.py",
)

_EXPECTED_SOURCE_MEMBER_LEDGER = {
    "cascade.py": ("CASCADE_CERULEAN_RIVAL", "CASCADE_MISTY"),
    "vermilion.py": (
        "VERMILION_ROCKET_THIEF",
        "VERMILION_ROUTE_6_JR_TRAINER_F",
        "VERMILION_ROUTE_6_JR_TRAINER_M",
    ),
    "ss_anne.py": ("SS_ANNE_RIVAL",),
    "lavender.py": tuple(
        item.name
        for item in RedBattlePlanId
        if item.name.startswith("LAVENDER_")
    ),
    "celadon.py": ("CELADON_ROUTE_8_LASS",),
    "hideout.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("HIDEOUT_")
    ),
    "tower.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("TOWER_")
    ),
    "fuchsia.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("FUCHSIA_")
    ),
    "koga.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("KOGA_")
    ),
    "erika.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("ERIKA_")
    ),
    # The rival callsite is deliberately referenced in both branches of a
    # bounded recovery path; the lexical ledger pins that duplication too.
    "silph.py": (
        "SILPH_5F_ROCKET",
        "SILPH_3F_ROCKET",
        "SILPH_11F_ROCKET",
        "SILPH_11F_GIOVANNI",
        "SILPH_7F_RIVAL",
        "SILPH_7F_RIVAL",
        "SILPH_7F_RIVAL",
    ),
    "dojo.py": (
        "DOJO_BLACKBELT_SET_5",
        "DOJO_BLACKBELT_SET_3",
        "DOJO_BLACKBELT_SET_4",
        "DOJO_BLACKBELT_SET_2",
        "DOJO_KARATE_MASTER",
    ),
    "sabrina.py": ("SABRINA_LEADER",),
    "blaine.py": ("BLAINE_LEADER",),
    "giovanni.py": tuple(
        item.name for item in RedBattlePlanId if item.name.startswith("GIOVANNI_")
    ),
    "victory_road.py": ("VICTORY_ROAD_ROUTE_22_RIVAL",),
    "lorelei.py": ("LEAGUE_LORELEI",),
    "bruno.py": ("LEAGUE_BRUNO",),
    "agatha.py": ("LEAGUE_AGATHA",),
    "lance.py": ("LEAGUE_LANCE",),
    "champion.py": ("LEAGUE_CHAMPION",),
}


def test_full_adaptive_battle_route_has_68_ordered_unique_public_ids() -> None:
    assert RED_BATTLE_PLAN_IDS == EXPECTED_RED_BATTLE_PLAN_IDS
    assert len(RED_BATTLE_PLAN_IDS) == 68
    assert len(set(RED_BATTLE_PLAN_IDS)) == 68
    assert all(
        re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", battle_plan_id)
        for battle_plan_id in RED_BATTLE_PLAN_IDS
    )
    assert set(item.value for item in RedBattlePlanId) == set(RED_BATTLE_PLAN_IDS)


def test_every_planned_battle_is_referenced_by_the_production_route() -> None:
    source_root = Path(__file__).parents[1] / "src" / "pokemon_red_completion"
    referenced_members: set[str] = set()
    missing_intent_fields: list[str] = []
    missing_runtime_intents: list[str] = []
    for module_name in _ROUTE_MODULES:
        path = source_root / module_name
        source = path.read_text(encoding="utf-8")
        observed_members = tuple(
            re.findall(r"RedBattlePlanId\.([A-Z][A-Z0-9_]*)", source)
        )
        assert observed_members == _EXPECTED_SOURCE_MEMBER_LEDGER[module_name]
        referenced_members.update(observed_members)
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "run_adaptive_trainer_battle"
                and "intent" not in {keyword.arg for keyword in node.keywords}
            ):
                missing_runtime_intents.append(f"{module_name}:{node.lineno}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "BattleIntent"
                and "battle_plan_id" not in {keyword.arg for keyword in node.keywords}
            ):
                missing_intent_fields.append(f"{module_name}:{node.lineno}")

    assert referenced_members == {item.name for item in RedBattlePlanId}
    assert missing_intent_fields == []
    assert missing_runtime_intents == []
