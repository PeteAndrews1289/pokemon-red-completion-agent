from __future__ import annotations

import hashlib
import json

import pytest

from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.red_battle_cartridge_campaign import (
    RedBattleCartridgeCampaignError,
    assignment_for_case,
    execute_durable_red_battle_cartridge_campaign,
    execute_red_battle_cartridge_campaign,
    parse_red_battle_cartridge_campaign,
)

COMMIT = "a" * 40
STATE = "b" * 64
ROM = "c" * 64
BUNDLE = "d" * 64
MENUS = ("e" * 64, "f" * 64)


def _document() -> dict[str, object]:
    return {
        "campaign_id": "battle-cartridge-v2-new",
        "cases": [
            {
                "case_id": "route11-control-new",
                "coverage": "route control",
                "episode_id": "battle-cartridge-v2-route11-control-new",
                "menu_semantic_sha256": MENUS[0],
                "party_index": 0,
                "pre_encounter_wait_frames": 17,
                "venue_id": "route_11",
            },
            {
                "case_id": "diglett-cross-venue-new",
                "coverage": "cross venue",
                "episode_id": "battle-cartridge-v2-diglett-cross-venue-new",
                "menu_semantic_sha256": MENUS[1],
                "party_index": 1,
                "pre_encounter_wait_frames": 101,
                "venue_id": "digletts_cave",
            },
        ],
        "correlated_development_only": True,
        "coverage_gaps": [
            "forced_switch",
            "move_learning",
            "same_battler_move_replacement",
        ],
        "evaluation_credit": False,
        "learning_credit": False,
        "limits": {
            "maximum_campaign_actions": 12000,
            "maximum_campaign_frames": 2000000,
            "maximum_case_actions": 2000,
            "maximum_case_frames": 200000,
            "maximum_cases": 4,
            "maximum_encounter_steps": 512,
        },
        "policy": "fixed_strongest_usable_move",
        "qualification_ci_run_id": 12345,
        "retry_allowed": False,
        "rom_sha256": ROM,
        "schema": "pokemon.red.battle-cartridge-campaign.v2",
        "source": {
            "active_party_index": None,
            "expected_map": 22,
            "partition": "development",
            "party_options": [
                {
                    "hp_ratio": 1.0,
                    "menu_semantic_sha256": MENUS[0],
                    "party_index": 0,
                    "supported_move_count": 2,
                },
                {
                    "hp_ratio": 0.5,
                    "menu_semantic_sha256": MENUS[1],
                    "party_index": 1,
                    "supported_move_count": 3,
                },
            ],
            "reachable_venue_ids": ["digletts_cave", "route_11"],
            "source_commit": COMMIT,
            "source_id": "model121-exact-terminal",
            "source_kind": "field",
            "source_lineage_id": "model121-correlated-qualification-v2-new",
            "state_sha256": STATE,
        },
        "source_bundle_sha256": BUNDLE,
        "source_commit": COMMIT,
    }


def _payload(document: dict[str, object] | None = None) -> bytes:
    return (
        json.dumps(document or _document(), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "private"
    repository = tmp_path / "repository"
    root.mkdir()
    repository.mkdir()
    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=lambda path: 2 if path == root.resolve() else 1,
        git_worktree_probe=lambda path: False,
    )


def test_parse_freezes_exact_identity_limits_and_cross_venue_cases() -> None:
    payload = _payload()
    plan = parse_red_battle_cartridge_campaign(payload)

    assert plan.sha256 == hashlib.sha256(payload).hexdigest()
    assert plan.source.state_sha256 == STATE
    assert plan.source.source_commit == plan.source_commit == COMMIT
    assert plan.case_limits.maximum_actions == 2000
    assert plan.campaign_limits.maximum_frames == 2000000
    assert tuple(case.venue_id for case in plan.cases) == ("route_11", "digletts_cave")
    assignment = assignment_for_case(plan, plan.cases[1])
    assert assignment.scenario_id == "battle-cartridge-v2-new-diglett-cross-venue-new"
    assert assignment.source_lineage_id == "model121-correlated-qualification-v2-new"
    assert assignment.menu_semantic_sha256 == MENUS[1]


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda d: d.update(retry_allowed=True), "authority"),
        (lambda d: d["limits"].update(maximum_case_actions=2001), "limits"),
        (lambda d: d["cases"].pop(), "cross-venue"),
        (
            lambda d: d["cases"][1].update(episode_id=d["cases"][0]["episode_id"]),
            "identities repeat",
        ),
        (
            lambda d: d["cases"][0].update(menu_semantic_sha256="0" * 64),
            "differs from source",
        ),
        (lambda d: d["source"].update(source_commit="0" * 40), "authority"),
    ],
)
def test_parser_rejects_weakened_or_incoherent_plan(mutate, match) -> None:
    document = _document()
    mutate(document)
    with pytest.raises(RedBattleCartridgeCampaignError, match=match):
        parse_red_battle_cartridge_campaign(_payload(document))


