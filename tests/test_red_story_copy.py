import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest
from test_red_trainer_battle_lifecycle import fixture as lifecycle_fixture
from test_red_trainer_practice_fit import _target

from pokemon_red_completion import red_story_copy as copy
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_learned_trainer import (
    load_story_trainer_model,
    qualified_party_limit,
)
from pokemon_red_completion.red_trainer_battle_lifecycle import continue_learned_trainer_battle
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


@pytest.fixture
def setup(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    source = campaign / "source.state"
    source.write_bytes(b"protected source")
    output = tmp_path / "isolated-copy"
    output.mkdir()
    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=1, require_corpus_floor=False
    )
    payload = json.dumps(model.to_dict()).encode()
    contract = copy.StoryTrainerContract(
        "defeat_test", "cartridge-trainer-story", 61, (230, 30, 4), 8, 480
    )
    scope = copy.StoryCopyScope(
        source,
        sha256(source.read_bytes()).hexdigest(),
        campaign,
        output,
        sha256(payload).hexdigest(),
        canonical_sha256(model.to_dict()),
        contract,
    )
    scope.load_model(payload)
    battler = copy.StoryCopyBattler(
        scope,
        SimpleNamespace(save_state_bytes=lambda: b"terminal"),
        model,
        "a" * 40,
        "development-root",
        {},
    )
    return scope, battler, payload


@pytest.mark.parametrize(
    "fault",
    ["campaign_output", "ancestor_output", "alias", "source", "model", "noncopy", "decisions"],
)
def test_scope_rejects_mismatches_without_actions(setup, fault):
    scope, battler, payload = setup
    if fault == "campaign_output":
        scope = replace(scope, output=scope.campaign_directory / "new")
    elif fault == "ancestor_output":
        scope = replace(scope, output=scope.campaign_directory.parent)
    elif fault == "alias":
        link = scope.output.parent / "alias"
        link.symlink_to(scope.output, target_is_directory=True)
        scope = replace(scope, output=link)
    elif fault == "source":
        scope = replace(scope, source_sha256="0" * 64)
    elif fault == "model":
        payload += b" "
    elif fault == "noncopy":
        scope = replace(scope, isolated_copy=False)
    else:
        scope = replace(scope, maximum_decisions=81)
    with pytest.raises(ValueError):
        scope.load_model(payload)
    assert battler.calls == 0


def test_copy_is_not_default_deployment(setup):
    scope, battler, payload = setup
    with pytest.raises(ValueError):
        load_story_trainer_model(payload, b"copy permission")
    assert qualified_party_limit(scope.model_sha256) == 0
    with pytest.raises(ValueError):
        battler.require_scope(replace(scope))
    with pytest.raises(ValueError):
        scope.require_model(None)


@pytest.mark.parametrize("outcome", ["won", "lost", "unresolved"])
def test_copy_reuses_unchanged_native_settlement(setup, monkeypatch, outcome):
    scope, battler, _ = setup
    state, reader, fake, executor = lifecycle_fixture(outcome)
    monkeypatch.setattr(battler, "continue_battle", fake.continue_battle)
    result = continue_learned_trainer_battle(
        battler,
        reader,
        executor,
        trainer_identity=scope.contract.trainer_identity,
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        copy_scope=scope,
    )
    assert result.outcome == outcome
    assert result.field_ready is (outcome != "unresolved")


