#!/usr/bin/env python3
"""Preflight or execute one frozen natural middle-PP preparation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.battle_runtime import (  # noqa: E402
    BattleIntent,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    ROUTE_11_TRAINING_VENUE,
    VERMILION_CENTER_TO_ROUTE_11,
    _field_fly_to_vermilion_from_cinnabar,
    _move,
    _pulse,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressEnvelope,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import (  # noqa: E402
    ControllerTiming,
    CountingExecutor,
    FrameSafeExecutor,
)
from pokemon_red_completion.gen1_cartridge import wild_tables  # noqa: E402
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCapture,
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import (  # noqa: E402
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactWriter,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_party import (  # noqa: E402
    PP_VALUE_MASK,
    PokemonRedPartyReader,
)
from pokemon_red_completion.red_party_development_pp_materialization import (  # noqa: E402
    RedPartyDevelopmentPpMaterializationPlan,
    RedPpMaterializationSource,
    RedPpStartAdapter,
    red_pp_protected_state_sha256,
    red_pp_source_boundary_sha256,
    red_pp_venue_binding_sha256,
)
from pokemon_red_completion.red_party_pp import (  # noqa: E402
    decode_red_party_pp,
)
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_rom_path,
    verify_rom_bytes,
)
from pokemon_red_completion.route_evidence import (  # noqa: E402
    rom_adjacent_artifacts,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.surge import VERMILION_PC_TO_NURSE  # noqa: E402

_MAX_JSON_BYTES = 4 * 1024 * 1024
_OUTPUT_STATE_CLAIM = b"pokemon-red-party-pp-materialization-attempt-claim-v1\n"
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_CI_RUN_JSON_FIELDS = "attempt,conclusion,databaseId,event,headSha,status,url,workflowName"
_PRIVATE_PATH_TOKEN = re.compile(
    r"(?i)(?:file:(?://)?[^\s'\"]+|(?<![\w])~(?:[/\\][^\s'\"]*)?"
    r"|(?<![\w])(?:\.{1,2}[/\\][^\s'\"]+"
    r"|(?=[^\s'\"]*[a-z_.-])(?:[a-z0-9_.-]+[/\\])+[^\s'\"]+)"
    r"|(?<![\w])/(?:[^\s'\"]+)|(?<![\w])[a-z]:[/\\][^\s'\"]+"
    r"|\\\\[^\s'\"]+)"
)
_BATTLE_INTENT = BattleIntent(
    "train_party",
    battle_plan_id="red.party-pp-materialization",
)


class RedPartyPpMaterializationRunError(RuntimeError):
    """Raised before an unsafe or ambiguous preparation can be accepted."""


class _HardBoundedCountingExecutor(CountingExecutor):
    """Refuse the controller action that would cross either frozen hard cap."""

    def __init__(
        self,
        delegate: FrameSafeExecutor,
        *,
        emulator: PyBoyAdapter,
        timing: ControllerTiming,
        start_frame: int,
        maximum_actions: int,
        maximum_frames: int,
    ) -> None:
        super().__init__(delegate)
        self._emulator = emulator
        self._timing = timing
        self._start_frame = start_frame
        self._maximum_actions = maximum_actions
        self._maximum_frames = maximum_frames

    def execute(self, action: MacroAction) -> object:
        predicted_frames = action.repeat * (
            self._timing.wait_frames
            if action.kind is MacroActionKind.WAIT
            else self._timing.press_frames + self._timing.release_frames
        )
        if (
            self.actions_executed >= self._maximum_actions
            or self._emulator.frame_count - self._start_frame + predicted_frames
            > self._maximum_frames
        ):
            raise RedPartyPpMaterializationRunError(
                "PP preparation refused a controller action beyond its frozen bound"
            )
        result = super().execute(action)
        if (
            self.actions_executed > self._maximum_actions
            or self._emulator.frame_count - self._start_frame > self._maximum_frames
        ):  # pragma: no cover - exact FrameSafeExecutor accounting owns this
            raise AssertionError("PP executor crossed a prechecked hard bound")
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-file-sha256", required=True)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--checkpoint-inventory", type=Path, required=True)
    parser.add_argument("--checkpoint-inventory-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument(
        "--partition",
        choices=tuple(item.value for item in ScenarioPartition),
        required=True,
    )
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--out-state", type=Path, default=None)
    parser.add_argument("--exact-ci-run", type=int, default=None)
    parser.add_argument("--exact-ci-attempt", type=int, default=None)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="consume exactly one selected preparation identity",
    )
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyPpMaterializationRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise RedPartyPpMaterializationRunError(f"{subject} file digest or size differs")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyPpMaterializationRunError(f"{subject} is not valid ASCII JSON") from error
    if not isinstance(value, Mapping):
        raise RedPartyPpMaterializationRunError(f"{subject} document is invalid")
    return value


def _validate_execution_request(
    *,
    execute: bool,
    private_root: Path | None,
    out_state: Path | None,
    exact_ci_run: int | None,
    exact_ci_attempt: int | None,
) -> tuple[Path, Path, int, int] | None:
    for value, subject in (
        (exact_ci_run, "run"),
        (exact_ci_attempt, "attempt"),
    ):
        if value is not None and (
            type(value) is not int or value <= 0  # noqa: E721
        ):
            raise RedPartyPpMaterializationRunError(f"exact CI {subject} identity is invalid")
    if not execute:
        if (
            private_root is not None
            or out_state is not None
            or exact_ci_run is not None
            or exact_ci_attempt is not None
        ):
            raise RedPartyPpMaterializationRunError(
                "read-only PP preflight cannot accept execution-only arguments"
            )
        return None
    if (
        private_root is None
        or out_state is None
        or exact_ci_run is None
        or exact_ci_attempt is None
    ):
        raise RedPartyPpMaterializationRunError(
            "PP execution requires private root, output state, exact CI run and attempt"
        )
    return private_root, out_state, exact_ci_run, exact_ci_attempt


def _require_exact_green_ci_run(
    exact_ci_run: int,
    exact_ci_attempt: int,
    *,
    source_commit: str,
) -> Mapping[str, object]:
    """Authenticate the owner-named Actions run before any attempt is claimed."""

    if (
        type(exact_ci_run) is not int  # noqa: E721
        or exact_ci_run <= 0
        or type(exact_ci_attempt) is not int  # noqa: E721
        or exact_ci_attempt <= 0
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise RedPartyPpMaterializationRunError("PP execution CI binding is invalid")
    command = (
        "gh",
        "run",
        "view",
        str(exact_ci_run),
        "--repo",
        _GITHUB_REPOSITORY,
        "--json",
        _CI_RUN_JSON_FIELDS,
    )
    environment = {**os.environ, "GH_PROMPT_DISABLED": "1"}
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RedPartyPpMaterializationRunError(
            "PP execution could not authenticate its exact CI run"
        ) from error
    if completed.returncode != 0:
        raise RedPartyPpMaterializationRunError(
            "PP execution could not authenticate its exact CI run"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RedPartyPpMaterializationRunError("PP execution CI evidence is invalid") from error
    expected_url = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    if (
        not isinstance(document, Mapping)
        or document.get("databaseId") != exact_ci_run
        or document.get("headSha") != source_commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("workflowName") != _CI_WORKFLOW_NAME
        or document.get("event") != "pull_request"
        or document.get("url") != expected_url
        or type(document.get("attempt")) is not int  # noqa: E721
        or document.get("attempt") != exact_ci_attempt
    ):
        raise RedPartyPpMaterializationRunError(
            "PP execution CI run is not the exact successful source-bound run"
        )
    return document


def _require_designated_private_root(
    private_root: Path,
    *,
    protected_inputs: tuple[Path, ...],
    output_state: Path,
) -> Path:
    resolved_root = _require_external(private_root, subject="artifact root")
    if not all(path.resolve().is_relative_to(resolved_root) for path in protected_inputs):
        raise RedPartyPpMaterializationRunError(
            "PP execution root does not contain every authenticated private input"
        )
    if not output_state.resolve().is_relative_to(resolved_root):
        raise RedPartyPpMaterializationRunError(
            "PP output state must remain inside the designated private root"
        )
    return resolved_root


def _require_output_boundary(output_state: Path) -> None:
    """Reject an output that cannot be committed safely after controller use."""

    parent = output_state.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise RedPartyPpMaterializationRunError(
            "PP output parent must already be a writable private directory"
        )
    if output_state.is_symlink():
        raise RedPartyPpMaterializationRunError("PP output state cannot be a symbolic link")


def _require_fresh_output_identity(
    output_state: Path,
    entry: RedPpMaterializationSource,
) -> Path:
    """Bind one unoccupied owner-only output pair to the selected plan entry."""

    output_envelope = Path(f"{output_state}.json")
    if (
        output_state.name != f"{entry.output_capture_id}.state"
        or output_state.exists()
        or output_envelope.exists()
        or output_envelope.is_symlink()
    ):
        raise RedPartyPpMaterializationRunError(
            "PP output identity is occupied or differs from the frozen plan"
        )
    _require_output_boundary(output_state)
    return output_envelope


def _require_protected_files_unchanged(
    expected_digests: Mapping[Path, str],
) -> None:
    try:
        observed = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in expected_digests
        }
    except OSError:
        raise RedPartyPpMaterializationRunError(
            "PP execution could not revalidate every authenticated private input"
        ) from None
    if observed != expected_digests:
        raise RedPartyPpMaterializationRunError(
            "PP execution changed an authenticated private input"
        )


def _require_rom_adjacent_unchanged(
    rom_path: Path,
    expected: tuple[tuple[bool, str | None], ...],
    *,
    operation: str,
) -> None:
    if rom_adjacent_artifacts(rom_path) != expected:
        raise RedPartyPpMaterializationRunError(f"PP {operation} created a ROM-adjacent artifact")


def _source_paths(
    catalog_root: Path,
    entry: RedPpMaterializationSource,
) -> tuple[Path, Path]:
    state = catalog_root / "captures" / f"{entry.source_checkpoint_id}.state"
    envelope = state.with_suffix(".state.json")
    if not state.is_file() or not envelope.is_file():
        raise RedPartyPpMaterializationRunError(
            "PP source is missing its authenticated capture files"
        )
    return state, envelope


def _require_source_capture_bindings(
    *,
    capture: GoalManagerContextCapture,
    entry: RedPpMaterializationSource,
    root_lineage_id: str,
    reservation_plan: PartyDevelopmentQuestionReservationPlan,
    inventory_entry: PartyDevelopmentInventoryEntry,
) -> None:
    """Authenticate the selected source against lineage, exclusions and inventory."""

    if (
        capture.capture_id != entry.source_checkpoint_id
        or capture.state_sha256 != entry.source_state_sha256
        or capture.envelope_sha256 != entry.source_envelope_sha256
        or root_lineage_id != entry.source_root_lineage_id
        or root_lineage_id in reservation_plan.excluded_root_lineage_ids
        or entry.source_state_sha256 in reservation_plan.excluded_state_sha256
    ):
        raise RedPartyPpMaterializationRunError("PP source capture differs from its frozen lineage")
    if (
        inventory_entry.checkpoint_id != entry.source_checkpoint_id
        or inventory_entry.state_sha256 != entry.source_state_sha256
        or inventory_entry.envelope_sha256 != entry.source_envelope_sha256
        or inventory_entry.semantic_signature_sha256 != entry.source_semantic_signature_sha256
    ):
        raise RedPartyPpMaterializationRunError(
            "PP source differs from the authenticated inventory"
        )


def _selected_entry(
    plan: RedPartyDevelopmentPpMaterializationPlan,
    partition: ScenarioPartition,
) -> RedPpMaterializationSource:
    matches = tuple(item for item in plan.entries if item.partition is partition)
    if len(matches) != 1:
        raise RedPartyPpMaterializationRunError(
            "PP plan does not contain one selected partition entry"
        )
    return matches[0]


def _selected_inventory_entry(
    inventory: PartyDevelopmentCheckpointInventory,
    checkpoint_id: str,
) -> PartyDevelopmentInventoryEntry:
    matches = tuple(item for item in inventory.entries if item.checkpoint_id == checkpoint_id)
    if len(matches) != 1:
        raise RedPartyPpMaterializationRunError(
            "PP source differs from the authenticated inventory"
        )
    return matches[0]


def _require_execution_input_bindings(
    *,
    plan: RedPartyDevelopmentPpMaterializationPlan,
    reservation_plan: PartyDevelopmentQuestionReservationPlan,
    inventory: PartyDevelopmentCheckpointInventory,
    registry: PartyDevelopmentVenuePriorRegistry,
    source_commit: str,
    source_bundle_sha256: str,
    runner_source_sha256: str,
    reservation_plan_file_sha256: str,
    checkpoint_inventory_file_sha256: str,
    venue_prior_registry_file_sha256: str,
) -> None:
    """Require every parsed private input to match the frozen execution plan."""

    if (
        source_commit != plan.source_commit
        or source_bundle_sha256 != plan.source_bundle_sha256
        or runner_source_sha256 != plan.runner_source_sha256
        or reservation_plan.plan_sha256 != plan.reservation_plan_sha256
        or reservation_plan_file_sha256 != plan.reservation_plan_file_sha256
        or inventory.inventory_sha256 != plan.inventory_sha256
        or checkpoint_inventory_file_sha256 != plan.inventory_file_sha256
        or registry.registry_sha256 != plan.venue_prior_registry_sha256
        or venue_prior_registry_file_sha256 != plan.venue_prior_registry_file_sha256
        or len(registry.entries) != plan.venue_prior_count
    ):
        raise RedPartyPpMaterializationRunError("PP execution inputs differ from the frozen plan")


def _require_context_catalog_binding(
    *,
    observed_catalog_sha256: str,
    context_catalog_file_sha256: str,
    plan: RedPartyDevelopmentPpMaterializationPlan,
) -> None:
    if (
        observed_catalog_sha256 != plan.context_catalog_sha256
        or context_catalog_file_sha256 != plan.context_catalog_file_sha256
    ):
        raise RedPartyPpMaterializationRunError("PP context catalog differs from the frozen plan")


def _require_rom_binding(
    *,
    observed_rom_sha256: str,
    plan: RedPartyDevelopmentPpMaterializationPlan,
) -> None:
    if observed_rom_sha256 != plan.rom_sha256:
        raise RedPartyPpMaterializationRunError("PP execution ROM differs from the frozen plan")


def _require_runtime_venue_binding(
    *,
    registry: PartyDevelopmentVenuePriorRegistry,
    entry: RedPpMaterializationSource,
    rom_bytes: bytes,
) -> None:
    """Re-derive the selected venue from the authenticated ROM and registry."""

    venue = ROUTE_11_TRAINING_VENUE
    slots = wild_tables(rom_bytes).get(venue.map_id)
    evidence = registry.evidence_for(venue.band)
    if not slots or evidence is None:
        raise RedPartyPpMaterializationRunError(
            "PP execution cannot re-derive its frozen venue evidence"
        )
    wild_species_ids = tuple(sorted({species for _level, species in slots}))
    maximum_wild_level = max(level for level, _species in slots)
    observed_binding = red_pp_venue_binding_sha256(
        venue.band,
        map_id=venue.map_id,
        venue_prior_evidence_sha256=evidence.evidence_sha256,
        operational_contract_sha256=evidence.operational_contract_sha256,
        wild_species_ids=wild_species_ids,
        maximum_wild_level=maximum_wild_level,
    )
    if (
        entry.venue_map_id != venue.map_id
        or entry.possible_wild_species_ids != wild_species_ids
        or entry.venue_maximum_wild_level != maximum_wild_level
        or entry.venue_binding_sha256 != observed_binding
    ):
        raise RedPartyPpMaterializationRunError(
            "PP execution venue differs from its cartridge-bound prior"
        )


def _require_output_claim_unchanged(
    output_state: Path,
    expected_sha256: str,
) -> None:
    try:
        observed_sha256 = hashlib.sha256(output_state.read_bytes()).hexdigest()
    except OSError:
        raise RedPartyPpMaterializationRunError(
            "PP output attempt claim changed before controller entry"
        ) from None
    if observed_sha256 != expected_sha256:
        raise RedPartyPpMaterializationRunError(
            "PP output attempt claim changed before controller entry"
        )


def _party_experience(emulator: PyBoyAdapter, *, subject: str) -> tuple[int, ...]:
    observed = tuple(member.experience for member in PokemonRedPartyReader(emulator).read().members)
    if any(value is None for value in observed):
        raise RedPartyPpMaterializationRunError(
            f"PP {subject} lacks complete party-experience evidence"
        )
    return tuple(value for value in observed if value is not None)


def _observe_and_authenticate_source(
    emulator: PyBoyAdapter,
    entry: RedPpMaterializationSource,
) -> tuple[PokemonRedStateReader, RawGameState, str]:
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    input_ready = reader.read_input_readiness().ready
    pokedex = reader.read_pokedex_state()
    boxes = reader.read_all_box_states()
    party_experience = _party_experience(emulator, subject="execution source")
    if (
        not raw.game_started
        or raw.battle_state != 0
        or not input_ready
        or red_pp_source_boundary_sha256(raw, input_ready=input_ready)
        != entry.source_boundary_sha256
        or red_pp_protected_state_sha256(
            raw,
            pokedex,
            boxes,
            party_experience,
            target_party_slot=entry.target_party_slot,
        )
        != entry.protected_state_sha256
    ):
        raise RedPartyPpMaterializationRunError(
            "PP execution source differs from its read-only preflight"
        )
    moves = raw.party_moves or ()
    pp = raw.party_pp or ()
    species = raw.party_species_ids or ()
    levels = raw.party_levels or ()
    hp = raw.party_hp or ()
    maximum_hp = raw.party_max_hp or ()
    index = entry.target_party_slot - 1
    if (
        len(moves) <= index
        or len(pp) <= index
        or len(species) <= index
        or len(levels) <= index
        or len(hp) <= index
        or len(maximum_hp) <= index
        or species[index] != entry.target_species_id
        or levels[index] != entry.target_level
        or hp[index] != entry.target_hp
        or maximum_hp[index] != entry.target_max_hp
        or tuple(moves[index]) != entry.target_move_ids
        or tuple(pp[index]) != entry.target_initial_packed_pp
    ):
        raise RedPartyPpMaterializationRunError("PP execution target differs from its private plan")
    pp_state = decode_red_party_pp(tuple(moves[index]), tuple(pp[index]))
    if (
        pp_state.current_total != entry.current_total_pp
        or pp_state.maximum_total != entry.maximum_total_pp
        or pp_state.minimum_consumption_to_middle != entry.minimum_pp_consumption
    ):
        raise RedPartyPpMaterializationRunError("PP execution source resource arithmetic drifted")
    return reader, raw, entry.protected_state_sha256


def _require_protected_state(
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    entry: RedPpMaterializationSource,
    expected_sha256: str,
) -> RawGameState:
    raw = reader.read()
    party_experience = _party_experience(emulator, subject="preparation state")
    observed = red_pp_protected_state_sha256(
        raw,
        reader.read_pokedex_state(),
        reader.read_all_box_states(),
        party_experience,
        target_party_slot=entry.target_party_slot,
    )
    if observed != expected_sha256:
        raise RedPartyPpMaterializationRunError(
            "PP preparation changed protected party, collection or story state"
        )
    return raw


def _require_runtime_bounds(
    *,
    plan: RedPartyDevelopmentPpMaterializationPlan,
    actions: CountingExecutor,
    frames_executed: int,
    battles_completed: int,
    encounter_steps: int,
) -> None:
    bounds = plan.bounds
    if (
        actions.actions_executed > bounds.maximum_controller_actions
        or frames_executed > bounds.maximum_frames
        or battles_completed > bounds.maximum_completed_battles
        or encounter_steps > bounds.maximum_encounter_steps
    ):
        raise RedPartyPpMaterializationRunError("PP preparation exhausted a frozen execution bound")


def _require_next_battle_capacity(
    *,
    battles_completed: int,
    maximum_completed_battles: int,
) -> None:
    """Reject a newly entered battle before it can cross the completed cap."""

    if battles_completed >= maximum_completed_battles:
        raise RedPartyPpMaterializationRunError(
            "PP preparation refused a battle beyond its frozen bound"
        )


def _require_next_encounter_step_capacity(
    *,
    encounter_steps: int,
    maximum_encounter_steps: int,
) -> None:
    """Reject the next encounter step before it can cross the step cap."""

    if encounter_steps >= maximum_encounter_steps:
        raise RedPartyPpMaterializationRunError(
            "PP preparation refused a step beyond its frozen bound"
        )


def _move_to_route_11(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    entry: RedPpMaterializationSource,
) -> None:
    if entry.start_adapter is RedPpStartAdapter.CINNABAR_CENTER_PC_TO_ROUTE_11:
        _move(
            actions,
            reader,
            VERMILION_PC_TO_NURSE,
            "PP preparation Cinnabar PC boundary",
        )
        _move(
            actions,
            reader,
            ("down",) * 5,
            "PP preparation Cinnabar Center exit",
        )
    elif entry.start_adapter is RedPpStartAdapter.CINNABAR_MART_CLERK_TO_ROUTE_11:
        _move(
            actions,
            reader,
            ("right", "down", "down", "down"),
            "PP preparation Cinnabar Mart exit",
        )
    else:  # pragma: no cover - enum and plan validation own this branch
        raise AssertionError("unsupported PP start adapter")
    raw = reader.read()
    if raw.map_id != MapId.CINNABAR_ISLAND or raw.battle_state:
        raise RedPartyPpMaterializationRunError(
            "PP preparation did not reach the Cinnabar outdoor boundary"
        )
    _field_fly_to_vermilion_from_cinnabar(actions, reader, emulator)
    raw = reader.read()
    if (
        raw.map_id != MapId.VERMILION_CITY
        or (raw.player_x, raw.player_y) != (11, 4)
        or raw.battle_state
    ):
        raise RedPartyPpMaterializationRunError(
            "PP preparation Fly did not reach the Vermilion boundary"
        )
    _move(
        actions,
        reader,
        VERMILION_CENTER_TO_ROUTE_11,
        "PP preparation Vermilion east approach",
    )
    for _ in range(24):
        before = reader.read()
        if before.map_id == entry.venue_map_id:
            return
        if before.battle_state:
            raise RedPartyPpMaterializationRunError(
                "PP preparation met a battle before its declared venue"
            )
        _pulse(actions, MacroActionKind.MOVE, "right", 120)
        after = reader.read()
        if after.map_id == entry.venue_map_id:
            return
        if after.battle_state:
            raise RedPartyPpMaterializationRunError(
                "PP preparation met a battle outside its declared venue"
            )
    raise RedPartyPpMaterializationRunError(
        "PP preparation did not reach its bounded encounter venue"
    )


def _current_target_pp(
    raw: RawGameState,
    entry: RedPpMaterializationSource,
) -> tuple[int, int]:
    moves = raw.party_moves or ()
    pp = raw.party_pp or ()
    index = entry.target_party_slot - 1
    if len(moves) <= index or len(pp) <= index:
        raise RedPartyPpMaterializationRunError("PP preparation lost target move evidence")
    state = decode_red_party_pp(tuple(moves[index]), tuple(pp[index]))
    return state.current_total, state.maximum_total


def _require_middle_pp_state(current_total: int, maximum_total: int) -> bool:
    """Return whether the target is in the middle bin; reject invalid/low state."""

    if (
        type(current_total) is not int  # noqa: E721
        or type(maximum_total) is not int  # noqa: E721
        or maximum_total <= 0
        or not 0 <= current_total <= maximum_total
    ):
        raise RedPartyPpMaterializationRunError(
            "PP preparation observed invalid target resource evidence"
        )
    if current_total * 100 >= maximum_total * 67:
        return False
    if current_total * 100 < maximum_total * 34:
        raise RedPartyPpMaterializationRunError(
            "PP preparation skipped past the middle resource bin"
        )
    return True


def _require_declared_wild_encounter(
    raw: RawGameState,
    entry: RedPpMaterializationSource,
) -> None:
    if (
        not raw.battle_state
        or type(raw.enemy_species_id) is not int  # noqa: E721
        or raw.enemy_species_id not in entry.possible_wild_species_ids
        or type(raw.enemy_level) is not int  # noqa: E721
        or not 1 <= raw.enemy_level <= entry.venue_maximum_wild_level
    ):
        raise RedPartyPpMaterializationRunError(
            "PP preparation observed an undeclared wild encounter"
        )


def _select_safe_move(
    policy_state: RawGameState,
    entry: RedPpMaterializationSource,
) -> int:
    level = policy_state.battler_level
    hp = policy_state.battler_hp
    maximum_hp = policy_state.battler_max_hp
    active_pp = policy_state.battler_pp
    disabled = policy_state.player_disabled_move_slot
    if disabled is None:
        disabled = 0
    if (
        policy_state.active_party_index != 0
        or policy_state.active_party_species_id != entry.target_species_id
        or type(level) is not int  # noqa: E721
        or not entry.target_level <= level <= entry.target_level + 1
        or policy_state.battler_moves != entry.target_move_ids
        or policy_state.battler_status != 0
        or type(hp) is not int  # noqa: E721
        or type(maximum_hp) is not int  # noqa: E721
        or not 0 < hp <= maximum_hp
        or hp * 2 <= maximum_hp
        or not isinstance(active_pp, tuple)
        or len(active_pp) != 4
        or type(disabled) is not int  # noqa: E721
        or not 0 <= disabled <= 4
    ):
        raise RedPartyPpMaterializationRunError(
            "PP preparation target crossed its per-turn safety boundary"
        )
    for slot in entry.safe_move_slots:
        if slot != disabled and active_pp[slot - 1] & PP_VALUE_MASK:
            return slot
    raise RedPartyPpMaterializationRunError("PP preparation has no safe declared move remaining")


def _require_ready_field_control(
    raw: RawGameState,
    *,
    input_ready: bool,
) -> None:
    if raw.battle_state or input_ready is not True:
        raise RedPartyPpMaterializationRunError(
            "PP preparation battle did not return to ready field control"
        )


def _require_terminal_acceptance(
    raw: RawGameState,
    entry: RedPpMaterializationSource,
    *,
    input_ready: bool,
    pressed_buttons: object,
    final_total: int,
    final_maximum: int,
    battles_completed: int,
) -> None:
    hp = raw.party_hp
    status = raw.party_status
    levels = raw.party_levels
    target_index = entry.target_party_slot - 1
    if (
        not raw.game_started
        or raw.map_id != entry.venue_map_id
        or raw.battle_state
        or input_ready is not True
        or bool(pressed_buttons)
        or not isinstance(hp, tuple)
        or not isinstance(status, tuple)
        or not isinstance(levels, tuple)
        or len(hp) != 6
        or len(status) != 6
        or len(levels) != 6
        or any(type(value) is not int or value <= 0 for value in hp)  # noqa: E721
        or any(type(value) is not int or value != 0 for value in status)  # noqa: E721
        or type(levels[target_index]) is not int  # noqa: E721
        or not entry.target_level <= levels[target_index] <= entry.target_level + 1
        or type(final_total) is not int  # noqa: E721
        or type(final_maximum) is not int  # noqa: E721
        or final_maximum != entry.maximum_total_pp
        or final_total > entry.middle_pp_ceiling
        or final_total * 100 < final_maximum * 34
        or entry.current_total_pp - final_total < entry.minimum_pp_consumption
        or type(battles_completed) is not int  # noqa: E721
        or battles_completed < 1
    ):
        raise RedPartyPpMaterializationRunError(
            "PP preparation terminal state failed its frozen acceptance gate"
        )


def _execute_preparation(
    *,
    plan: RedPartyDevelopmentPpMaterializationPlan,
    entry: RedPpMaterializationSource,
    rom_path: Path,
    capture_state_bytes: bytes,
    output_state: Path,
    progress_sink: Callable[[Mapping[str, object]], None],
) -> dict[str, object]:
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture_state_bytes)
        reader, _raw, protected_sha256 = _observe_and_authenticate_source(
            emulator,
            entry,
        )
        timing = DEFAULT_NEW_GAME_TIMING.controller_timing()
        start_frame = emulator.frame_count
        actions = _HardBoundedCountingExecutor(
            FrameSafeExecutor(emulator, timing),
            emulator=emulator,
            timing=timing,
            start_frame=start_frame,
            maximum_actions=plan.bounds.maximum_controller_actions,
            maximum_frames=plan.bounds.maximum_frames,
        )
        _move_to_route_11(actions, reader, emulator, entry)
        raw = _require_protected_state(
            reader,
            emulator,
            entry,
            protected_sha256,
        )
        if raw.map_id != entry.venue_map_id:
            raise RedPartyPpMaterializationRunError(
                "PP preparation relocation ended outside its venue"
            )

        battles_completed = 0
        encounter_steps = 0
        walker = ROUTE_11_TRAINING_VENUE.fresh_walk_to_grass()
        while True:
            raw = reader.read()
            current_total, maximum_total = _current_target_pp(raw, entry)
            if _require_middle_pp_state(current_total, maximum_total):
                break
            _require_runtime_bounds(
                plan=plan,
                actions=actions,
                frames_executed=emulator.frame_count - start_frame,
                battles_completed=battles_completed,
                encounter_steps=encounter_steps,
            )
            if raw.battle_state:
                _require_next_battle_capacity(
                    battles_completed=battles_completed,
                    maximum_completed_battles=(plan.bounds.maximum_completed_battles),
                )
                _require_declared_wild_encounter(raw, entry)

                run_adaptive_wild_battle(
                    reader,
                    actions,
                    lambda state: _select_safe_move(state, entry),
                    expected_map=entry.venue_map_id,
                    intent=_BATTLE_INTENT,
                    timing=ROUTE_11_TRAINING_VENUE.battle_timing,
                    label="natural PP preparation encounter",
                    unknown_cancel_interval=3,
                    transient_zero_pp_main_is_dialogue=False,
                )
                battles_completed += 1
                terminal = _require_protected_state(
                    reader,
                    emulator,
                    entry,
                    protected_sha256,
                )
                _require_ready_field_control(
                    terminal,
                    input_ready=reader.read_input_readiness().ready,
                )
                current_total, maximum_total = _current_target_pp(terminal, entry)
                progress_sink(
                    {
                        "record_type": "party_development_pp_materialization_progress",
                        "schema_version": 1,
                        "battles_completed": battles_completed,
                        "encounter_steps": encounter_steps,
                        "current_total_pp": current_total,
                        "maximum_total_pp": maximum_total,
                        "controller_actions": actions.actions_executed,
                        "frames_executed": emulator.frame_count - start_frame,
                        "candidate_menus_constructed": 0,
                        "learner_outcomes_opened": 0,
                        "teacher_queries": 0,
                        "model_predictions": 0,
                    }
                )
                continue

            if raw.map_id != entry.venue_map_id:
                raise RedPartyPpMaterializationRunError(
                    "PP preparation left its frozen encounter venue"
                )
            _require_next_encounter_step_capacity(
                encounter_steps=encounter_steps,
                maximum_encounter_steps=plan.bounds.maximum_encounter_steps,
            )
            encounter_steps += walker(actions, reader, emulator)

        terminal = _require_protected_state(
            reader,
            emulator,
            entry,
            protected_sha256,
        )
        final_total, final_maximum = _current_target_pp(terminal, entry)
        _require_terminal_acceptance(
            terminal,
            entry,
            input_ready=reader.read_input_readiness().ready,
            pressed_buttons=emulator.pressed_buttons,
            final_total=final_total,
            final_maximum=final_maximum,
            battles_completed=battles_completed,
        )
        _require_runtime_bounds(
            plan=plan,
            actions=actions,
            frames_executed=emulator.frame_count - start_frame,
            battles_completed=battles_completed,
            encounter_steps=encounter_steps,
        )
        emulator.save_state(output_state)
        os.chmod(output_state, 0o600)
        with output_state.open("rb+") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        output_state_sha256 = hashlib.sha256(output_state.read_bytes()).hexdigest()
        return {
            "record_type": "party_development_pp_materialization_terminal",
            "schema_version": 1,
            "partition": entry.partition.value,
            "output_capture_id": entry.output_capture_id,
            "output_state_sha256": output_state_sha256,
            "battles_completed": battles_completed,
            "encounter_steps": encounter_steps,
            "initial_total_pp": entry.current_total_pp,
            "final_total_pp": final_total,
            "maximum_total_pp": final_maximum,
            "pp_consumed": entry.current_total_pp - final_total,
            "final_pp_bin": "middle",
            "faints": 0,
            "new_persistent_statuses": 0,
            "heals": 0,
            "party_switches": 0,
            "captures": 0,
            "storage_accesses": 0,
            "controller_actions": actions.actions_executed,
            "frames_executed": emulator.frame_count - start_frame,
            "candidate_menus_constructed": 0,
            "learner_outcomes_opened": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
        }


def _authenticate_materialized_output(
    *,
    rom_path: Path,
    output_state: Path,
    entry: RedPpMaterializationSource,
    terminal: Mapping[str, object],
) -> None:
    """Reload the saved bytes before an envelope can make them a capture."""

    expected_state_sha256 = terminal.get("output_state_sha256")
    if (
        not isinstance(expected_state_sha256, str)
        or hashlib.sha256(output_state.read_bytes()).hexdigest() != expected_state_sha256
    ):
        raise RedPartyPpMaterializationRunError("PP output state changed before authentication")
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state(output_state)
        reader = PokemonRedStateReader(emulator)
        raw = _require_protected_state(
            reader,
            emulator,
            entry,
            entry.protected_state_sha256,
        )
        current_total, maximum_total = _current_target_pp(raw, entry)
        hp = raw.party_hp or ()
        status = raw.party_status or ()
        levels = raw.party_levels or ()
        if (
            raw.map_id != entry.venue_map_id
            or raw.battle_state
            or not reader.read_input_readiness().ready
            or len(hp) != 6
            or len(status) != 6
            or len(levels) != 6
            or any(value <= 0 for value in hp)
            or any(value != 0 for value in status)
            or levels[entry.target_party_slot - 1] > entry.target_level + 1
            or current_total != terminal.get("final_total_pp")
            or maximum_total != terminal.get("maximum_total_pp")
            or current_total > entry.middle_pp_ceiling
            or current_total * 100 < maximum_total * 34
        ):
            raise RedPartyPpMaterializationRunError(
                "PP output state failed independent reload authentication"
            )
    if hashlib.sha256(output_state.read_bytes()).hexdigest() != expected_state_sha256:
        raise RedPartyPpMaterializationRunError(
            "PP output state changed during reload authentication"
        )


def _publish_output_envelope(
    *,
    output_envelope: Path,
    entry: RedPpMaterializationSource,
    source_envelope: CapturedProgressEnvelope,
    output_state_sha256: str,
) -> str:
    output = CapturedProgressEnvelope(
        state_sha256=output_state_sha256,
        checkpoint_id=entry.output_capture_id,
        checkpoint_label="Natural middle-PP party curriculum boundary",
        checkpoints_completed=source_envelope.checkpoints_completed,
        checkpoints_total=source_envelope.checkpoints_total,
        verified_objective_ids=source_envelope.verified_objective_ids,
    )
    payload = (
        json.dumps(
            output.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")
    return _write_exclusive(output_envelope, payload)


def _write_exclusive(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _path_free_exception_message(message: str) -> str:
    return _PRIVATE_PATH_TOKEN.sub("[private-path]", message)


def _private_failure_record(error: BaseException) -> dict[str, object]:
    message = str(error)
    retained = _path_free_exception_message(message)
    return {
        "record_type": "party_development_pp_materialization_failure",
        "schema_version": 1,
        "exception_type": type(error).__name__,
        "exception_message": retained,
        "exception_message_retained_exactly": retained == message,
        "exception_message_redacted": retained != message,
        "exception_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "private_path_fields": 0,
    }


def _execute_with_retention(
    writer: PrivateArtifactWriter,
    execute: Callable[
        [Callable[[Mapping[str, object]], None]],
        dict[str, object],
    ],
) -> dict[str, object]:
    try:
        terminal = execute(lambda record: writer.append("progress", record, durable=True))
    except (Exception, KeyboardInterrupt, SystemExit) as error:
        with suppress(Exception):
            writer.append(
                "failure",
                _private_failure_record(error),
                durable=True,
            )
        raise
    writer.append("terminal", terminal, durable=True)
    return terminal


def _run(args: argparse.Namespace) -> dict[str, object]:
    execution_request = _validate_execution_request(
        execute=args.execute,
        private_root=args.private_root,
        out_state=args.out_state,
        exact_ci_run=args.exact_ci_run,
        exact_ci_attempt=args.exact_ci_attempt,
    )
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - publication guard owns this
        raise AssertionError("published PP execution lost its source commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    runner_source_sha256 = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()

    plan_path = _require_external(args.plan, subject="PP materialization plan")
    reservation_plan_path = _require_external(args.reservation_plan, subject="reservation plan")
    inventory_path = _require_external(args.checkpoint_inventory, subject="checkpoint inventory")
    registry_path = _require_external(args.venue_prior_registry, subject="venue-prior registry")
    catalog_root = _require_external(args.catalog_root, subject="context catalog root")
    context_catalog_path = _require_external(
        args.context_catalog, subject="historical context catalog"
    )
    plan = RedPartyDevelopmentPpMaterializationPlan.from_private_dict(
        _load_json(
            plan_path,
            expected_sha256=args.plan_file_sha256,
            subject="PP materialization plan",
        )
    )
    reservation_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_json(
            reservation_plan_path,
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            inventory_path,
            expected_sha256=args.checkpoint_inventory_file_sha256,
            subject="checkpoint inventory",
        )
    )
    registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            registry_path,
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue-prior registry",
        )
    )
    _require_execution_input_bindings(
        plan=plan,
        reservation_plan=reservation_plan,
        inventory=inventory,
        registry=registry,
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle_sha256,
        runner_source_sha256=runner_source_sha256,
        reservation_plan_file_sha256=args.reservation_plan_file_sha256,
        checkpoint_inventory_file_sha256=(args.checkpoint_inventory_file_sha256),
        venue_prior_registry_file_sha256=(args.venue_prior_registry_file_sha256),
    )
    partition = ScenarioPartition(args.partition)
    entry = _selected_entry(plan, partition)

    context_catalog_document = _load_json(
        context_catalog_path,
        expected_sha256=args.context_catalog_file_sha256,
        subject="historical context catalog",
    )
    context_catalog_source_commit = context_catalog_document.get("source_commit")
    if not isinstance(context_catalog_source_commit, str):
        raise RedPartyPpMaterializationRunError("historical context catalog source is invalid")
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_catalog_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        context_catalog_path.read_bytes(),
        historical_registry,
    )
    _require_context_catalog_binding(
        observed_catalog_sha256=context_catalog.catalog_sha256,
        context_catalog_file_sha256=args.context_catalog_file_sha256,
        plan=plan,
    )

    state_path, envelope_path = _source_paths(catalog_root, entry)
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    catalog_entry = context_catalog.entry(entry.source_checkpoint_id)
    root_lineage_id = catalog_entry.authenticated_root_lineage_id(
        slot_id=entry.source_checkpoint_id,
        capture_id=entry.source_checkpoint_id,
        state_sha256=entry.source_state_sha256,
        envelope_sha256=entry.source_envelope_sha256,
    )
    inventory_entry = _selected_inventory_entry(
        inventory,
        entry.source_checkpoint_id,
    )
    _require_source_capture_bindings(
        capture=capture,
        entry=entry,
        root_lineage_id=root_lineage_id,
        reservation_plan=reservation_plan,
        inventory_entry=inventory_entry,
    )

    rom_path = resolve_rom_path(args.rom)
    rom_bytes = rom_path.read_bytes()
    _require_rom_binding(
        observed_rom_sha256=verify_rom_bytes(
            rom_bytes,
            filename=rom_path.name,
        ).sha256,
        plan=plan,
    )
    _require_runtime_venue_binding(
        registry=registry,
        entry=entry,
        rom_bytes=rom_bytes,
    )
    adjacent_before = rom_adjacent_artifacts(rom_path)
    private_input_paths = (
        plan_path,
        reservation_plan_path,
        inventory_path,
        registry_path,
        context_catalog_path,
        state_path,
        envelope_path,
    )
    protected_files = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (*private_input_paths, rom_path)
    }
    protected_files[SCRIPT_PATH] = runner_source_sha256
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        _observe_and_authenticate_source(emulator, entry)

    preflight = {
        "schema": "pokemon.red.party-development-pp-materialization-preflight.v1",
        "status": "ready" if execution_request is not None else "ready_authorization_required",
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "runner_source_sha256": runner_source_sha256,
        "private_plan_sha256": plan.plan_sha256,
        "private_plan_file_sha256": args.plan_file_sha256,
        "partition": partition.value,
        "source_root_authenticated": True,
        "source_state_authenticated": True,
        "source_pp_bin": "high",
        "target_pp_bin": "middle",
        "safe_move_capacity_sufficient": True,
        "wild_species_seen_coverage_complete": True,
        "execution_authorized": execution_request is not None,
        "materializations_completed": 0,
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    if execution_request is None:
        _require_rom_adjacent_unchanged(
            rom_path,
            adjacent_before,
            operation="read-only preflight",
        )
        return preflight

    (
        requested_root,
        requested_output_state,
        exact_ci_run,
        exact_ci_attempt,
    ) = execution_request
    authenticated_ci_run = _require_exact_green_ci_run(
        exact_ci_run,
        exact_ci_attempt,
        source_commit=source.git_commit,
    )
    output_state = _require_external(
        requested_output_state,
        subject="prepared output state",
    )
    output_envelope = _require_fresh_output_identity(output_state, entry)
    designated_root = _require_designated_private_root(
        requested_root,
        protected_inputs=private_input_paths,
        output_state=output_state,
    )
    private_root = open_private_root(
        designated_root,
        repository_root=PROJECT_ROOT,
    )
    artifact_id = f"red-party-pp-materialization-v1-{partition.value}"
    writer = private_root.begin_artifact(
        artifact_id,
        kind="party_development_pp_materialization",
    )
    with writer:
        writer.append(
            "plan",
            {
                "record_type": "party_development_pp_materialization_plan",
                "schema_version": 1,
                "source_commit": source.git_commit,
                "source_bundle_sha256": source_bundle_sha256,
                "exact_ci_run": exact_ci_run,
                "exact_ci_run_attempt": exact_ci_attempt,
                "exact_ci_workflow": authenticated_ci_run["workflowName"],
                "exact_ci_head_sha": authenticated_ci_run["headSha"],
                "private_plan_sha256": plan.plan_sha256,
                "private_plan_file_sha256": args.plan_file_sha256,
                "partition": partition.value,
                "scenario_id": entry.scenario_id,
                "source_checkpoint_id": entry.source_checkpoint_id,
                "source_root_lineage_id": entry.source_root_lineage_id,
                "source_state_sha256": entry.source_state_sha256,
                "output_capture_id": entry.output_capture_id,
                "retry_after_controller_input": False,
                "candidate_menus_constructed": 0,
                "learner_outcomes_opened": 0,
                "teacher_queries": 0,
                "model_predictions": 0,
            },
            durable=True,
        )
        output_claim_sha256 = _write_exclusive(
            output_state,
            _OUTPUT_STATE_CLAIM,
        )
        writer.append(
            "output_claim",
            {
                "record_type": "party_development_pp_output_claim",
                "schema_version": 1,
                "partition": partition.value,
                "output_capture_id": entry.output_capture_id,
                "claim_sha256": output_claim_sha256,
                "controller_actions": 0,
                "retry_after_controller_input": False,
                "private_path_fields": 0,
            },
            durable=True,
        )

        def execute_and_validate(
            progress_sink: Callable[[Mapping[str, object]], None],
        ) -> dict[str, object]:
            _require_output_claim_unchanged(
                output_state,
                output_claim_sha256,
            )
            terminal = _execute_preparation(
                plan=plan,
                entry=entry,
                rom_path=rom_path,
                capture_state_bytes=capture.state_bytes,
                output_state=output_state,
                progress_sink=progress_sink,
            )
            _require_protected_files_unchanged(protected_files)
            _require_rom_adjacent_unchanged(
                rom_path,
                adjacent_before,
                operation="execution",
            )
            _authenticate_materialized_output(
                rom_path=rom_path,
                output_state=output_state,
                entry=entry,
                terminal=terminal,
            )
            _require_protected_files_unchanged(protected_files)
            _require_rom_adjacent_unchanged(
                rom_path,
                adjacent_before,
                operation="output authentication",
            )
            output_state_sha256 = terminal.get("output_state_sha256")
            if not isinstance(output_state_sha256, str):  # pragma: no cover
                raise AssertionError("terminal PP state digest disappeared")
            envelope_sha256 = _publish_output_envelope(
                output_envelope=output_envelope,
                entry=entry,
                source_envelope=capture.envelope,
                output_state_sha256=output_state_sha256,
            )
            return {
                **terminal,
                "output_envelope_sha256": envelope_sha256,
                "output_reload_authenticated": True,
            }

        terminal = _execute_with_retention(writer, execute_and_validate)

    return {
        **preflight,
        "schema": "pokemon.red.party-development-pp-materialization-result.v1",
        "status": "complete_context_prepared",
        "exact_ci_run": exact_ci_run,
        "exact_ci_run_attempt": exact_ci_attempt,
        "exact_ci_authenticated": True,
        "artifact": writer.summary.public_dict(),
        "materializations_completed": 1,
        "controller_actions": terminal["controller_actions"],
        "frames_executed": terminal["frames_executed"],
        "battles_completed": terminal["battles_completed"],
        "encounter_steps": terminal["encounter_steps"],
        "pp_consumed": terminal["pp_consumed"],
        "final_pp_bin": "middle",
        "heals": 0,
        "faints": 0,
        "party_switches": 0,
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "model_fit": False,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except KeyboardInterrupt:
        raise
    except Exception as error:
        parser.error(
            "Red PP materialization failed closed; private paths were withheld. "
            f"Failure type: {type(error).__name__}."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
