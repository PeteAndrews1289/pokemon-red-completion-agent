#!/usr/bin/env python3
"""Run/recover the four frozen descriptive Red pairs with the saved fitted model.

Development uses clean published code, strict local input/runtime checks and
durable one-attempt arms. It does not wait for another exact-main CI cycle.
The frozen producer, old train reservations, model and four-root denominator
remain exact. This command has no fitting or full-game execution interface.
"""

# ruff: noqa: E402 -- establish the existing repository imports first.

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for directory in (PROJECT_ROOT / "scripts", PROJECT_ROOT / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import run_red_living_dex_targeted_bank_retirement_train as training_support
from run_product_focus_dashboard import _load_learning_evidence, _training_projection

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    read_root_pair_claim,
)
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.goal_manager_composition_qualification import (
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.living_dex_goal_model_record import load_living_dex_goal_model_record
from pokemon_red_completion.living_dex_paired_development import private_failure_diagnostic
from pokemon_red_completion.living_dex_policy_development_journal import _ensure_store_anchor
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionRuntimeLimits,
    RedLivingDexProductionSetupResolver,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_retired_bank_paired import (
    RedLivingDexRetiredPairedAssignment,
    retired_paired_campaign_summary,
    retired_paired_setup_claim,
    run_red_living_dex_retired_paired_assignment,
)
from pokemon_red_completion.red_living_dex_setup_identity import (
    compose_red_living_dex_setup_execution_identity,
)
from pokemon_red_completion.red_living_dex_setup_recipe import RedLivingDexAuthenticatedSetupRoot
from pokemon_red_completion.red_living_dex_setup_trust import RedLivingDexSetupEffectMeter
from pokemon_red_completion.red_living_dex_targeted_bank_retirement_reader import (
    authenticate_red_living_dex_targeted_bank_retirement_plan,
    load_red_living_dex_targeted_bank_retirement_descriptor,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_replay import (
    rebind_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "expected-source-commit",
        "expected-source-bundle-sha256",
        "training-source-commit",
        "expected-schedule-sha256",
        "producer-source-commit",
        "producer-source-bundle-sha256",
        "expected-context-catalog-sha256",
        "expected-context-plan-sha256",
        "registry-source-commit",
        "expected-registry-sha256",
        "expected-model-sha256",
        "expected-model-record-sha256",
        "expected-route-registry-sha256",
        "expected-runtime-identity-sha256",
        "fitted-model-sha256",
        "fitted-record-sha256",
    ):
        parser.add_argument("--" + option, required=True)
    for option in (
        "schedule",
        "context-catalog",
        "context-plan",
        "private-root",
        "rom",
        "fitted-model",
    ):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


class _LiveView:
    """Passive spectator feed; mechanics and both policies never consult it."""

    def __init__(self, model_sha256: str, meter: RedLivingDexSetupEffectMeter) -> None:
        training, component = _training_projection(_load_learning_evidence())
        if component.model_sha256 != model_sha256:
            raise ValueError("live evidence belongs to another fitted model")
        self.snapshot = DashboardSnapshot(
            game="Pokémon Red",
            run_status="running",
            stage="Routed model-play comparison",
            message=(
                "Preparing four frozen Red scenarios. Setup is deterministic; model choices follow."
            ),
            collection_observed=False,
            collection_target=151,
            training=training,
            learning_components=(component,),
            model=DashboardModelState(
                mode="waiting", candidate="Living-Dex option scorer · 29 examples"
            ),
            experiment=DashboardExperimentState(
                phase="live_evaluation",
                zero_shot_total=4,
                adaptation_total=8,
                sealed_total=0,
                heading="Bounded Red play",
                eyebrow="Descriptive model versus control",
                counter_labels=("Scenarios terminal", "Arms terminal", "Sealed cases"),
            ),
            events=("This is bounded development, not a full-game run or model fitting.",),
        )
        self.state = DashboardState(self.snapshot)
        self._frame_sink = DashboardFrameObserver(self.state, maximum_fps=12)
        self.frame_observer = self
        self.viewer_failures = 0
        self.frames_disabled = False
        self.meter = meter
        self.kinds: tuple[str, ...] = ()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._publish, daemon=True)

    def wants_frame(self, logical_frame: int) -> bool:
        if self.frames_disabled:
            return False
        try:
            return self._frame_sink.wants_frame(logical_frame)
        except Exception:
            self.frames_disabled = True
            self.viewer_failures += 1
            return False

    def publish_frame(self, width: int, height: int, rgb: bytes, logical_frame: int) -> None:
        if self.frames_disabled:
            return
        try:
            self._frame_sink.publish_frame(width, height, rgb, logical_frame)
        except Exception:
            self.frames_disabled = True
            self.viewer_failures += 1

    def _publish(self) -> None:
        while not self.stop.wait(0.5):
            with self.lock:
                self.state.publish(
                    replace(
                        self.snapshot,
                        actions=self.meter.controller_actions,
                        frame_count=self.meter.emulator_frames,
                    )
                )

    def event(self, stage: str, document: Mapping[str, object]) -> None:
        try:
            self._event(stage, document)
        except Exception:
            self.viewer_failures += 1

    def _event(self, stage: str, document: Mapping[str, object]) -> None:
        with self.lock:
            message = stage.replace("_", " ")
            model = self.snapshot.model
            heading = self.snapshot.stage
            experiment = self.snapshot.experiment
            observed = None
            if stage == "choices_committed":
                message = (
                    "Both model and control choices are durably committed before either outcome."
                )
                self.kinds = tuple(
                    item["kind"] for item in document["control_question"]["candidates"]
                )
                observed = document["origin_observation"]
                experiment = replace(experiment, predictions_committed=True)
            if stage == "arm_started":
                actor = str(document["actor"])
                heading = "Model-selected goal" if actor == "model" else "Deterministic control"
                message = f"Executing {actor} choice from the identical conditioned origin."
                index = int(document["selected_candidate_index"])
                model = replace(
                    model,
                    mode="model" if actor == "model" else "teacher",
                    choice=self.kinds[index].replace("_", " "),
                    decisions=model.decisions + int(actor == "model"),
                )
            if stage == "arm_terminal":
                message = (
                    f"{document['actor']} arm finished: {document['status']}. Outcome retained."
                )
                experiment = replace(
                    experiment, adaptation_completed=experiment.adaptation_completed + 1
                )
                provenance = document.get("observation")
                if isinstance(provenance, Mapping):
                    observed = provenance.get("after_observation")
            snapshot = self.snapshot
            if isinstance(observed, Mapping) and isinstance(observed.get("collection"), Mapping):
                counts = observed["collection"]
                # Authentic collection counts may have different declared living
                # and registered targets. The viewer uses the larger target and
                # rejects inconsistent observed counts instead of silently fixing them.
                snapshot = replace(
                    snapshot,
                    collection_observed=True,
                    registered_species=counts["registered"],
                    living_species=counts["living"],
                    level_cap_species=counts["level_cap"],
                    collection_target=max(counts["registered_target"], counts["living_target"]),
                    capture_items=observed["capture_item_count"],
                    free_storage_slots=observed["free_storage_slots"],
                )
            self.snapshot = replace(
                snapshot,
                stage=heading,
                experiment=experiment,
                message=message,
                model=model,
                events=(*self.snapshot.events[-7:], message),
            )


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        if not 1024 <= args.port <= 65535:
            raise ValueError("dashboard port differs")
        stage = "clean_published_source"
        source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
        require_clean_source(source)
        require_published_source(PROJECT_ROOT, source)
        bundle = working_source_bundle_sha256(PROJECT_ROOT)
        if (
            source.git_commit != args.expected_source_commit
            or bundle != args.expected_source_bundle_sha256
        ):
            raise ValueError("paired executable source differs")
        stage = "schedule_envelope_authentication"
        payload = training_support.base._read_schedule(args.schedule)
        expectations = training_support._expectations(args)
        descriptor = load_red_living_dex_targeted_bank_retirement_descriptor(
            payload,
            expected_plan_sha256=args.expected_schedule_sha256,
            expectations=expectations,
        )
        stage = "fitted_model_authentication"
        model_record = load_living_dex_goal_model_record(
            args.fitted_model, expected_model_sha256=args.fitted_model_sha256
        )
        if model_record.file_sha256 != args.fitted_record_sha256:
            raise ValueError("paired fitted model record differs")
        stage = "private_input_authentication"
        rom_path, _, rom_bytes, contexts, _, _ = training_support.base._authenticate_inputs(args)
        runtime = build_runtime_identity()
        require_pyboy_import_origins(runtime)
        if runtime.sha256 != args.expected_runtime_identity_sha256:
            raise ValueError("paired runtime differs")
        routes = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
        if routes.registry_sha256 != args.expected_route_registry_sha256:
            raise ValueError("paired route registry differs")
        identity = compose_red_living_dex_setup_execution_identity(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=bundle,
            route_registry_sha256=routes.registry_sha256,
            runtime_identity=runtime,
        )
        store = open_private_root(
            args.private_root, repository_root=PROJECT_ROOT, allow_same_device=True
        )
        registry = open_fixed_account_claim_registry()
        # Do not create an anchor in an action-free preflight. Existing anchors
        # authenticate only this store's exact claims during command recovery.
        anchor_record = store.find_sealed_record(
            "living-dex-policy-development-store-anchor-v1",
            expected_kind="living_dex_policy_development_store_anchor",
        )
        anchor = None if anchor_record is None else _ensure_store_anchor(store)

        def owned_claim(root: RedLivingDexAuthenticatedSetupRoot, lineage: str) -> bool:
            if anchor is None:
                return False
            slots = [
                slot
                for slot in descriptor.schedule_descriptor.schedule.slots
                if slot.partition == "development"
                and slot.lineage_sha256 == lineage
                and slot.physical_root_sha256 == root.physical_root_sha256
            ]
            if len(slots) != 1:
                return False
            expected = retired_paired_setup_claim(
                root,
                identity,
                model_sha256=args.fitted_model_sha256,
                store_anchor_sha256=anchor,
                schedule_binding_sha256=descriptor.schedule_descriptor.binding_sha256,
                schedule_sha256=descriptor.schedule_descriptor.schedule.schedule_sha256,
                slot_sha256=slots[0].slot_sha256,
            )
            try:
                return read_root_pair_claim(registry, expected.claim_sha256) == expected
            except ClaimFirstAdmissionError:
                return False

        stage = "action_free_schedule_replay"
        observed = training_support._observe_retired_roots(
            descriptor,
            contexts,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
            claim_registry=registry,
            source_commit=args.training_source_commit,
            owned_development_claim=owned_claim,
        )
        world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
        replay_meter = RedLivingDexSetupEffectMeter()
        capabilities = enumerate_red_living_dex_causal_capabilities(
            observed,
            world=world,
            corridors=derive_red_living_dex_provider_corridors(world),
            effects_before=replay_meter.checkpoint(),
            effects_after=replay_meter.checkpoint(),
        )
        binding = authenticate_red_living_dex_targeted_bank_retirement_plan(
            payload,
            expected_plan_sha256=args.expected_schedule_sha256,
            expectations=expectations,
            freshly_derived_binding=rebind_red_living_dex_targeted_schedule(
                descriptor.schedule_descriptor, capabilities
            ),
        )
        if args.preflight_only:
            print(
                json.dumps(
                    {
                        "status": "paired_preflight_passed",
                        "paired_roots": 4,
                        "model_examples": model_record.model.settled_examples,
                        "controller_actions": 0,
                        "model_predictions": 0,
                        "root_claims_created": 0,
                        "model_fits": 0,
                        "private_path_fields": 0,
                    }
                ),
                flush=True,
            )
            return 0
        stage = "four_paired_development_roots"
        meter = RedLivingDexSetupEffectMeter()
        view = _LiveView(args.fitted_model_sha256, meter)
        resolver = RedLivingDexProductionSetupResolver(
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            producer_execution_identity=identity,
            runtime_limits=RedLivingDexProductionRuntimeLimits(
                maximum_controller_actions=200_000,
                maximum_emulator_frames=20_000_000,
            ),
            frame_observer=view.frame_observer,
        )
        receipts = []
        with ProgressDashboardServer(view.state, port=args.port):
            view.thread.start()
            try:
                for ordinal in (8, 9, 10, 11):
                    with view.lock:
                        view.snapshot = replace(
                            view.snapshot,
                            stage=f"Red scenario {ordinal - 7} of 4 · setup",
                            message=(
                                "Constructing and checking the declared routed menu. "
                                "No model action yet for this pair."
                            ),
                            model=replace(view.snapshot.model, mode="waiting", choice=None),
                            collection_observed=False,
                            experiment=replace(
                                view.snapshot.experiment, predictions_committed=False
                            ),
                        )
                    result = run_red_living_dex_retired_paired_assignment(
                        RedLivingDexRetiredPairedAssignment(binding, ordinal),
                        model_record.model,
                        expected_model_sha256=args.fitted_model_sha256,
                        store=store,
                        claim_registry=registry,
                        setup_execution_identity=identity,
                        resolver=resolver,
                        meter=meter,
                        observer=view.event,
                    )
                    receipts.append(result)
                    print(json.dumps(result.public_dict(), sort_keys=True), flush=True)
                    with view.lock:
                        view.snapshot = replace(
                            view.snapshot,
                            stage_progress=len(receipts) / 4,
                            experiment=replace(
                                view.snapshot.experiment, zero_shot_completed=len(receipts)
                            ),
                        )
            finally:
                view.stop.set()
                view.thread.join(timeout=2)
        summary = retired_paired_campaign_summary(tuple(receipts))
        summary.update(
            {
                "source_commit": source.git_commit,
                "source_bundle_sha256": bundle,
                "controller_actions": meter.controller_actions,
                "emulator_frames": meter.emulator_frames,
                "viewer_failures": view.viewer_failures,
            }
        )
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed_closed",
                    "stage": stage,
                    "diagnostic": private_failure_diagnostic(error),
                    "model_fits": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
