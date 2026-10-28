from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_preparation_scope import DevelopmentPreparationScope
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler, qualified_party_limit
from pokemon_red_completion.scenario_lab import ScenarioPartition


def actor(tmp_path):
    model = N(to_dict=lambda: {"candidate": True})
    scope = DevelopmentPreparationScope(
        "a" * 64, "root", "b" * 64, canonical_sha256(model.to_dict()), "c" * 64, 18
    )
    return FrozenTrainerBattler(
        None,
        model,
        tmp_path,
        "d" * 40,
        "root",
        "a" * 64,
        {},
        model_sha256="b" * 64,
        qualification_sha256=scope.identity,
        development_preparation_scope=scope,
    )


@pytest.mark.parametrize(
    "fault", [None, "source", "root", "model", "receipt", "partition", "map", "mixed"]
)
def test_exact_preparation_scope_not_global(tmp_path, fault):
    a = actor(tmp_path)
    if fault == "source":
        a.source_state_sha256 = "e" * 64
    if fault == "root":
        a.root_lineage_id = "other"
    if fault == "model":
        a.model = N(to_dict=lambda: {})
    if fault == "receipt":
        a.qualification_sha256 = "e" * 64
    if fault == "partition":
        a.source_partition = ScenarioPartition.TRAIN
    if fault == "mixed":
        a.train_funding_diagnostic = True
    assert qualified_party_limit(a.model_sha256, a.qualification_sha256) == 0
    if fault:
        with pytest.raises(ValueError):
            a.wild_authority(19 if fault == "map" else 18)
    else:
        assert a.wild_authority(18) == "scoped-wild-preparation-development"
        with pytest.raises(ValueError):
            a.require_story_identity()


@pytest.mark.parametrize("map_id,battle_state", [(19, 1), (18, 2), (18, 0)])
def test_wrong_live_mode_rejected_before_inputs(tmp_path, map_id, battle_state):
    a = actor(tmp_path)
    with pytest.raises(ValueError):
        a.run_wild_training(
            N(read=lambda: N(map_id=map_id, battle_state=battle_state)),
            None,
            expected_map=map_id,
            timing=BattleRuntimeTiming(),
            decision_guard=lambda _: None,
        )
    assert a.calls == 0 and not tuple(tmp_path.iterdir())


def test_changed_scope_and_trainer_mode_rejected(tmp_path):
    a = actor(tmp_path)
    with pytest.raises(ValueError):
        a._play(
            None,
            None,
            expected_map=18,
            timing=BattleRuntimeTiming(),
            label="test",
            decision_guard=lambda _: None,
            resume=True,
            require_win=False,
            authority=a.wild_authority(18),
        )
    a.development_preparation_scope = replace(a.development_preparation_scope, map_id=19)
    with pytest.raises(ValueError):
        a.wild_authority(19)
    assert a.calls == 0
