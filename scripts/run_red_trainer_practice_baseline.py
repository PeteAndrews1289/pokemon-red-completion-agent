"""Run frozen and simple fixed trainer controls on TRAIN or DEVELOPMENT.

This baseline deliberately declines optional switches and takes the first living
forced replacement. It tests the model seam but does not claim learned switching.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController, FrameSafeExecutor
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_episode import (
    run_red_trainer_practice_episode,
)
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-baseline-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _bound_file(value: object, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{label} identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} hash differs")
    return payload


def _opening_idle_frames(plan: dict[str, object]) -> int:
    value = plan.get("opening_idle_frames", 0)
    if type(value) is not int or not 0 <= value <= 12:
        raise ValueError("trainer baseline timing differs")
    return value


def _matched_player_turn_horizon(plan: dict[str, object]) -> int:
    value = plan.get("matched_player_turn_horizon", 2)
    if type(value) is not int or value not in {2, 4}:  # noqa: E721
        raise ValueError("trainer matched horizon differs")
    return value


def _timed_choice_plan_supported(plan: dict[str, object], observation_schema: str | None) -> bool:
    offsets = plan.get("matched_timing_offsets")
    return offsets is None or (
        offsets == [0, 2, 4, 6, 8]
        and observation_schema == OBSERVATION_SCHEMA_V2
        and (
            plan.get("matched_choices") is not None
            or plan.get("matched_prompt_choices") is True
            or plan.get("matched_forced_choices") is True
        )
    )


def _authenticate(plan: object):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("trainer baseline plan differs")
    _opening_idle_frames(plan)
    horizon = _matched_player_turn_horizon(plan)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer baseline code before running it")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("trainer baseline source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("trainer baseline Red ROM differs")
    baseline_policy = plan.get("baseline_policy", "frozen-attack")
    if baseline_policy not in {"frozen-attack", "first-legal-attack"}:
        raise ValueError("trainer baseline policy differs")
    model = (
        MaskedMLPMoveRanker.from_dict(json.loads(_bound_file(plan.get("model"), "model")))
        if baseline_policy == "frozen-attack" else None
    )
    state = plan.get("capture_state")
    manifest = plan.get("capture_manifest")
    _bound_file(state, "trainer state")
    _bound_file(manifest, "trainer manifest")
    assert isinstance(state, dict) and isinstance(manifest, dict)
    capture = open_battle_scenario_capture(Path(state["path"]), Path(manifest["path"]))
    if (
        capture.manifest.partition not in {
            ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT
        }
        or capture.manifest.expected_battle_state != 2
        or plan.get("max_decisions") != 80
        or plan.get("maximum_frames") != 120000
        or plan.get("matched_choices")
        not in {
            None, "opening_attack_vs_five_switches", "all_legal_opening",
            "opening_move_one_vs_switch_two",
        }
        or plan.get("matched_prompt_choices") not in {None, True}
        or plan.get("matched_forced_choices") not in {None, True}
        or not _timed_choice_plan_supported(plan, capture.manifest.observation_schema)
        or (horizon == 4 and plan.get("matched_choices") not in {
            "all_legal_opening", "opening_move_one_vs_switch_two"
        })
    ):
        raise ValueError("trainer baseline scope differs")
    if (
        capture.manifest.partition is ScenarioPartition.DEVELOPMENT
        and any(plan.get(name) is not None for name in (
            "matched_choices", "matched_prompt_choices", "matched_forced_choices",
            "matched_timing_offsets",
        ))
    ):
        raise ValueError("DEVELOPMENT baseline cannot collect branch targets")
    if baseline_policy == "first-legal-attack" and any(
        plan.get(name) is not None for name in (
            "matched_choices", "matched_prompt_choices", "matched_forced_choices",
            "matched_timing_offsets",
        )
    ):
        raise ValueError("fixed baseline cannot collect branch targets")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists():
        raise ValueError("trainer baseline output must be new")
    return plan, capture, model


def _all_legal_opening_choices(
    prepared: PreparedRedBattleScenario,
    party_hp: tuple[int, ...],
    active_party_index: int,
) -> tuple[TrainerPracticeFirstChoice, ...]:
    if not 0 <= active_party_index < len(party_hp):
        raise ValueError("trainer opening active party slot differs")
    move_choices = tuple(
        TrainerPracticeFirstChoice(BattleAction.move(slot + 1))
        for slot, legal in zip(
            prepared.features.slot_indices,
            prepared.supported_candidate_mask,
            strict=True,
        )
        if legal
    )
    switch_choices = tuple(
        TrainerPracticeFirstChoice(BattleAction.switch(index + 1))
        for index, hp in enumerate(party_hp)
        if hp > 0 and index != active_party_index
    )
    return move_choices + switch_choices


def _first_living_switch_from_observation(observation: dict[str, object]) -> int:
    features = observation.get("features")
    party = features.get("party") if isinstance(features, dict) else None
    members = party.get("members") if isinstance(party, dict) else None
    active = party.get("active_index") if isinstance(party, dict) else None
    if not isinstance(members, list) or type(active) is not int:  # noqa: E721
        raise ValueError("trainer baseline has no observable switch target")
    for member in members:
        if not isinstance(member, dict):
            continue
        index, hp = member.get("party_index"), member.get("hp")
        if type(index) is int and type(hp) is int and index != active and hp > 0:  # noqa: E721
            return index + 1
    raise ValueError("trainer baseline has no living switch target")


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan, capture, model = _authenticate(json.loads(plan_path.read_bytes()))

    class AttackBaseline:
        policy_id = (
            "frozen-attack-model-decline-optional-first-legal-forced"
            if model is not None else "fixed-first-legal-attack-decline-optional-first-legal-forced"
        )

        def __init__(self):
            self.last_decision_diagnostics: dict[str, object] = {}

        def choose_main(self, observation, prepared):
            if not any(prepared.supported_candidate_mask):
                slot = _first_living_switch_from_observation(observation)
                self.last_decision_diagnostics = {
                    "control_rule": "forced_switch_no_attack_pp",
                    "switch_target_rule": "first_living_reserve",
                }
                return BattleAction.switch(slot)
            if model is None:
                index = next(
                    index for index, legal in enumerate(prepared.supported_candidate_mask)
                    if legal
                )
                self.last_decision_diagnostics = {"control_rule": "first_legal_attack"}
            else:
                probabilities = model.predict_proba(
                    prepared.features.candidate_vectors,
                    legal_mask=prepared.features.legal_mask,
                    current_pp=prepared.features.current_pp,
                )
                index = int(probabilities.argmax())
                self.last_decision_diagnostics = {
                    "move_probabilities": probabilities.tolist(),
                    "move_candidate_slots": [slot + 1 for slot in prepared.features.slot_indices],
                    "control_rule": "always_attack",
                }
            return BattleAction.move(prepared.features.slot_indices[index] + 1)

        def choose_switch(self, _observation, legal_party_slots, *, forced, may_decline):
            if forced:
                self.last_decision_diagnostics = {"control_rule": "first_legal_forced"}
                return legal_party_slots[0]
            assert may_decline
            self.last_decision_diagnostics = {"control_rule": "decline_optional"}
            return None

    if check_only:
        return {
            "status": "action_free_trainer_baseline_preflight_passed",
            "capture_id": capture.manifest.capture_id,
            "controller_actions": 0,
            "emulator_frames": 0,
            "persistent_artifacts": 0,
        }

    rom_record = plan["rom"]
    assert isinstance(rom_record, dict) and isinstance(rom_record["path"], str)
    public_stats = (
        RedPracticeCartridge(_bound_file(rom_record, "ROM")).public_base_stats
        if capture.manifest.observation_schema == OBSERVATION_SCHEMA_V2
        else None
    )

    @contextmanager
    def session_factory():
        with PyBoyAdapter(Path(rom_record["path"]), watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=120000)

    def all_legal_opening_choices():
        with session_factory() as session:
            session.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(session)
            raw = reader.read()
            prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(
                    reader,
                    include_battle_stats=(
                        capture.manifest.observation_schema == OBSERVATION_SCHEMA_V2
                    ),
                    public_species_base_stats=public_stats,
                ),
                raw,
                allow_no_attack=True,
            )
            if raw.party_hp is None or raw.active_party_index is None:
                raise ValueError("trainer opening party is unavailable")
            return _all_legal_opening_choices(prepared, raw.party_hp, raw.active_party_index)

    output = Path(plan["output"])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(
        output / "execution-started.json",
        {
            "capture_manifest_sha256": capture.manifest_sha256,
            "policy_id": AttackBaseline.policy_id,
            "source_commit": plan["source_commit"],
            "opening_idle_frames": _opening_idle_frames(plan),
        },
    )
    model_binding = plan.get("model")
    if model is not None and not isinstance(model_binding, dict):
        raise ValueError("frozen baseline model binding differs")
    policy_identity = (
        {"model_sha256": model_binding["sha256"]}
        if isinstance(model_binding, dict)
        else {"fixed_policy_id": AttackBaseline.policy_id}
    )
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity={
            "source_commit": plan["source_commit"],
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "partition": capture.manifest.partition.value,
            "capture_manifest_sha256": capture.manifest_sha256,
            **policy_identity,
            "policy_id": AttackBaseline.policy_id,
            "maximum_frames": plan["maximum_frames"],
            "max_decisions": plan["max_decisions"],
            "opening_idle_frames": _opening_idle_frames(plan),
        },
    )
    try:
        matched_choices = plan.get("matched_choices")
        matched_horizon = _matched_player_turn_horizon(plan)
        first_choices = (
            all_legal_opening_choices()
            if matched_choices in {"all_legal_opening", "opening_move_one_vs_switch_two"}
            else (
                TrainerPracticeFirstChoice(BattleAction.move(1)),
                *(TrainerPracticeFirstChoice(BattleAction.switch(slot)) for slot in range(2, 7)),
            )
        )
        if matched_choices == "opening_move_one_vs_switch_two":
            first_choices = tuple(
                choice for ref in (
                    "pokemon.core:battle:move:1", "pokemon.core:battle:switch:2"
                ) for choice in first_choices if choice.semantic_ref == ref
            )
            if len(first_choices) != 2:
                raise ValueError("two-choice opening inventory differs")
        timed = plan.get("matched_timing_offsets") is not None
        offsets = tuple(plan["matched_timing_offsets"]) if timed else (0,)
        branch_directories = (
            tuple(output / f"timing-{offset:02d}" for offset in offsets)
            if timed else (output,)
        )
        if matched_choices in {
            "opening_attack_vs_five_switches", "all_legal_opening",
            "opening_move_one_vs_switch_two",
        }:
            for offset, branch_directory in zip(offsets, branch_directories, strict=True):
                if timed:
                    branch_directory.mkdir(mode=0o700, exist_ok=False)
                _record(branch_directory / "matched-plan.json", {
                    "schema": "pokemon.red.trainer-practice-choice-plan.v1",
                    "capture_manifest_sha256": capture.manifest_sha256,
                    "source_commit": plan["source_commit"],
                    "model_sha256": model_binding["sha256"],
                    "continuation_policy_id": AttackBaseline.policy_id,
                    "first_choice_refs": [choice.semantic_ref for choice in first_choices],
                    "player_turn_horizon": matched_horizon,
                    "max_decisions": 12 if matched_horizon == 4 else 8,
                    "opening_idle_frames": offset,
                })
        result = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=AttackBaseline(),
            max_decisions=80,
            opening_idle_frames=_opening_idle_frames(plan),
            event_sink=log.emit,
            public_species_base_stats=public_stats,
        )

        matched = None
        if matched_choices in {
            "opening_attack_vs_five_switches", "all_legal_opening",
            "opening_move_one_vs_switch_two",
        }:
            for offset, branch_directory in zip(offsets, branch_directories, strict=True):
                plan_sha = hashlib.sha256(
                    (branch_directory / "matched-plan.json").read_bytes()
                ).hexdigest()

                def retain_branch(  # type: ignore[no-untyped-def]
                    index, choice, episode, directory=branch_directory
                ):
                    _record(
                        directory / f"matched-branch-{index:02d}.json",
                        {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()},
                    )
                    _record(
                        directory / f"matched-branch-{index:02d}-event-log-verification.json",
                        verify_trainer_practice_event_log(
                            directory / f"matched-branch-{index:02d}-events"
                        ),
                    )

                def branch_event_log(  # type: ignore[no-untyped-def]
                    index, choice, directory=branch_directory, timing_offset=offset,
                    declared_plan_sha=plan_sha,
                ):
                    return TrainerPracticeEventLog(
                        directory / f"matched-branch-{index:02d}-events",
                        run_identity={
                            "source_commit": plan["source_commit"],
                            "capture_id": capture.manifest.capture_id,
                            "root_lineage_id": capture.manifest.root_lineage_id,
                            "partition": "train",
                            "capture_manifest_sha256": capture.manifest_sha256,
                            "model_sha256": model_binding["sha256"],
                            "policy_id": AttackBaseline.policy_id,
                            "first_choice_ref": choice.semantic_ref,
                            "player_turn_horizon": matched_horizon,
                            "max_decisions": 12 if matched_horizon == 4 else 8,
                            "opening_idle_frames": timing_offset,
                            "plan_sha256": declared_plan_sha,
                        },
                    )

                matched = collect_trainer_practice_counterfactuals(
                    capture,
                    session_factory=session_factory,
                    continuation_policy_factory=AttackBaseline,
                    first_choices=first_choices,
                    max_decisions=12 if matched_horizon == 4 else 8,
                    player_turn_horizon=matched_horizon,
                    branch_sink=retain_branch,
                    branch_event_log_factory=branch_event_log,
                    public_species_base_stats=public_stats,
                    opening_idle_frames=offset,
                )
                _record(branch_directory / "matched-choices.json", matched.public_dict())
        matched_prompt = None
        if plan.get("matched_prompt_choices") is True:
            with PyBoyAdapter(Path(rom_record["path"]), watch=False, speed=None) as emulator:
                emulator.load_state_bytes(capture.state_bytes)
                reader = PokemonRedStateReader(emulator)
                actions = FrameSafeExecutor(FrameBudgetController(emulator, maximum_frames=10000))
                execute_bounded_battle_move_turn(
                    reader,
                    actions,
                    expected_map=capture.manifest.expected_map,
                    selected_slot=1,
                    expected_battle_state=2,
                    settle_to_next_decision=True,
                    timing=replace(
                        DEFAULT_BATTLE_RUNTIME_TIMING,
                        max_post_attack_transition_pulses=40,
                    ),
                    label="trainer practice prompt capture",
                )
                raw = reader.read()
                if not reader.trainer_switch_prompt_visible(raw):
                    raise ValueError("trainer practice opening attack missed replacement prompt")
                observation = (
                    PokemonRedObservationEncoder.from_state_reader(
                        reader,
                        include_battle_stats=(
                            capture.manifest.observation_schema == OBSERVATION_SCHEMA_V2
                        ),
                        public_species_base_stats=public_stats,
                    )
                    .snapshot_from_raw(raw)
                    .to_dict()
                )
                prompt_state = emulator.save_state_bytes()
            prompt_manifest = build_battle_scenario_capture_payload(
                capture_id=f"{capture.manifest.capture_id}-replacement-prompt",
                root_lineage_id=capture.manifest.root_lineage_id,
                partition=ScenarioPartition.TRAIN,
                state_bytes=prompt_state,
                initial_observation_sha256=canonical_sha256(observation),
                source_commit=plan["source_commit"],
                expected_map=capture.manifest.expected_map,
                expected_battle_state=2,
                source_state_sha256=capture.manifest.state_sha256,
                observation_schema=capture.manifest.observation_schema,
            )
            _write(output / "prompt.state", prompt_state)
            _write(output / "prompt.state.json", prompt_manifest)
            prompt_capture = open_battle_scenario_capture(
                output / "prompt.state", output / "prompt.state.json"
            )
            if raw.party_hp is None or raw.active_party_index is None:
                raise ValueError("trainer prompt party is unavailable")
            prompt_choices = (
                TrainerPracticeFirstChoice(None),
                *(
                    TrainerPracticeFirstChoice(BattleAction.switch(index + 1))
                    for index, hp in enumerate(raw.party_hp)
                    if hp > 0 and index != raw.active_party_index
                ),
            )
            if len(prompt_choices) < 3:
                raise ValueError("trainer prompt needs two living switch alternatives")
            for offset in offsets:
                prompt_directory = output / f"prompt-timing-{offset:02d}" if timed else output
                if timed:
                    prompt_directory.mkdir(mode=0o700, exist_ok=False)
                prompt_plan_path = prompt_directory / "matched-prompt-plan.json"
                _record(prompt_plan_path, {
                    "schema": "pokemon.red.trainer-practice-choice-plan.v1",
                    "capture_manifest_sha256": prompt_capture.manifest_sha256,
                    "source_commit": plan["source_commit"],
                    "model_sha256": model_binding["sha256"],
                    "continuation_policy_id": AttackBaseline.policy_id,
                    "first_choice_refs": [choice.semantic_ref for choice in prompt_choices],
                    "player_turn_horizon": 1,
                    "max_decisions": 5,
                    "opening_idle_frames": offset,
                })
                prompt_plan_sha256 = hashlib.sha256(prompt_plan_path.read_bytes()).hexdigest()

                def retain_prompt_branch(  # type: ignore[no-untyped-def]
                    index, choice, episode, directory=prompt_directory
                ):
                    _record(
                        directory / f"prompt-branch-{index:02d}.json",
                        {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()},
                    )
                    _record(
                        directory / f"prompt-branch-{index:02d}-event-log-verification.json",
                        verify_trainer_practice_event_log(
                            directory / f"prompt-branch-{index:02d}-events"
                        ),
                    )

                def prompt_branch_event_log(  # type: ignore[no-untyped-def]
                    index, choice, directory=prompt_directory,
                    timing_offset=offset, declared_plan_sha=prompt_plan_sha256,
                ):
                    return TrainerPracticeEventLog(
                        directory / f"prompt-branch-{index:02d}-events",
                        run_identity={
                            "source_commit": plan["source_commit"],
                            "capture_id": prompt_capture.manifest.capture_id,
                            "root_lineage_id": prompt_capture.manifest.root_lineage_id,
                            "partition": "train",
                            "capture_manifest_sha256": prompt_capture.manifest_sha256,
                            "model_sha256": model_binding["sha256"],
                            "policy_id": AttackBaseline.policy_id,
                            "first_choice_ref": choice.semantic_ref,
                            "player_turn_horizon": 1,
                            "max_decisions": 5,
                            "opening_idle_frames": timing_offset,
                            "plan_sha256": declared_plan_sha,
                        },
                    )

                matched_prompt = collect_trainer_practice_counterfactuals(
                    prompt_capture,
                    session_factory=session_factory,
                    continuation_policy_factory=AttackBaseline,
                    first_choices=prompt_choices,
                    max_decisions=5,
                    player_turn_horizon=1,
                    branch_sink=retain_prompt_branch,
                    branch_event_log_factory=prompt_branch_event_log,
                    public_species_base_stats=public_stats,
                    opening_idle_frames=offset,
                )
                _record(
                    prompt_directory / "matched-prompt-choices.json",
                    matched_prompt.public_dict(),
                )
        if plan.get("matched_forced_choices") is True:
            with PyBoyAdapter(Path(rom_record["path"]), watch=False, speed=None) as emulator:
                emulator.load_state_bytes(capture.state_bytes)
                reader = PokemonRedStateReader(emulator)
                actions = FrameSafeExecutor(FrameBudgetController(emulator, maximum_frames=10000))
                execute_bounded_battle_move_turn(
                    reader,
                    actions,
                    expected_map=capture.manifest.expected_map,
                    selected_slot=1,
                    expected_battle_state=2,
                    settle_to_next_decision=True,
                    timing=replace(
                        DEFAULT_BATTLE_RUNTIME_TIMING,
                        max_post_attack_transition_pulses=40,
                    ),
                    label="trainer practice forced capture",
                )
                raw = reader.read()
                if (
                    raw.battle_state != 2
                    or raw.battler_hp != 0
                    or reader.trainer_switch_prompt_visible(raw)
                    or raw.party_hp is None
                    or raw.active_party_index is None
                ):
                    raise ValueError("trainer practice opening attack missed forced replacement")
                forced_options = tuple(
                    index + 1
                    for index, hp in enumerate(raw.party_hp)
                    if hp > 0 and index != raw.active_party_index
                )
                if len(forced_options) < 2:
                    raise ValueError("trainer forced context needs two living switch alternatives")
                observation = (
                    PokemonRedObservationEncoder.from_state_reader(
                        reader,
                        include_battle_stats=(
                            capture.manifest.observation_schema == OBSERVATION_SCHEMA_V2
                        ),
                        public_species_base_stats=public_stats,
                    )
                    .snapshot_from_raw(raw)
                    .to_dict()
                )
                forced_state = emulator.save_state_bytes()
            forced_manifest = build_battle_scenario_capture_payload(
                capture_id=f"{capture.manifest.capture_id}-forced-replacement",
                root_lineage_id=capture.manifest.root_lineage_id,
                partition=ScenarioPartition.TRAIN,
                state_bytes=forced_state,
                initial_observation_sha256=canonical_sha256(observation),
                source_commit=plan["source_commit"],
                expected_map=capture.manifest.expected_map,
                expected_battle_state=2,
                source_state_sha256=capture.manifest.state_sha256,
                observation_schema=capture.manifest.observation_schema,
            )
            _write(output / "forced.state", forced_state)
            _write(output / "forced.state.json", forced_manifest)
            forced_capture = open_battle_scenario_capture(
                output / "forced.state", output / "forced.state.json"
            )
            forced_choices = tuple(
                TrainerPracticeFirstChoice(BattleAction.switch(slot))
                for slot in forced_options
            )
            for offset in offsets:
                forced_directory = output / f"forced-timing-{offset:02d}" if timed else output
                if timed:
                    forced_directory.mkdir(mode=0o700, exist_ok=False)
                forced_plan_path = forced_directory / "matched-forced-plan.json"
                _record(forced_plan_path, {
                    "schema": "pokemon.red.trainer-practice-choice-plan.v1",
                    "capture_manifest_sha256": forced_capture.manifest_sha256,
                    "source_commit": plan["source_commit"],
                    "model_sha256": model_binding["sha256"],
                    "continuation_policy_id": AttackBaseline.policy_id,
                    "first_choice_refs": [choice.semantic_ref for choice in forced_choices],
                    "player_turn_horizon": 1,
                    "max_decisions": 5,
                    "opening_idle_frames": offset,
                })
                forced_plan_sha256 = hashlib.sha256(forced_plan_path.read_bytes()).hexdigest()

                def retain_forced_branch(  # type: ignore[no-untyped-def]
                    index, choice, episode, directory=forced_directory
                ):
                    _record(
                        directory / f"forced-branch-{index:02d}.json",
                        {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()},
                    )
                    _record(
                        directory / f"forced-branch-{index:02d}-event-log-verification.json",
                        verify_trainer_practice_event_log(
                            directory / f"forced-branch-{index:02d}-events"
                        ),
                    )

                def forced_branch_event_log(  # type: ignore[no-untyped-def]
                    index, choice, directory=forced_directory,
                    timing_offset=offset, declared_plan_sha=forced_plan_sha256,
                ):
                    return TrainerPracticeEventLog(
                        directory / f"forced-branch-{index:02d}-events",
                        run_identity={
                            "source_commit": plan["source_commit"],
                            "capture_id": forced_capture.manifest.capture_id,
                            "root_lineage_id": forced_capture.manifest.root_lineage_id,
                            "partition": "train",
                            "capture_manifest_sha256": forced_capture.manifest_sha256,
                            "model_sha256": model_binding["sha256"],
                            "policy_id": AttackBaseline.policy_id,
                            "first_choice_ref": choice.semantic_ref,
                            "player_turn_horizon": 1,
                            "max_decisions": 5,
                            "opening_idle_frames": timing_offset,
                            "plan_sha256": declared_plan_sha,
                        },
                    )

                matched_forced = collect_trainer_practice_counterfactuals(
                    forced_capture,
                    session_factory=session_factory,
                    continuation_policy_factory=AttackBaseline,
                    first_choices=forced_choices,
                    max_decisions=5,
                    player_turn_horizon=1,
                    branch_sink=retain_forced_branch,
                    branch_event_log_factory=forced_branch_event_log,
                    public_species_base_stats=public_stats,
                    opening_idle_frames=offset,
                )
                _record(
                    forced_directory / "matched-forced-choices.json",
                    matched_forced.public_dict(),
                )
    except Exception as error:
        log.fail(error)
        _record(
            output / "event-log-verification.json",
            verify_trainer_practice_event_log(log.directory),
        )
        _record(output / "failure.json", {"type": type(error).__name__, "message": str(error)})
        raise
    report = result.public_dict()
    report.update(
        {
            "baseline_only": True,
            "baseline_policy": plan.get("baseline_policy", "frozen-attack"),
            "partition": capture.manifest.partition.value,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "learned_switch_authority": False,
            "source_commit": plan["source_commit"],
            "model_updates": 0,
            "full_game_replays": 0,
        }
    )
    _record(output / "outcome.json", report)
    log.finish(
        {
            "battle_won": result.battle_won,
            "stop_reason": result.stop_reason,
            "decision_count": len(result.decisions),
            "elapsed_ns": result.elapsed_ns,
            "outcome_sha256": canonical_sha256(report),
        }
    )
    _record(
        output / "event-log-verification.json",
        verify_trainer_practice_event_log(log.directory),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