@pytest.mark.parametrize("fault", ["story", "reward", "target", "fake", "budget"])
def test_lifecycle_rejects_expanded_copy_before_read(setup, fault):
    scope, battler, _ = setup
    args = dict(
        trainer_identity=scope.contract.trainer_identity,
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        copy_scope=scope,
    )
    if fault == "story":
        args["story_authority"] = True
    elif fault == "reward":
        args["victory_items"] = ((1, 1),)
    elif fault == "target":
        args["defeated_event"] = 9
    elif fault == "fake":
        battler = SimpleNamespace()
    else:
        args["remaining_decisions"] = 81
    with pytest.raises(ValueError):
        continue_learned_trainer_battle(battler, None, None, **args)


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("mechanics,diagnostic", [(False, False), (True, False), (True, True)])
def test_copy_actor_retains_terminal_and_cannot_repeat(
    setup, monkeypatch, fails, mechanics, diagnostic
):
    scope, battler, _ = setup
    scope = replace(
        scope, mechanics_aware_choices=mechanics, diagnostic_stay_when_productive=diagnostic
    )
    battler.scope = scope
    raw = SimpleNamespace(battle_state=2, map_id=61)
    reader = SimpleNamespace(read=lambda: raw, read_active_trainer_identity=lambda: (230, 30, 4))
    encoder = SimpleNamespace(snapshot_from_raw=lambda _: SimpleNamespace(to_dict=lambda: {}))
    monkeypatch.setattr(
        copy.PokemonRedObservationEncoder, "from_state_reader", lambda *a, **k: encoder
    )

    def manifest(**kw):
        assert kw["partition"].value == "development"
        return b"manifest"

    monkeypatch.setattr(copy, "build_battle_scenario_capture_payload", manifest)
    capture = SimpleNamespace(manifest=SimpleNamespace(capture_id="copy"))
    monkeypatch.setattr(copy, "open_battle_scenario_capture", lambda *a: capture)

    def play(_capture, **kw):
        assert kw["allow_status_moves"] is True
        assert "allow_forced_struggle" not in kw
        assert kw["policy"].model is battler.model
        assert kw["policy"].mechanics_aware_choices is mechanics
        assert kw["policy"].diagnostic_stay_when_productive is diagnostic
        if fails:
            raise RuntimeError("unsupported boundary")
        return SimpleNamespace(public_dict=lambda: {"battle_won": False})

    monkeypatch.setattr(copy, "run_live_red_trainer_practice_episode", play)

    def run():
        return battler.continue_battle(
            reader,
            object(),
            expected_map=61,
            timing=BattleRuntimeTiming(),
            decision_guard=lambda _: None,
        )

    if fails:
        with pytest.raises(RuntimeError):
            run()
    else:
        run()
    assert (scope.output / "battle/final.state").read_bytes() == b"terminal"
    assert verify_trainer_practice_event_log(scope.output / "battle/events")["terminal_event"] == (
        "run_failed" if fails else "run_finished"
    )
    with pytest.raises(FileExistsError):
        run()
    assert battler.calls == 1


def test_mechanics_copy_setting_is_explicit_boolean(setup):
    scope, _, _ = setup
    with pytest.raises(ValueError, match="invalid isolated"):
        replace(scope, mechanics_aware_choices=1).validate()


def test_consumed_controller_does_not_advance_text(setup):
    scope, battler, _ = setup
    (scope.output / "battle").mkdir()
    actor = copy.StoryCopyController(battler)
    with pytest.raises(ValueError, match="consumed"):
        actor.run(
            None,
            None,
            None,
            expected_map=61,
            intent=BattleIntent("defeat_test", "cartridge-trainer-story"),
            timing=BattleRuntimeTiming(),
            label="test",
            consume_battle_start_schedule=False,
            move_decision_guard=lambda _: None,
        )


def test_explicit_resolver_does_not_expand_default_or_rematch(setup):
    from pokemon_red_completion.red_lorelei_story import story_league_controller

    scope, battler, _ = setup
    actor = copy.StoryCopyController(battler)
    runtime = SimpleNamespace(league_story_battle_controller=actor, league_battle_controller=None)
    assert story_league_controller(runtime, "defeat_test") is actor
    with pytest.raises(ValueError):
        story_league_controller(runtime, "defeat_other")
    with pytest.raises(ValueError):
        story_league_controller(runtime, "defeat_test", rematch=True)
    runtime.league_battle_controller = object()
    with pytest.raises(ValueError):
        story_league_controller(runtime, "defeat_test")


