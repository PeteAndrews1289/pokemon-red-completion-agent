#!/usr/bin/env python3
"""Admit a completed autonomous Red run and fit its measured choices once."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.collection_protocol import committed_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ReadOnlyController
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import detect_source_identity, require_clean_source
from pokemon_red_completion.red_autonomous_learning import (
    authenticated_autonomous_execution_limits,
    publish_autonomous_measured_choice,
)
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID, red_species_ref
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
from pokemon_red_completion.red_player_incremental_fit import fit_incremental_registered_results
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
    load_player_goal_model_record_bytes,
)
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.red_resource_economy import red_economy_snapshot
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)

ROOT = Path(__file__).resolve().parents[1]
AutonomousStep = tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    bytes,
    bytes,
    str,
    str,
    str,
]


def _bytes(path: Path, expected: str, subject: str) -> bytes:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"autonomous {subject} authentication failed")
    return payload


def _json(payload: bytes, subject: str) -> dict[str, object]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"autonomous {subject} differs")
    return value


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"autonomous {subject} differs")
    return value


def _require_unassisted_goal_fit(
    plan: Mapping[str, object], provenance: Mapping[str, object]
) -> None:
    if provenance.get("training_assistance") is not None or plan.get(
        "assisted_training_money"
    ) is not None:
        raise ValueError("assisted training cannot enter the ordinary goal-value fit")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()

    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    if source.git_commit is None:
        raise ValueError("autonomous fit source identity is unavailable")
    plan_bytes = args.plan.read_bytes()
    plan = _json(plan_bytes, "external plan")
    payloads: dict[str, bytes] = {}
    for key in ("rom", "state", "checkpoint", "profile", "model"):
        row = _mapping(plan.get(key), f"{key} declaration")
        path = Path(str(row.get("path")))
        payloads[key] = _bytes(path, str(row.get("sha256")), key)

    output = Path(str(plan.get("output")))
    run_plan_path = output / "plan.json"
    run_result_path = output / "result.json"
    run_plan_bytes = run_plan_path.read_bytes()
    run_result_bytes = run_result_path.read_bytes()
    run_plan = _json(run_plan_bytes, "run plan")
    run_result = _json(run_result_bytes, "run result")
    provenance = _mapping(run_plan.get("provenance"), "run provenance")
    _require_unassisted_goal_fit(plan, provenance)
    execution_maximum_actions, execution_maximum_frames = (
        authenticated_autonomous_execution_limits(plan, provenance)
    )
    prior = load_player_goal_model_record(
        Path(str(_mapping(plan["model"], "model declaration").get("path"))),
        expected_model_sha256=str(plan.get("model_sha256")),
    )
    if not isinstance(prior, RedPlayerModelRecord) or prior.objective != REGISTERED_OBJECTIVE:
        raise ValueError("autonomous fit requires its registered behavior model")
    outcomes = run_result.get("outcomes")
    if (
        run_plan.get("schema") != "pokemon.red.autonomous-option-run.v1"
        or run_plan.get("teacher_actions_allowed") is not False
        or run_plan.get("model_sha256") != prior.model.model_sha256
        or provenance.get("plan_sha256") != hashlib.sha256(plan_bytes).hexdigest()
        or provenance.get("parent_state_sha256") != _mapping(plan["state"], "state").get("sha256")
        or provenance.get("rom_sha256") != _mapping(plan["rom"], "rom").get("sha256")
        or provenance.get("model_file_sha256") != prior.file_sha256
        or provenance.get("source_dirty") is not False
        or run_result.get("schema") != "pokemon.red.autonomous-option-result.v1"
        or run_result.get("model_sha256") != prior.model.model_sha256
        or run_result.get("teacher_actions") != 0
        or not isinstance(outcomes, list)
        or run_result.get("executed_decisions") != len(outcomes)
        or run_result.get("successful_decisions") != sum(
            outcome.get("verification") == "succeeded"
            for outcome in outcomes
            if isinstance(outcome, dict)
        )
        or not outcomes
    ):
        raise ValueError("autonomous run scope differs")

    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("autonomous run identity differs")
    step_rows: list[AutonomousStep] = []
    expected_before_sha = str(_mapping(plan["state"], "state").get("sha256"))
    for ordinal, raw_outcome in enumerate(outcomes):
        step = output / f"step-{ordinal:03d}"
        intent_path = step / "intent.json"
        decision_path = step / "decision.json"
        outcome_path = step / "outcome.json"
        before_path = step / "before.json"
        before_state_path = step / "before.state"
        terminal_state_path = step / "terminal.state"
        intent = _json(intent_path.read_bytes(), "intent")
        decision = _json(decision_path.read_bytes(), "decision")
        outcome = _json(outcome_path.read_bytes(), "outcome")
        before = _json(before_path.read_bytes(), "before snapshot")
        if (
            raw_outcome != outcome
            or outcome.get("choice") != decision
            or outcome.get("ordinal") != ordinal
            or outcome.get("before_state_sha256") != expected_before_sha
            or before.get("state_sha256") != expected_before_sha
            or before.get("facts") != outcome.get("before")
            or before.get("safe") is not True
            or _hash(before_state_path) != expected_before_sha
            or intent.get("state_sha256") != expected_before_sha
            or intent.get("model_sha256") != prior.model.model_sha256
            or _hash(terminal_state_path) != outcome.get("terminal_state_sha256")
        ):
            raise ValueError(f"autonomous step {ordinal} chain differs")
        expected_before_sha = str(outcome.get("terminal_state_sha256"))
        step_rows.append(
            (
                intent,
                decision,
                outcome,
                before_state_path.read_bytes(),
                terminal_state_path.read_bytes(),
                _hash(intent_path),
                _hash(decision_path),
                _hash(outcome_path),
            )
        )

    envelope = dict(
        _mapping(
            _json(payloads["checkpoint"], "checkpoint").get("envelope"),
            "checkpoint envelope",
        )
    )
    profile = parse_red_goal_context_profile(payloads["profile"])
    rom_path = Path(str(_mapping(plan["rom"], "rom").get("path")))
    initial_state_sha = str(_mapping(plan["state"], "state").get("sha256"))

    def capture_for(state: bytes, state_sha: str):
        state_envelope = dict(envelope)
        state_envelope.update(
            state_sha256=state_sha,
            checkpoint_id=run_id,
            checkpoint_label="Autonomous measured-choice admission",
        )
        return parse_goal_manager_context_capture(
            state,
            (json.dumps(state_envelope, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )

    store = open_private_root(
        args.private_artifact_root,
        repository_root=ROOT,
        allow_same_device=True,
    )
    measured_inputs = []
    measured_results = []
    support_choices: list[str] = []
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(step_rows[0][3])
        controller = ReadOnlyController(emulator)
        initial_runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture_for(step_rows[0][3], initial_state_sha),
            emulator=controller,
            reader=PokemonRedStateReader(controller),
        )
        initial = initial_runtime.adapter.observe().collection_observation
        registration = observation_from_collection(
            initial,
            seen_species=initial.owned_species,
            national_ids={red_species_ref(n): n for n in range(1, 152)},
            run_id=run_id,
            game_id=RED_COLLECTION_GAME_ID,
            adapter_id="red-autonomous-collection-v1",
            cartridge_sha256=str(_mapping(plan["rom"], "rom").get("sha256")),
            snapshot_sha256=initial_state_sha,
            sequence=0,
        )
        protected = Counter(
            specimen.species_ref
            for specimen in initial.specimens
            if specimen.location.value == "party"
        )
        policy = RedRegistrationPolicy(
            RegistrationSnapshot((registration,)),
            run_id,
            initial_state_sha,
            initial,
            protected,
            completion_scope="local_red",
        )

        def observe(state: bytes, state_sha: str):
            emulator.load_state_bytes(state)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture_for(state, state_sha),
                emulator=controller,
                reader=PokemonRedStateReader(controller),
            )
            raw = runtime.adapter.observe()
            economy = red_economy_snapshot(raw.raw)
            if economy is None:
                raise ValueError("autonomous economy observation is unavailable")
            return project_registered_observation(raw, policy).public_dict(), economy

        for ordinal, step_row in enumerate(step_rows):
            (
                intent,
                decision,
                outcome,
                before_state,
                terminal_state,
                intent_sha,
                decision_sha,
                outcome_sha,
            ) = step_row
            before_sha = str(outcome["before_state_sha256"])
            terminal_sha = str(outcome["terminal_state_sha256"])
            mode = decision.get("mode")
            if mode != "model_exploration":
                if (
                    mode != "deterministic_safety"
                    or outcome.get("selected_kind") != "manage_storage"
                    or outcome.get("learning_eligible") is not False
                    or outcome.get("support_role") != "deterministic_storage_safety"
                    or decision.get("teacher_labels") != 0
                ):
                    raise ValueError("autonomous nonlearning support differs")
                support_choices.append(f"{run_id}:step-{ordinal:03d}")
                continue
            if outcome.get("learning_eligible") not in (None, True) or outcome.get(
                "support_role"
            ) not in (None,):
                raise ValueError("autonomous model learning role differs")
            before_observation, before_economy = observe(before_state, before_sha)
            after_observation, after_economy = observe(terminal_state, terminal_sha)
            measured, result = publish_autonomous_measured_choice(
                store,
                behavior=prior,
                run_id=run_id,
                ordinal=ordinal,
                intent=intent,
                decision=decision,
                outcome=outcome,
                before_observation=before_observation,
                after_observation=after_observation,
                before_economy=before_economy,
                after_economy=after_economy,
                autonomous_plan_sha256=hashlib.sha256(run_plan_bytes).hexdigest(),
                autonomous_result_sha256=hashlib.sha256(run_result_bytes).hexdigest(),
                intent_sha256=intent_sha,
                decision_sha256=decision_sha,
                outcome_sha256=outcome_sha,
                source_commit=str(provenance.get("source_commit")),
                source_bundle_sha256=str(provenance.get("source_bundle_sha256")),
                execution_maximum_actions=execution_maximum_actions,
                execution_maximum_frames=execution_maximum_frames,
            )
            measured_inputs.append(measured)
            measured_results.append(result)

    def resolve(expected: str):
        if expected == prior.model.model_sha256:
            return prior
        record = store.find_sealed_record(f"rpr-model-{expected}", expected_kind="red_player_model")
        if record is None:
            record = store.find_sealed_record(
                f"rp-model-{expected}", expected_kind="red_player_model"
            )
        if record is None:
            raise ValueError("recorded behavior model is unavailable")
        return load_player_goal_model_record_bytes(
            record.read_bytes(), expected_model_sha256=expected
        )

    fitted = fit_incremental_registered_results(
        store,
        prior=prior,
        results=tuple(measured_results),
        resolve=resolve,
        source_commit=source.git_commit,
        source_bundle_sha256=committed_source_bundle_sha256(ROOT),
    )
    result = {
        "schema": "pokemon.red.autonomous-collection-fit.v1",
        "run_id": run_id,
        "admitted_choices": [item.choice_id for item in measured_inputs],
        "support_choices": support_choices,
        "teacher_actions": 0,
        "replayed_actions": 0,
        "fit": fitted,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.result is not None:
        with args.result.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
