import hashlib
import json
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_model_battle_episode as episode
from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

ORIGIN = b"authenticated train field state"


def binding(partition=ScenarioPartition.TRAIN):
    state_sha = hashlib.sha256(ORIGIN).hexdigest()
    assignment = "a" * 64
    envelope = "b" * 64
    return BattleScenarioSourceBinding(
        partition=partition,
        source_state_sha256=state_sha,
        source_slot_id="train-slot",
        source_assignment_id=assignment,
        source_context_id="c" * 64,
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=state_sha,
            envelope_sha256=envelope,
        ),
        catalog_sha256="d" * 64,
        registry_sha256="e" * 64,
        registry_source_commit="f" * 40,
    )


class Reader:
    def __init__(self):
        self.state = SimpleNamespace(map_id=22, battle_state=0)
        self.ready = True

    def read(self):
        return self.state

    def read_input_readiness(self):
        return SimpleNamespace(ready=self.ready)


class Model:
    def to_json(self):
        return '{"frozen":true}'


def harness(tmp_path, monkeypatch, *, signatures=(("one", "two"), ("three",))):
    reader = Reader()
    output = tmp_path / "episode"
    setup_calls = []
    child_calls = []

    def setup(index):
        assert (output / "plan.json").exists()
        assert (output / "origin.state").read_bytes() == ORIGIN
        setup_calls.append(index)

    def child(**kwargs):
        index = len(child_calls)
        assert kwargs["evidence_partition"] is ScenarioPartition.TRAIN
        assert kwargs["provenance"]["root_lineage_id"] == binding().root_lineage_id
        assert kwargs["maximum_decisions"] <= 8
        kwargs["setup"]()
        child_calls.append(kwargs)
        report = {
            "stop_reason": "battle_exited",
            "model_queries": len(signatures[index]),
            "decisions": [
                {
                    "choice": {
                        "observation_sha256": hashlib.sha256(signature.encode()).hexdigest()
                    },
                    "immediate_outcome": {},
                    "settled_facts": {"pp": (1, 2)},
                }
                for signature in signatures[index]
            ],
            "terminal_state_sha256": hashlib.sha256(ORIGIN).hexdigest(),
        }
        directory = kwargs["output"]
        directory.mkdir()
        (directory / "plan.json").write_text(
            json.dumps(
                {
                    "partition": "train",
                    "fit_allowed": False,
                    "provenance": kwargs["provenance"],
                }
            )
        )
        for ordinal, row in enumerate(report["decisions"]):
            step = directory / f"step-{ordinal:03d}"
            step.mkdir()
            (step / "before.state").write_bytes(ORIGIN)
            (step / "query-started.json").write_text(
                json.dumps(
                    {
                        "state_sha256": hashlib.sha256(ORIGIN).hexdigest(),
                        "observation_sha256": row["choice"]["observation_sha256"],
                    }
                )
            )
            (step / "execution-started.json").write_text(json.dumps(row["choice"]))
            (step / "outcome.json").write_text(json.dumps(row))
        (directory / "terminal.state").write_bytes(ORIGIN)
        (directory / "outcome.json").write_text(json.dumps(report))
        return report

    monkeypatch.setattr(episode, "run_learned_battle", child)
    args = dict(
        output=output,
        source=binding(),
        reader=reader,
        executor=object(),
        encoder=object(),
        model=Model(),
        snapshot=lambda: ORIGIN,
        costs=lambda: {"actions": len(setup_calls), "frames": 0},
        setup_encounter=setup,
        expected_map=22,
        maximum_encounters=len(signatures),
        maximum_actions=4,
        maximum_frames=100,
    )
    return args, reader, setup_calls, child_calls


def test_multiple_encounters_keep_one_root_and_count_distinct_decisions(tmp_path, monkeypatch):
    args, _, setup_calls, child_calls = harness(tmp_path, monkeypatch)
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "encounter_limit"
    assert result["model_queries"] == 3
    assert result["completed_decisions"] == 3
    assert result["distinct_semantic_decisions"] == 3
    assert setup_calls == [0, 1] and len(child_calls) == 2
    assert result["fit_eligible_examples"] == 0
    assert result["root_lineage_id"] == binding().root_lineage_id
    assert json.loads((args["output"] / "plan.json").read_text())["fit_allowed"] is False
    with pytest.raises(FileExistsError):
        episode.run_model_battle_train_episode(**args)
    assert setup_calls == [0, 1]


