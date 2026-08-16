#!/usr/bin/env python3
"""Inspect reserved Red party questions without freezing or executing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.captured_progress import (  # noqa: E402
    load_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.gen1_cartridge import evolution_graph  # noqa: E402
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import PartyMemberObservation  # noqa: E402
from pokemon_red_completion.party_development_adapter import (  # noqa: E402
    BoundPartyDevelopmentMenu,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (  # noqa: E402
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (  # noqa: E402
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RedPartyDevelopmentQuestionPreflight,
    build_red_party_development_snapshot,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.team_training import GrindingArea  # noqa: E402
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingChoiceKind,
)

_SHA256_LENGTH = 64


class RedPartyDevelopmentPreflightRunError(RuntimeError):
    """Raised before a private question can be inspected ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument(
        "--second-venue-operational-contract-sha256",
        required=True,
        help="prospectively reviewed contract for the still-unmeasured second venue",
    )
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _load_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RedPartyDevelopmentPreflightRunError(f"{subject} file digest differs")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyDevelopmentPreflightRunError(
            f"{subject} is not valid canonical JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentPreflightRunError(f"{subject} document is invalid")
    return value


def _require_digest(value: str, *, subject: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RedPartyDevelopmentPreflightRunError(f"{subject} digest is invalid")


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyDevelopmentPreflightRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _question_paths(catalog_root: Path, checkpoint_id: str) -> tuple[Path, Path, Path]:
    state = catalog_root / "captures" / f"{checkpoint_id}.state"
    envelope = state.with_suffix(".state.json")
    profile = catalog_root / "profiles" / f"{checkpoint_id}.json"
    if not state.is_file() or not envelope.is_file() or not profile.is_file():
        raise RedPartyDevelopmentPreflightRunError(
            "reserved question is missing its capture, envelope, or profile"
        )
    return state, envelope, profile


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - publication guard owns this
        raise AssertionError("published party preflight lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)

    plan_path = _require_external(args.reservation_plan, subject="reservation plan")
    registry_path = _require_external(
        args.venue_prior_registry,
        subject="venue-prior registry",
    )
    catalog_root = _require_external(args.catalog_root, subject="context catalog")
    context_catalog_path = _require_external(
        args.context_catalog,
        subject="historical context catalog",
    )
    plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_json(
            plan_path,
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            registry_path,
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue-prior registry",
        )
    )
    context_catalog_document = _load_json(
        context_catalog_path,
        expected_sha256=args.context_catalog_file_sha256,
        subject="historical context catalog",
    )
    context_catalog_source_commit = context_catalog_document.get("source_commit")
    if not isinstance(context_catalog_source_commit, str):
        raise RedPartyDevelopmentPreflightRunError(
            "historical context catalog source is invalid"
        )
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_catalog_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        context_catalog_path.read_bytes(),
        historical_registry,
    )
    if plan.venue_prior_registry_sha256 != venue_registry.registry_sha256:
        raise RedPartyDevelopmentPreflightRunError(
            "reservation plan and venue-prior registry differ"
        )
    _require_digest(
        args.second_venue_operational_contract_sha256,
        subject="second venue operational contract",
    )

    route_area = ROUTE_11_TRAINING_VENUE.band
    cave_area = DIGLETTS_CAVE_TRAINING_VENUE.band
    route_evidence = venue_registry.evidence_for(route_area)
    if route_evidence is None:
        raise RedPartyDevelopmentPreflightRunError(
            "reservation registry lacks the qualified shared-venue prior"
        )
    areas = (route_area, cave_area)
    operational_contracts = (
        route_evidence.operational_contract_sha256,
        args.second_venue_operational_contract_sha256,
    )

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    cartridge_evolutions = evolution_graph(rom_path.read_bytes())
    adjacent_before = rom_adjacent_artifacts(rom_path)
    protected_files = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (plan_path, registry_path, context_catalog_path)
    }

    inspected = 0
    prospectively_validated = 0
    canonical_root_bindings_resolved = 0
    pending_preparation = 0
    kind_counts: Counter[str] = Counter()
    candidate_widths: Counter[int] = Counter()
    availability_widths: Counter[int] = Counter()
    unavailable_reasons: Counter[str] = Counter()

    for reservation in plan.reservations:
        if reservation.preparation is not PartyDevelopmentContextPreparation.NONE:
            pending_preparation += 1
            continue
        state_path, envelope_path, profile_path = _question_paths(
            catalog_root,
            reservation.source_checkpoint_id,
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path, profile_path)
        }
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        if (
            capture.capture_id != reservation.source_checkpoint_id
            or capture.state_sha256 != reservation.source_state_sha256
            or capture.envelope_sha256 != reservation.source_envelope_sha256
        ):
            raise RedPartyDevelopmentPreflightRunError(
                "reserved capture identity differs from its authenticated source"
            )
        # Re-load through the older envelope helper as a second independent
        # envelope/state association check. It performs no emulator action.
        loaded = load_captured_progress(envelope_path, state_path=state_path)
        if (
            loaded.checkpoint_id != capture.capture_id
            or loaded.state_sha256 != capture.state_sha256
        ):
            raise RedPartyDevelopmentPreflightRunError(
                "reserved capture loaders disagree"
            )
        profile = load_red_goal_context_profile(profile_path)
        catalog_entry = context_catalog.entry(reservation.source_checkpoint_id)
        source_root_lineage_id = catalog_entry.authenticated_root_lineage_id(
            slot_id=reservation.source_checkpoint_id,
            capture_id=reservation.source_checkpoint_id,
            state_sha256=reservation.source_state_sha256,
            envelope_sha256=reservation.source_envelope_sha256,
        )
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()

        snapshot = build_red_party_development_snapshot(
            reservation,
            source_root_lineage_id=source_root_lineage_id,
            observation=observation,
            evolutions=cartridge_evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
            areas=areas,
            venue_prior_registry=venue_registry,
            venue_operational_contract_sha256=operational_contracts,
            source_commit=source.git_commit,
            source_bundle_sha256=source_bundle_sha256,
        )
        menu: (
            BoundPartyDevelopmentMenu[PartyMemberObservation]
            | BoundPartyDevelopmentMenu[GrindingArea]
            | None
        )
        if reservation.kind is TrainingChoiceKind.TRAINEE:
            menu = snapshot.trainee_menu(route_area)
        else:
            fixed_trainee = snapshot.unique_weakest_goal_relevant_venue_trainee()
            menu = snapshot.venue_menu(fixed_trainee)
        if menu is None or len(menu.bindings) < 2:
            raise RedPartyDevelopmentPreflightRunError(
                "reserved state does not expose a genuine multi-candidate question"
            )

        inspected += 1
        canonical_root_bindings_resolved += 1
        kind_counts[reservation.kind.value] += 1
        candidate_widths[len(menu.bindings)] += 1
        available = sum(menu.candidate_available)
        availability_widths[available] += 1
        unavailable_reasons.update(
            reason.value
            for reason in menu.candidate_unavailable_reasons
            if reason is not None
        )
        if available >= 2:
            binding = snapshot.freeze_binding(
                menu,
                scenario_id=reservation.scenario_id,
            )
            RedPartyDevelopmentQuestionPreflight(
                reservation=reservation,
                source_root_lineage_id=source_root_lineage_id,
                snapshot=snapshot,
                menu=menu,
                binding=binding,
            )
            prospectively_validated += 1

        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path, profile_path)
        }
        if after != before:
            raise RedPartyDevelopmentPreflightRunError(
                "reserved question inputs changed during read-only inspection"
            )

    if inspected + pending_preparation != len(plan.reservations):
        raise RedPartyDevelopmentPreflightRunError(
            "party preflight did not account for every reservation"
        )
    if {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in protected_files
    } != protected_files:
        raise RedPartyDevelopmentPreflightRunError(
            "reservation inputs changed during read-only inspection"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedPartyDevelopmentPreflightRunError(
            "read-only party preflight created a ROM-adjacent artifact"
        )

    return {
        "schema": "pokemon.red.party-development-question-preflight-summary.v1",
        "reservation_count": len(plan.reservations),
        "direct_questions_inspected": inspected,
        "canonical_root_bindings_resolved": canonical_root_bindings_resolved,
        "historical_context_catalog_sha256": context_catalog.catalog_sha256,
        "preparation_questions_pending": pending_preparation,
        "prospective_bindings_validated_in_memory": prospectively_validated,
        "kind_counts": dict(sorted(kind_counts.items())),
        "candidate_width_counts": {
            str(width): count for width, count in sorted(candidate_widths.items())
        },
        "available_width_counts": {
            str(width): count for width, count in sorted(availability_widths.items())
        },
        "unavailable_reason_counts": dict(sorted(unavailable_reasons.items())),
        "candidate_menus_durably_frozen": 0,
        "outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "authority_promoted": False,
        "candidate_feature_values_public": False,
        "private_binding_values_public": False,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error(
            "Red party-development preflight failed closed; private paths were withheld."
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
