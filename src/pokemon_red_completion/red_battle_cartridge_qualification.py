"""One integrated, disposable Red battle qualification, not learned play.

The caller supplies an authenticated observation and frozen assignment; the
materializer re-authenticates the source inside the claimed journal. No default
ROM paths, source discovery, campaign retry, fitting, or checkpoint promotion.
"""

from __future__ import annotations

import hashlib
from typing import cast

from pokemon_red_completion.battle_runtime import run_adaptive_wild_battle
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cartridge_qualification import (
    QualificationCampaign,
    QualificationError,
    QualificationJournal,
    QualificationLimits,
    run_qualification_case,
)
from pokemon_red_completion.gen1_route_runtime import strongest_usable_move_slot
from pokemon_red_completion.observation import PokemonRedStateReader, RawGameState, ReadOnlyMemory
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.red_repeatable_battle_scenario_runtime import (
    RepeatableRedBattleScenarioSessionFactory,
    materialize_repeatable_red_battle_scenario,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattleScenarioAssignment,
    RepeatableBattleScenarioKind,
    RepeatableBattleSourceObservation,
)


def qualify_repeatable_red_wild_battle(
    store: PrivateArtifactRoot,
    episode_id: str,
    source: RepeatableBattleSourceObservation,
    assignment: RepeatableBattleScenarioAssignment,
    state_bytes: bytes,
    *,
    rom_bytes: bytes,
    materializer_source_commit: str,
    session_factory: RepeatableRedBattleScenarioSessionFactory,
    limits: QualificationLimits,
    campaign: QualificationCampaign,
    maximum_encounter_steps: int = 512,
) -> dict[str, object]:
    """Measure setup and shared-runtime battle across separate emulator sessions."""

    def execute(journal: QualificationJournal) -> dict[str, object]:
        if assignment.scenario_kind is not RepeatableBattleScenarioKind.WILD:
            raise ValueError("qualification requires a wild assignment")
        materialized = materialize_repeatable_red_battle_scenario(
            source,
            assignment,
            state_bytes,
            rom_bytes=rom_bytes,
            materializer_source_commit=materializer_source_commit,
            session_factory=session_factory,
            maximum_encounter_steps=maximum_encounter_steps,
            executor_factory=journal.executor,
            phase_observer=journal.enter_phase,
        )
        journal.enter_phase("battle")
        selections = 0

        def fixed_policy(raw: RawGameState) -> int:
            nonlocal selections
            slot = strongest_usable_move_slot(raw)
            journal.append(
                "selections",
                {
                    "slot": slot,
                    "active_party_index": raw.active_party_index,
                    "moves": list(raw.battler_moves or ()),
                    "pp_before": list(raw.battler_pp or ()),
                    "status_before": raw.battler_status,
                    "enemy_hp_before": raw.enemy_hp,
                },
            )
            selections += 1
            return slot

        with session_factory() as session:
            session.load_state_bytes(materialized.state_bytes)
            reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
            executor = journal.executor(session, DEFAULT_NEW_GAME_TIMING.controller_timing())
            final = run_adaptive_wild_battle(
                reader,
                executor,
                fixed_policy,
                expected_map=materialized.expected_map,
                label="disposable cartridge qualification",
            )
            journal.enter_phase("terminal")
            readiness = reader.read_input_readiness()
            if final.battle_state != 0 or not readiness.ready or not selections:
                raise QualificationError("unsettled_terminal")
        return {"status": "settled_wild_battle", "selections": selections}

    return run_qualification_case(
        store,
        episode_id,
        {
            "scenario_id": assignment.scenario_id,
            "source_id": assignment.source_id,
            "source_lineage_id": assignment.source_lineage_id,
            "partition": assignment.partition.value,
            "source_state_sha256": assignment.source_state_sha256,
            "source_commit": assignment.source_commit,
            "materializer_source_commit": materializer_source_commit,
            "rom_sha256": hashlib.sha256(rom_bytes).hexdigest(),
            "party_index": assignment.party_index,
            "venue_id": assignment.venue_id,
            "pre_encounter_wait_frames": assignment.pre_encounter_wait_frames,
            "menu_semantic_sha256": assignment.menu_semantic_sha256,
            "maximum_encounter_steps": maximum_encounter_steps,
            "policy": "fixed_strongest_usable_move",
            "correlated_development_only": True,
        },
        limits=limits,
        campaign=campaign,
        execute=execute,
    )