def test_duplicate_semantic_turn_does_not_create_new_example(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(
        tmp_path, monkeypatch, signatures=(("one", "one"), ("one",), ("new",))
    )
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "no_new_semantic_decision"
    assert result["model_queries"] == 3
    assert result["distinct_semantic_decisions"] == 1
    assert setup_calls == [0, 1]


@pytest.mark.parametrize("stop_reason", ["failed", "no_alternatives", "decision_limit"])
def test_child_failure_or_boundary_never_starts_another_encounter(
    tmp_path, monkeypatch, stop_reason
):
    args, _, setup_calls, child_calls = harness(tmp_path, monkeypatch)
    original = episode.run_learned_battle

    def stopped(**kwargs):
        report = original(**kwargs)
        report["stop_reason"] = stop_reason
        (kwargs["output"] / "outcome.json").write_text(json.dumps(report))
        return report

    monkeypatch.setattr(episode, "run_learned_battle", stopped)
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == stop_reason
    assert setup_calls == [0] and len(child_calls) == 1
    assert (args["output"] / "terminal.state").exists()


def test_total_decision_limit_is_global(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(tmp_path, monkeypatch)
    result = episode.run_model_battle_train_episode(**args, maximum_decisions=2)
    assert result["stop_reason"] == "decision_limit"
    assert setup_calls == [0]


def test_not_ready_field_stops_before_second_setup(tmp_path, monkeypatch):
    args, reader, setup_calls, _ = harness(tmp_path, monkeypatch)
    original = episode.run_learned_battle

    def unset_ready(**kwargs):
        report = original(**kwargs)
        reader.ready = False
        return report

    monkeypatch.setattr(episode, "run_learned_battle", unset_ready)
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "field_not_ready"
    assert setup_calls == [0]


def test_cost_overrun_never_starts_second_setup(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(tmp_path, monkeypatch)
    args["maximum_actions"] = 0
    with pytest.raises(ValueError, match="actions bound"):
        episode.run_model_battle_train_episode(**args)
    assert setup_calls == []

    args["maximum_actions"] = 1
    args["costs"] = lambda: {"actions": 2 * len(setup_calls), "frames": 0}
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "cost_bound_exceeded"
    assert setup_calls == [0]


def test_wrong_partition_or_origin_rejected_before_output(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(tmp_path, monkeypatch)
    args["source"] = binding(ScenarioPartition.DEVELOPMENT)
    with pytest.raises(ValueError, match="train source"):
        episode.run_model_battle_train_episode(**args)
    args["source"] = binding()
    args["snapshot"] = lambda: b"different"
    with pytest.raises(ValueError, match="origin differs"):
        episode.run_model_battle_train_episode(**args)
    assert not args["output"].exists() and not setup_calls


def test_child_exception_retains_terminal_and_does_not_retry(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(tmp_path, monkeypatch)

    def raise_after_setup(**kwargs):
        kwargs["setup"]()
        raise RuntimeError("injected failure")

    monkeypatch.setattr(episode, "run_learned_battle", raise_after_setup)
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "failed"
    assert result["error"]["type"] == "RuntimeError"
    assert setup_calls == [0]
    assert (args["output"] / "terminal.state").read_bytes() == ORIGIN


def test_missing_child_turn_outcome_stops_before_next_encounter(tmp_path, monkeypatch):
    args, _, setup_calls, _ = harness(tmp_path, monkeypatch)
    original = episode.run_learned_battle

    def missing_turn(**kwargs):
        report = original(**kwargs)
        (kwargs["output"] / "step-000" / "outcome.json").unlink()
        return report

    monkeypatch.setattr(episode, "run_learned_battle", missing_turn)
    result = episode.run_model_battle_train_episode(**args)
    assert result["stop_reason"] == "failed"
    assert result["error"]["type"] == "FileNotFoundError"
    assert setup_calls == [0]
