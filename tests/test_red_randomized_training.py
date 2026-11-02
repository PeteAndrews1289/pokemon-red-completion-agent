from collections import defaultdict
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_practice_factory import BattlePracticeError
from pokemon_red_completion.observation import BattleMenuPhase, RamAddress
from pokemon_red_completion.red_status_practice import condition_train_randomness
from pokemon_red_completion.scenario_lab import ScenarioPartition


def reader(**overrides):
    state = SimpleNamespace(battle_state=2, party_count=1, enemy_party_count=1,
                            active_party_index=0, enemy_party_position=0)
    for key, value in overrides.items():
        setattr(state, key, value)
    return SimpleNamespace(read=lambda: state, read_battle_menu_state=lambda _: SimpleNamespace(
        phase=BattleMenuPhase.MAIN))


def test_rng_fork_changes_only_two_verified_bytes():
    memory = defaultdict(int)
    receipt = condition_train_randomness(reader(), memory, partition=ScenarioPartition.TRAIN,
                                        seed=0xABCD)
    assert dict(memory) == {0xFFD3: 0xAB, 0xFFD4: 0xCD}
    assert (int(RamAddress.RANDOM_ADD), int(RamAddress.RANDOM_SUB)) == (0xFFD3, 0xFFD4)
    assert receipt["actor_memory_writes"] == 0
    assert receipt["teacher_memory_write_count"] == 2
    assert receipt["before"] == [0, 0] and receipt["after"] == [171, 205]


@pytest.mark.parametrize("partition",
                         [p for p in ScenarioPartition if p != ScenarioPartition.TRAIN])
def test_non_train_rng_rejected_without_read_or_write(partition):
    with pytest.raises(BattlePracticeError, match="TRAIN"):
        condition_train_randomness(None, None, partition=partition, seed=1)


@pytest.mark.parametrize("seed", [-1, 65536, True, 1.5, "12", None])
def test_invalid_rng_seed_rejected_before_access(seed):
    with pytest.raises(BattlePracticeError):
        condition_train_randomness(None, None, partition=ScenarioPartition.TRAIN, seed=seed)


@pytest.mark.parametrize("field,value", [("battle_state", 1), ("party_count", 2),
    ("enemy_party_count", 2), ("active_party_index", 1), ("enemy_party_position", 1)])
def test_wrong_boundary_no_writes(field, value):
    memory = {}
    with pytest.raises(BattlePracticeError, match="boundary"):
        condition_train_randomness(reader(**{field: value}), memory,
                                   partition=ScenarioPartition.TRAIN, seed=1)
    assert memory == {}


def test_rng_readback_failure_rejected():
    class ReadOnlyDict(defaultdict):
        def __setitem__(self, key, value):
            pass
    with pytest.raises(BattlePracticeError, match="readback"):
        condition_train_randomness(reader(), ReadOnlyDict(int),
                                   partition=ScenarioPartition.TRAIN, seed=123)


def test_changed_visible_state_rejected():
    memory = defaultdict(int)
    r = reader()
    # Use a fresh semantic object on every read, with an accidental visible change.
    r.read = lambda: SimpleNamespace(battle_state=2, party_count=1, enemy_party_count=1,
        active_party_index=0, enemy_party_position=0, visible=memory.get(0xFFD4, 0))
    with pytest.raises(BattlePracticeError, match="visible"):
        condition_train_randomness(r, memory, partition=ScenarioPartition.TRAIN, seed=123)


def test_collection_measure_retains_all_pairs_and_teacher_identity(tmp_path, monkeypatch):
    import run_red_randomized_training_collection as collector
    from test_red_outcome_value_learning import setup
    _, actor, targets, _, _ = setup()
    source = targets[0]
    slots, vectors = source["slots"], source["vectors"]
    capture = SimpleNamespace(manifest=SimpleNamespace(root_lineage_id=source["root"],
        capture_id="parent", state_sha256="a"*64), manifest_sha256="b"*64)
    monkeypatch.setattr(collector.loop.balanced, "context_view", lambda *a: (slots, vectors))
    monkeypatch.setattr(collector, "fork_rng", lambda *a: capture)
    calls = []

    def play(*args, **kw):
        calls.append(kw)
        assert args[1] is capture and args[2] is actor
        return {"decisions": [{"observation": {}}], "value": float(kw["first_slot"])}

    monkeypatch.setattr(collector.lab, "play", play)
    monkeypatch.setattr(collector, "win_conditioned_return", lambda ep: ep["value"])
    monkeypatch.setattr(collector.lab, "BattleFeatureProjector",
                        lambda _: SimpleNamespace(project=lambda _: None))
    monkeypatch.setattr(collector.loop, "project_balanced_status_moves",
                        lambda *a: SimpleNamespace(candidate_vectors=vectors,
                                                   candidate_slots=slots))
    target = collector.measure(None, capture, tmp_path / "target", None, actor,
                               list(range(32)), "c"*40, lambda: None)
    assert len(calls) == 64
    assert all(c == {"first_slot": s, "offset": 0, "horizon": 40}
               for c, s in zip(calls, slots*32, strict=True))
    assert target["returns"] == list(map(float, slots))
    assert all(len(v) == 32 for v in target["rng_returns"].values())
    assert target["teacher_continuation"] == "K_damage_only"
    assert "timing_returns" not in target
    assert (tmp_path / "target/target.json").exists()


def test_non_main_rng_boundary_rejected():
    r = reader()
    r.read_battle_menu_state = lambda _: SimpleNamespace(phase=BattleMenuPhase.MOVE)
    with pytest.raises(BattlePracticeError, match="boundary"):
        condition_train_randomness(r, {}, partition=ScenarioPartition.TRAIN, seed=123)