@pytest.mark.parametrize(
    "fault", [None, "all_fainted", "negative_hp", "payout", "event", "bag", "species", "fake_owner"]
)
def test_copy_outer_victory_allows_faint_but_preserves_other_guards(setup, monkeypatch, fault):
    from test_red_trainer_funding_battle import ScriptedEnvironment, make_candidate, make_state

    from pokemon_red_completion.red_trainer_funding_battle import (
        TrainerFundingBattleError,
        run_prepared_trainer_funding,
    )

    scope, battler, _ = setup
    actor = copy.StoryCopyController(battler)
    initial = make_state(map_id=61, hp=(50, 4))
    env = ScriptedEnvironment(initial, battle_identity=(230, 30, 230, 4), trainer_number=4)
    env.transitions = [(replace(initial, battle_state=2), False, True)]
    target = make_candidate(tc=230, ts=4, flag=8, pay=480)
    target = replace(target, trainer=replace(target.trainer, map_id=61))

    def play(self, reader, actions, move_slot_policy, **kw):
        # Learned lifecycle owns combat; this fake isolates the real outer
        # post-victory verifier that rejected the retained Lance victory.
        flags = bytearray(initial.event_flags)
        if fault != "event":
            flags[1] |= 1
        env.state = replace(
            initial,
            battle_state=0,
            battle_result=0,
            party_hp=(0, 0)
            if fault == "all_fainted"
            else (-1, 0)
            if fault == "negative_hp"
            else (30, 0),
            party_species_ids=(1, 2) if fault == "species" else initial.party_species_ids,
            bag_items=() if fault == "bag" else initial.bag_items,
            event_flags=bytes(flags),
            player_money=500 if fault == "payout" else 980,
        )
        return env.state

    monkeypatch.setattr(copy.StoryCopyController, "run", play)
    if fault == "fake_owner":
        from types import MethodType

        actor = SimpleNamespace(recovery_contract="league-profit-recovery-v1")
        actor.run = MethodType(play, actor)

    def run():
        return run_prepared_trainer_funding(
            env,
            env,
            target=target,
            validate_target=lambda: None,
            move_slot_policy=lambda _: pytest.fail("teacher fallback"),
            timing=BattleRuntimeTiming(),
            intent=BattleIntent(scope.contract.objective_id, "cartridge-trainer-story"),
            battle_runner_override=actor.run,
        )

    if fault:
        with pytest.raises(TrainerFundingBattleError):
            run()
    else:
        assert run().payout == 480 and env.state.party_hp == (30, 0)


@pytest.mark.parametrize(
    "fault",
    ["intent", "objective", "quote", "target", "source", "model", "items", "income", "resume"],
)
def test_copy_faint_contract_rejects_scope_expansion_before_input(setup, fault):
    from test_red_trainer_funding_battle import ScriptedEnvironment, make_candidate, make_state

    from pokemon_red_completion.red_trainer_funding_battle import run_prepared_trainer_funding

    scope, battler, _ = setup
    actor = copy.StoryCopyController(battler)
    env = ScriptedEnvironment(make_state(map_id=61))
    target = make_candidate(tc=230, ts=4, flag=8, pay=1 if fault == "quote" else 480)
    target = replace(
        target, trainer=replace(target.trainer, map_id=62 if fault == "target" else 61)
    )
    if fault == "source":
        scope.source.write_bytes(b"changed source")
    if fault == "model":
        battler.model = None
    with pytest.raises(ValueError):
        run_prepared_trainer_funding(
            env,
            env,
            target=target,
            validate_target=lambda: None,
            move_slot_policy=lambda _: pytest.fail("teacher fallback"),
            timing=BattleRuntimeTiming(),
            battle_runner_override=actor.run,
            intent=BattleIntent(
                "other" if fault == "objective" else scope.contract.objective_id,
                "ordinary-trainer-funding" if fault == "intent" else "cartridge-trainer-story",
            ),
            maximum_full_restores=1 if fault == "items" else 0,
            story_income_recovery=fault == "income",
            resume_active_battle=fault == "resume",
        )
    assert not env.actions
