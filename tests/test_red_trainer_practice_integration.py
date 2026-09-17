"""Private-cartridge mechanic check; never a train or development sample."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from os import environ
from pathlib import Path

import pytest

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_features import CONTROL_CLASS_REFS
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_recovery import resolve_trainer_switch_prompt
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController, FrameSafeExecutor
from pokemon_red_completion.observation import BattleMenuPhase, PokemonRedStateReader
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_outcome_runtime import (
    collect_red_battle_outcome_example,
    execute_red_battle_candidate,
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_practice_factory import materialize_red_train_practice
from pokemon_red_completion.red_battle_scenario import project_red_battle_turn_outcome
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_policy import RedTrainerPracticeModelPolicy
from pokemon_red_completion.scenario_lab import ScenarioPartition

pytestmark = pytest.mark.integration


def _move(identifier: int, pp: int) -> dict[str, object]:
    return {"move_ref": pokemon_red_move_ref(identifier), "pp": pp}


def test_authenticated_train_team_accepts_frozen_attack_model_without_teacher() -> None:
    """A real TRAIN capture, unlike the old diagnostic state, exercises the model seam."""

    rom_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_ROM")
    state_path = environ.get("POKEMON_RED_TRAINER_TRAIN_STATE")
    manifest_path = environ.get("POKEMON_RED_TRAINER_TRAIN_MANIFEST")
    model_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_MODEL")
    if not all((rom_path, state_path, manifest_path, model_path)):
        pytest.skip("private authenticated train inputs not supplied")
    assert state_path is not None and manifest_path is not None
    assert rom_path is not None and model_path is not None
    capture = open_battle_scenario_capture(Path(state_path), Path(manifest_path))
    assert capture.manifest.partition is ScenarioPartition.TRAIN
    assert capture.manifest.expected_battle_state == 2
    model = MaskedMLPMoveRanker.from_dict(json.loads(Path(model_path).read_bytes()))

    class FrozenAttackBaseline:
        policy_id = "frozen-attack-model-with-decline-and-first-legal-switch-baseline"

        def choose_main(self, _observation, prepared):
            index = model.predict(
                prepared.features.candidate_vectors,
                legal_mask=prepared.features.legal_mask,
                current_pp=prepared.features.current_pp,
            )
            return BattleAction.move(prepared.features.slot_indices[index] + 1)

        def choose_switch(self, _observation, legal_party_slots, *, forced, may_decline):
            if forced:
                return legal_party_slots[0]
            assert may_decline
            return None

    @contextmanager
    def session_factory():
        with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=120000)

    episode = run_red_trainer_practice_episode(
        capture,
        session_factory=session_factory,
        policy=FrozenAttackBaseline(),
        max_decisions=80,
    )
    assert not episode.battle_won
    assert episode.stop_reason == "party_defeated"
    assert sum(step["kind"] == "attack" for step in episode.decisions) >= 6
    assert any(step["kind"] == "switch_prompt" for step in episode.decisions)
    assert episode.public_dict()["teacher_queries"] == 0

    class SwitchThenAttack:
        calls = 0

        def predict_ref(self, _features):
            self.calls += 1
            return CONTROL_CLASS_REFS[5] if self.calls == 1 else CONTROL_CLASS_REFS[0]

    class HighestSlot:
        def probabilities(self, candidates):
            return [float(item.party_slot) for item in candidates.candidates]

    composed = RedTrainerPracticeModelPolicy(
        policy_id="trainer-composed-model-seam-diagnostic",
        battle_plan_id="trainer-train-lab",
        move_model=model,
        control_model=SwitchThenAttack(),
        switch_model=HighestSlot(),
    )
    switched = run_red_trainer_practice_episode(
        capture,
        session_factory=session_factory,
        policy=composed,
        max_decisions=2,
    )
    assert switched.stop_reason == "decision_budget"
    assert [step["kind"] for step in switched.decisions] == ["voluntary_switch", "attack"]
    assert switched.decisions[0]["party_slot"] == 6

    matched = collect_trainer_practice_counterfactuals(
        capture,
        session_factory=session_factory,
        continuation_policy_factory=FrozenAttackBaseline,
        first_choices=(
            TrainerPracticeFirstChoice(BattleAction.move(1)),
            *(TrainerPracticeFirstChoice(BattleAction.switch(slot)) for slot in range(2, 7)),
        ),
        max_decisions=3,
    )
    assert len(matched.branches) == 6
    assert matched.root_lineage_id == capture.manifest.root_lineage_id
    assert matched.public_dict()["new_independent_upstream_roots"] == 0
    assert all(episode.final_observation is not None for _choice, episode in matched.branches)
    assert [episode.decisions[0]["kind"] for _choice, episode in matched.branches] == [
        "attack", "voluntary_switch", "voluntary_switch", "voluntary_switch",
        "voluntary_switch", "voluntary_switch",
    ]


@pytest.mark.parametrize("team_count", [2, 6])
@pytest.mark.parametrize("target_index", [None, 1])
def test_two_member_trainer_knockout_reaches_next_model_decision(
    target_index: int | None,
    team_count: int,
    tmp_path: Path,
) -> None:
    rom_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_ROM")
    state_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_STATE")
    if not rom_path or not state_path:
        pytest.skip("private trainer mechanic inputs not supplied")
    rom = Path(rom_path).read_bytes()
    state = Path(state_path).read_bytes()
    with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state)
        reader = PokemonRedStateReader(emulator)
        for _ in range(5):
            emulator.press("a")
            emulator.tick(8)
            emulator.release("a")
            emulator.tick(136)
        before = reader.read()
        assert before.battle_state == 2
        assert before.party_count == 3
        assert reader.read_battle_menu_state(before).phase is BattleMenuPhase.MAIN
        assert before.map_id is not None
        spec = BattlePracticeSpec.from_dict(
            {
                "source_state_sha256": sha256(state).hexdigest(),
                "root_lineage_id": "trainer-mechanics-diagnostic",
                "partition": "train",
                "battle_kind": "trainer",
                "actor_species_ref": pokemon_red_species_ref(84),
                "actor_level": 35,
                "actor_moves": [_move(85, 15), _move(98, 30), _move(84, 30), _move(129, 20)],
                "party_reserves": [
                    {
                        "party_slot": 4,
                        "species_ref": pokemon_red_species_ref(28),
                        "level": 45,
                        "moves": [_move(57, 15), _move(34, 15)],
                    },
                    {
                        "party_slot": 5,
                        "species_ref": pokemon_red_species_ref(176),
                        "level": 30,
                        "moves": [_move(52, 25), _move(10, 35)],
                    },
                    {
                        "party_slot": 6,
                        "species_ref": pokemon_red_species_ref(84),
                        "level": 30,
                        "moves": [_move(85, 15), _move(98, 30)],
                    },
                ],
                "opponent_species_ref": pokemon_red_species_ref(177),
                "opponent_level": 30,
                "opponent_hp": 20,
                "opponent_moves": [_move(55, 25), _move(33, 35)],
                "opponent_party_count": team_count,
                "opponent_reserves": [
                    {
                        "party_slot": 2,
                        "species_ref": pokemon_red_species_ref(176),
                        "level": 30,
                        "moves": [_move(10, 35), _move(52, 25)],
                    },
                    {
                        "party_slot": 3,
                        "species_ref": pokemon_red_species_ref(177),
                        "level": 30,
                        "moves": [_move(55, 25), _move(33, 35)],
                    },
                    {
                        "party_slot": 4,
                        "species_ref": pokemon_red_species_ref(84),
                        "level": 30,
                        "moves": [_move(85, 15), _move(98, 30)],
                    },
                    {
                        "party_slot": 5,
                        "species_ref": pokemon_red_species_ref(28),
                        "level": 30,
                        "moves": [_move(57, 15), _move(34, 15)],
                    },
                    {
                        "party_slot": 6,
                        "species_ref": pokemon_red_species_ref(1),
                        "level": 30,
                        "moves": [_move(30, 25), _move(23, 20)],
                    },
                ][: team_count - 1],
            }
        )
        receipt = materialize_red_train_practice(
            reader,
            emulator._require_backend().memory,
            spec,
            cartridge=RedPracticeCartridge(rom),
        )
        if target_index is None:
            generated = emulator.save_state_bytes()
            capture_state_path = tmp_path / "trainer.state"
            capture_manifest_path = tmp_path / "trainer.state.json"
            capture_state_path.write_bytes(generated)
            capture_manifest_path.write_bytes(
                build_battle_scenario_capture_payload(
                    capture_id="trainer-mechanics-diagnostic",
                    root_lineage_id=spec.root_lineage_id,
                    partition=ScenarioPartition.TRAIN,
                    state_bytes=generated,
                    initial_observation_sha256=receipt.observation_sha256,
                    source_commit="0" * 40,
                    expected_map=before.map_id,
                    expected_battle_state=2,
                    source_state_sha256=spec.source_state_sha256,
                )
            )
            capture = open_battle_scenario_capture(capture_state_path, capture_manifest_path)

            @contextmanager
            def session_factory():
                with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as session:
                    yield FrameBudgetController(session, maximum_frames=10000)

            collection = collect_red_battle_outcome_example(
                capture,
                session_factory=session_factory,
            )
            assert collection.example.partition is ScenarioPartition.TRAIN
            assert len(collection.outcomes) == 4
            assert all(outcome is not None for outcome in collection.outcomes)
            assert len({outcome.pre_attack_frames for outcome in collection.outcomes}) == 1
            model_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_MODEL")
            if model_path:
                model = MaskedMLPMoveRanker.from_dict(json.loads(Path(model_path).read_bytes()))
                prepared = prepare_red_battle_outcome_capture(
                    capture, session_factory=session_factory
                )
                choice = model.predict(
                    prepared.features.candidate_vectors,
                    legal_mask=prepared.features.legal_mask,
                    current_pp=prepared.features.current_pp,
                )
                selected = execute_red_battle_candidate(
                    capture, choice, session_factory=session_factory
                )
                assert selected.selected_candidate_index == choice
                assert selected.outcome.move_executed

                class FrozenAttackPolicy:
                    policy_id = "diagnostic-frozen-expected-utility-v2"

                    def choose_main(self, _observation, prepared):
                        index = model.predict(
                            prepared.features.candidate_vectors,
                            legal_mask=prepared.features.legal_mask,
                            current_pp=prepared.features.current_pp,
                        )
                        return BattleAction.move(prepared.features.slot_indices[index] + 1)

                    def choose_switch(
                        self, _observation, _legal_party_slots, *, forced, may_decline
                    ):
                        assert not forced and may_decline
                        return None

                class VoluntarySwitchPolicy(FrozenAttackPolicy):
                    policy_id = "diagnostic-voluntary-switch-then-frozen-attacks"
                    switched = False

                    def choose_main(self, observation, prepared):
                        if not self.switched:
                            self.switched = True
                            return BattleAction.switch(4)
                        return super().choose_main(observation, prepared)

                    def choose_switch(self, observation, legal_party_slots, *, forced, may_decline):
                        if forced:
                            return legal_party_slots[0]
                        return super().choose_switch(
                            observation,
                            legal_party_slots,
                            forced=forced,
                            may_decline=may_decline,
                        )

                if team_count == 2:
                    episode = run_red_trainer_practice_episode(
                        capture,
                        session_factory=session_factory,
                        policy=FrozenAttackPolicy(),
                        max_decisions=12,
                    )
                    assert episode.battle_won
                    assert sum(step["kind"] == "attack" for step in episode.decisions) >= 2
                    assert any(step["kind"] == "switch_prompt" for step in episode.decisions)

                    voluntary = run_red_trainer_practice_episode(
                        capture,
                        session_factory=session_factory,
                        policy=VoluntarySwitchPolicy(),
                        max_decisions=12,
                    )
                    assert voluntary.decisions[0]["kind"] == "voluntary_switch"
                    assert voluntary.decisions[0]["party_slot"] == 4
                    assert voluntary.battle_won
                else:

                    @contextmanager
                    def long_session_factory():
                        with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as session:
                            yield FrameBudgetController(session, maximum_frames=60000)

                    full_team = run_red_trainer_practice_episode(
                        capture,
                        session_factory=long_session_factory,
                        policy=VoluntarySwitchPolicy(),
                        max_decisions=24,
                    )
                    assert full_team.battle_won
                    assert sum(step["kind"] == "attack" for step in full_team.decisions) >= 6
                    assert full_team.decisions[0]["kind"] == "voluntary_switch"
        controller = FrameSafeExecutor(FrameBudgetController(emulator, maximum_frames=16000))
        execution = execute_bounded_battle_move_turn(
            reader,
            controller,
            expected_map=before.map_id,
            selected_slot=1,
            expected_battle_state=2,
            settle_to_next_decision=True,
            timing=replace(DEFAULT_BATTLE_RUNTIME_TIMING, max_post_attack_transition_pulses=40),
        )
        after = execution.final_state
        assert execution.move_executed
        assert after.party_count == 6
        assert after.enemy_party_count == team_count
        assert after.battle_state == 2
        assert after.enemy_party_position == 1
        assert after.enemy_party_hp is not None and after.enemy_party_hp[0] == 0
        assert after.enemy_species_id == 176
        assert reader.trainer_switch_prompt_visible(after)
        outcome = project_red_battle_turn_outcome(execution)
        assert outcome.opponent_fainted
        assert outcome.opponent_damage_fraction == pytest.approx(20 / 66)
        assert before.party_hp is not None
        assert target_index is None or before.party_hp[target_index] > 0
        resolve_trainer_switch_prompt(
            controller,
            reader,
            emulator,
            target_index=target_index,
            label="diagnostic model choice",
        )
        settled = reader.read()
        assert reader.read_battle_menu_state(settled).phase is BattleMenuPhase.MAIN
    if target_index is not None:
        assert settled.active_party_index == target_index


def test_all_red_species_materialize_in_trainer_roster_without_controller_actions() -> None:
    if environ.get("POKEMON_RED_TRAINER_SWEEP") != "1":
        pytest.skip("full private trainer species sweep not requested")
    rom_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_ROM")
    state_path = environ.get("POKEMON_RED_TRAINER_DIAGNOSTIC_STATE")
    if not rom_path or not state_path:
        pytest.skip("private trainer mechanic inputs not supplied")
    rom = Path(rom_path).read_bytes()
    cartridge = RedPracticeCartridge(rom)
    with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(Path(state_path).read_bytes())
        for _ in range(5):
            emulator.press("a")
            emulator.tick(8)
            emulator.release("a")
            emulator.tick(136)
        source = emulator.save_state_bytes()
        source_hash = sha256(source).hexdigest()
        reader = PokemonRedStateReader(emulator)
        for species_id in PokemonRedBattleCatalog().species_ids:
            emulator.load_state_bytes(source)
            before_frame = emulator.frame_count
            spec = BattlePracticeSpec.from_dict(
                {
                    "source_state_sha256": source_hash,
                    "root_lineage_id": "trainer-species-mechanics-diagnostic",
                    "partition": "train",
                    "battle_kind": "trainer",
                    "actor_moves": [_move(85, 15), _move(98, 30)],
                    "opponent_species_ref": pokemon_red_species_ref(species_id),
                    "opponent_level": 30,
                    "opponent_hp": 20,
                    "opponent_moves": [_move(33, 35)],
                    "opponent_party_count": 1,
                }
            )
            receipt = materialize_red_train_practice(
                reader,
                emulator._require_backend().memory,
                spec,
                cartridge=cartridge,
            )
            assert receipt.opponent_species_id == species_id
            assert reader.read().enemy_party_count == 1
            assert emulator.frame_count == before_frame
