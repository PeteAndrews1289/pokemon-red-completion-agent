from types import SimpleNamespace

from run_red_trainer_broad_probe import broad_recipes, summarize


class Cartridge:
    species_ids = (1, 2, 3, 4, 5, 6, 7, 8)

    def species(self, species):
        return SimpleNamespace(
            national_number=species,
            teachable_moves_at_level=lambda level: (33, 34, 55, 57, 85, 98, 120, 45),
            neutral_stats=lambda level: SimpleNamespace(max_hp=level * 2),
            trainer_stats=lambda level: SimpleNamespace(max_hp=level * 2),
        )


def test_recipes_are_deterministic_varied_and_exclude_unsupported_moves():
    rows = broad_recipes(Cartridge())
    assert rows == broad_recipes(Cartridge())
    assert len(rows) == 24
    assert {r["actor_level"] for r in rows} == {16, 32, 48, 64}
    assert rows != broad_recipes(Cartridge(), seed=2026091902)
    for r in rows:
        assert r["partition"] == "train"
        assert len(r["party_reserves"]) == len(r["opponent_reserves"]) == 2
        assert [m["party_slot"] for m in r["opponent_reserves"]] == [2, 3]
        assert all(m["move_ref"].rsplit(":", 1)[1] not in {"120", "045"} for m in r["actor_moves"])


def test_empty_probe_cannot_pass_or_claim_natural_qualification():
    report = summarize([])
    assert not report["probe_passed"]
    assert not report["natural_qualified"]


def test_complete_but_worse_candidate_fails_probe():
    rows = [
        {
            "case": i,
            "arm": arm,
            "battle_won": arm == "frozen",
            "stop_reason": "battle_won" if arm == "frozen" else "party_defeated",
            "teacher_queries": 0,
            "memory_write_actions": 0,
            "decision_count": 5,
            "metrics": {
                "party_faints": 0 if arm == "frozen" else 3,
                "party_hp_lost": 10,
                "invalid_action_failures": 0,
            },
        }
        for i in range(24)
        for arm in ("frozen", "candidate")
    ]
    report = summarize(rows)
    assert report["gates"]["all_terminal_unassisted"]
    assert not report["probe_passed"]
    rows[0]["teacher_queries"] = 1
    assert not summarize(rows)["gates"]["all_terminal_unassisted"]


def test_broad_collection_cannot_silently_run_legacy_fit():
    import pytest
    from run_red_trainer_terminal_curriculum import run

    with pytest.raises(ValueError, match="separately declared fit"):
        run(SimpleNamespace(profile="broad", collect_only=False))
