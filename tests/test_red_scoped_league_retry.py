from dataclasses import replace
from types import SimpleNamespace

import pytest
import test_red_scoped_lorelei as lorelei

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedLeagueRetryController,
    story_league_controller,
)


def controller(tmp_path, objective="defeat_lorelei"):
    old = lorelei.controller(tmp_path)
    targets = {
        "defeat_lorelei": (MapId.LORELEIS_ROOM, (244, 44, 1), EventFlag.BEAT_LORELEI),
        "defeat_bruno": (MapId.BRUNOS_ROOM, (233, 33, 1), EventFlag.BEAT_BRUNO),
        "defeat_agatha": (MapId.AGATHAS_ROOM, (246, 46, 1), EventFlag.BEAT_AGATHA),
        "defeat_lance": (MapId.LANCES_ROOM, (247, 47, 1), EventFlag.BEAT_LANCES_ROOM_TRAINER),
    }
    room, identity, event = targets[objective]
    contract = replace(
        old.contract,
        objective_id=objective,
        map_id=int(room),
        trainer_identity=identity,
        defeated_event=int(event),
    )
    old.battler.development_story_scope = replace(
        old.battler.development_story_scope, contract=contract
    )
    old.battler.qualification_sha256 = old.battler.development_story_scope.identity
    return ScopedAssistedLeagueRetryController(old.battler, contract, old.admission, 80)


@pytest.mark.parametrize(
    "objective", ["defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance"]
)
def test_retry_requires_native_rematch_and_its_exact_target(tmp_path, objective):
    ctl = controller(tmp_path, objective)
    rt = SimpleNamespace(league_story_battle_controller=ctl)
    assert story_league_controller(rt, objective, rematch=True) is ctl
    with pytest.raises(ValueError):
        story_league_controller(rt, objective, rematch=False)
    with pytest.raises(ValueError):
        story_league_controller(rt, "defeat_champion", rematch=True)
    ctl.require_objective(objective)  # Inner battle uses the already bound target.


@pytest.mark.parametrize(
    "fault", ["source", "model", "work", "assistance", "contract", "partition", "budget"]
)
def test_retry_rechecks_original_scoped_guards(tmp_path, monkeypatch, fault):
    ctl = controller(tmp_path)
    monkeypatch.setattr(lorelei, "controller", lambda _: ctl)
    lorelei.test_scoped_lorelei_rejects_changed_authority(tmp_path, fault)


@pytest.mark.parametrize(
    "objective,deficit,allowed",
    [
        ("defeat_lorelei", 5, True),
        ("defeat_lorelei", 7, False),
        ("defeat_agatha", 6, True),
        ("defeat_lance", 7, True),
        ("defeat_lance", 9, True),
        ("defeat_lance", 10, False),
        ("defeat_lance", 100, False),
        ("defeat_bruno", 6, False),
    ],
)
def test_retry_level_screen_stays_target_specific(
    monkeypatch, tmp_path, objective, deficit, allowed
):
    from test_red_trainer_story import fixture

    from pokemon_red_completion.red_trainer_story import RedTrainerStoryError

    skill, _, _, _, _ = fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path, objective)
    skill.runtime.league_story_battle_controller = ctl

    def build():
        return replace(
            skill,
            objective_id=objective,
            rematch=True,
            recovery_controller=ctl.controller_name,
            maximum_level_deficit=deficit,
        )

    if allowed:
        build()._require_controller_contract()
    else:
        with pytest.raises(RedTrainerStoryError):
            build()


@pytest.mark.parametrize("objective", ["defeat_agatha", "defeat_lance"])
def test_prospective_retry_deficit_requires_exact_current_development_scope(
    monkeypatch, tmp_path, objective
):
    from test_red_trainer_story import fixture

    from pokemon_red_completion.red_trainer_story import RedTrainerStoryError
    from pokemon_red_completion.scenario_lab import ScenarioPartition

    skill, _, inputs, _, _ = fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path, objective)
    ctl.declared_level_deficit = 30
    skill.runtime.league_story_battle_controller = ctl
    options = dict(
        objective_id=objective,
        rematch=True,
        recovery_controller=ctl.controller_name,
        maximum_level_deficit=30,
    )
    replace(skill, **options)._require_controller_contract()
    with pytest.raises(RedTrainerStoryError):
        replace(skill, **(options | {"maximum_level_deficit": 29}))
    ctl.battler.source_partition = ScenarioPartition.TRAIN
    with pytest.raises(ValueError):
        replace(skill, **options)
    assert not inputs and ctl.battler.calls == 0


@pytest.mark.parametrize("objective", [
    "defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance",
])
def test_learned_retry_tactics_require_explicit_scope_without_control_overrides(
    tmp_path, objective,
):
    from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope

    ctl = controller(tmp_path, objective)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope,
        diagnostic_stay_when_productive=False, diagnostic_status_entry=True,
        allow_learned_tactics=True)
    actor.qualification_sha256 = actor.development_story_scope.identity
    ctl.declared_stay_when_productive = False
    ctl.require_identity()
    assert DevelopmentStoryScope.from_document(actor.development_story_scope.document()) == (
        actor.development_story_scope
    )
    assert actor.development_story_scope.diagnostic_prompt_stay is False
    assert actor.calls == 0
    ctl.declared_stay_when_productive = True
    with pytest.raises(ValueError):
        ctl.require_identity()


@pytest.mark.parametrize("fault", ["source", "content", "partition", "receipt", "work"])
def test_learned_retry_tactics_do_not_relax_source_weight_or_partition_guards(tmp_path, fault):
    from pokemon_red_completion.scenario_lab import ScenarioPartition

    ctl = controller(tmp_path)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope,
        diagnostic_stay_when_productive=False, allow_learned_tactics=True)
    actor.qualification_sha256 = actor.development_story_scope.identity
    ctl.declared_stay_when_productive = False
    if fault == "source":
        actor.source_state_sha256 = "e" * 64
    elif fault == "content":
        actor.model = SimpleNamespace(to_dict=lambda: {"changed": True})
    elif fault == "partition":
        actor.source_partition = ScenarioPartition.TRAIN
    elif fault == "receipt":
        actor.qualification_sha256 = "f" * 64
    elif fault == "work":
        ctl.admission = b"different order"
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert actor.calls == 0


@pytest.mark.parametrize("field", ["diagnostic_stay_when_productive",
                                    "diagnostic_prompt_stay", "diagnostic_status_release"])
def test_learned_tactics_cannot_hide_a_supplied_control_override(tmp_path, field):
    ctl = controller(tmp_path)
    with pytest.raises(ValueError, match="no supplied control"):
        replace(ctl.battler.development_story_scope,
                allow_learned_tactics=True, **{field: True})


@pytest.mark.parametrize("invalid", [1, 0, None, "true"])
def test_learned_tactics_permission_must_be_a_boolean(tmp_path, invalid):
    ctl = controller(tmp_path)
    with pytest.raises(ValueError, match="learned tactics"):
        replace(ctl.battler.development_story_scope, allow_learned_tactics=invalid)