def test_noncanonical_or_extra_fields_fail() -> None:
    document = _document()
    document["extra"] = True
    with pytest.raises(RedBattleCartridgeCampaignError, match="fields differ"):
        parse_red_battle_cartridge_campaign(_payload(document))
    with pytest.raises(RedBattleCartridgeCampaignError, match="not canonical"):
        parse_red_battle_cartridge_campaign(json.dumps(_document()).encode())


def test_campaign_runs_in_order_and_retains_shared_budget() -> None:
    plan = parse_red_battle_cartridge_campaign(_payload())
    seen = []

    def run_case(case, assignment, campaign):
        seen.append((case.case_id, assignment.scenario_id))
        campaign.actions_attempted += 2
        campaign.actions_completed += 2
        campaign.frames += 10
        return {"status": "complete", "campaign_emulator_frames": campaign.frames}

    result = execute_red_battle_cartridge_campaign(plan, run_case)
    assert result["status"] == "passed_with_declared_coverage_gaps"
    assert result["completed_cases"] == 2
    assert result["actions_attempted"] == result["actions_completed"] == 4
    assert result["emulator_frames"] == 20
    assert result["campaign_closed"] is False
    assert [item[0] for item in seen] == [case.case_id for case in plan.cases]


def test_campaign_stops_on_first_failure_without_opening_later_case() -> None:
    plan = parse_red_battle_cartridge_campaign(_payload())
    seen = []

    def run_case(case, assignment, campaign):
        del assignment
        seen.append(case.case_id)
        campaign.actions_attempted += 1
        campaign.frames += 5
        campaign.closed = True
        raise RuntimeError("private failure")

    result = execute_red_battle_cartridge_campaign(plan, run_case)
    assert result["status"] == "stopped_on_first_failure"
    assert result["completed_cases"] == 0
    assert result["failure"] == {
        "case_id": "route11-control-new",
        "episode_id": "battle-cartridge-v2-route11-control-new",
        "error_type": "RuntimeError",
    }
    assert seen == ["route11-control-new"]


def test_process_interrupt_is_never_converted_to_campaign_result() -> None:
    plan = parse_red_battle_cartridge_campaign(_payload())
    with pytest.raises(KeyboardInterrupt):
        execute_red_battle_cartridge_campaign(
            plan, lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
        )


def test_durable_campaign_claims_epoch_before_any_case_and_reopens_success(store) -> None:
    plan = parse_red_battle_cartridge_campaign(_payload())

    def run_case(case, assignment, campaign):
        del case, assignment
        campaign.cases_started += 1
        campaign.actions_attempted += 1
        campaign.actions_completed += 1
        campaign.frames += 5
        return {"status": "complete"}

    result = execute_durable_red_battle_cartridge_campaign(store, plan, run_case)
    reader = store.open_episode(plan.campaign_id)
    claim = list(reader.iter_stream("claim", max_records=1))[0]
    journal = list(reader.iter_stream("campaign_journal"))
    assert result["status"] == "passed_with_declared_coverage_gaps"
    assert claim == {
        "campaign_status_at_claim": "new",
        "failure_count": 0,
        "input_status_at_claim": "not_yet_sent",
        "resume_allowed": False,
    }
    assert [item["event"] for item in journal] == [
        "case_opening",
        "case_closed",
        "case_opening",
        "case_closed",
    ]
    with pytest.raises(Exception, match="already present"):
        execute_durable_red_battle_cartridge_campaign(
            store, plan, lambda *args: pytest.fail("consumed campaign ran")
        )


def test_durable_campaign_failure_closes_and_reopens_without_next_case(store) -> None:
    plan = parse_red_battle_cartridge_campaign(_payload())
    seen = []

    def run_case(case, assignment, campaign):
        del assignment
        seen.append(case.case_id)
        campaign.cases_started += 1
        campaign.actions_attempted += 1
        campaign.frames += 2
        campaign.closed = True
        raise RuntimeError("private failure")

    result = execute_durable_red_battle_cartridge_campaign(store, plan, run_case)
    evidence = store.read_failed_episode_diagnostic(plan.campaign_id)
    assert result["status"] == "stopped_on_first_failure"
    assert evidence.claim["failure_count"] == 0
    assert evidence.failure_diagnostic["failure"]["case_id"] == plan.cases[0].case_id
    assert evidence.failure_diagnostic["resume_allowed"] is False
    assert seen == [plan.cases[0].case_id]


def test_durable_campaign_journal_failure_before_case_prevents_input(store, monkeypatch) -> None:
    from pokemon_red_completion.private_artifacts import EpisodeWriter

    plan = parse_red_battle_cartridge_campaign(_payload())
    original = EpisodeWriter.append
    inputs = []

    def append(self, stream, record, **kwargs):
        if stream == "campaign_journal":
            raise OSError("campaign storage failure")
        return original(self, stream, record, **kwargs)

    monkeypatch.setattr(EpisodeWriter, "append", append)
    with pytest.raises(OSError, match="campaign storage failure"):
        execute_durable_red_battle_cartridge_campaign(
            store, plan, lambda *args: inputs.append(True)
        )
    assert inputs == []
