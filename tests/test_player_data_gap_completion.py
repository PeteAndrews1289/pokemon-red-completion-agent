"""ROM-free coverage and parity for the existing player journals.

No cartridge, native source, training fit or campaign is opened by these tests.
"""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_acquisition import _RouteOneSurveySimulation
from test_red_autonomous_player import _environment
from test_red_fishing_capture import _offer, _Port
from test_red_live_option_menu import _model
from test_red_one_off_capture import Sim
from test_red_player_lesson_runtime import fixture
from test_red_safari_acquisition import _live, _SafariSimulation
from test_routed_semantic_goal import _composer
from test_surge import _raw

import pokemon_red_completion.red_autonomous_player as autonomous
import pokemon_red_completion.surge as surge
from pokemon_red_completion.capture_survey import survey_operation_diagnostics
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.fishing import FishingCastOutcome
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import run_red_area_survey
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_fishing_capture import run_red_fishing_capture
from pokemon_red_completion.red_goal_context import _wild_search_diagnostic_observer
from pokemon_red_completion.red_player_lesson_runtime import (
    collection_dependency_diagnostics,
    player_diagnostic_state,
    player_outcome_diagnostics,
    player_resource_attribution,
    player_stop_diagnostics,
    record_native_player_lesson,
    summarize_player_diagnostic_events,
)
from pokemon_red_completion.red_trainer_practice_episode import battle_failure_diagnostics


def test_collection_credit_does_not_replace_a_consumable_physical_precursor():
    checkpoint = NS(
        completion_scope="local_red",
        local_species=("a",),
        global_species=("a", "b"),
        credited_species=("a",),
        target_species=("a", "b"),
        specimen_counts=(("a", 1),),
        protected_counts=(("a", 1),),
        allowed_evolutions=(("a", "b"),),
    )
    row = collection_dependency_diagnostics(checkpoint)
    assert row["missing_registrations"] == ["b"]
    edge = row["potential_consuming_dependencies"][0]
    assert edge["physical_stock"] == edge["protected_stock"] == 1
    assert edge["unprotected_stock"] == 0 and edge["physical_reacquisition_needed"]
    assert row["dependencies_are_alternatives_not_legal_offers"]
    assert collection_dependency_diagnostics(None) is None


def test_physical_context_ignores_unrelated_registration_but_not_stock_or_repel():
    obs = NS(
        raw=NS(map_id=13, repel_remaining_steps=4, party_levels=(30,), bag_items=((4, 9),)),
        collection_observation=NS(owned_species=frozenset({"a"}), specimens=(NS(species_ref="a"),)),
    )
    original = player_diagnostic_state(obs)
    obs.collection_observation.owned_species |= {"unrelated"}
    obs.raw.repel_remaining_steps = 3
    assert (
        player_diagnostic_state(obs)["physical_search_context_sha256"]
        == original["physical_search_context_sha256"]
    )
    obs.raw.repel_remaining_steps = 0
    assert (
        player_diagnostic_state(obs)["physical_search_context_sha256"]
        != original["physical_search_context_sha256"]
    )
    obs.raw.repel_remaining_steps = 4
    obs.collection_observation.specimens += (NS(species_ref="a"),)
    assert (
        player_diagnostic_state(obs)["physical_search_context_sha256"]
        != original["physical_search_context_sha256"]
    )
    assert original["specimen_counts"] == {"a": 1}


def _outcome(delta=-200, *, evidence=None, verified="succeeded", kind=GoalKind.RESUPPLY.value):
    return dict(
        diagnostic_delta=dict(player_money=delta),
        evidence=evidence,
        verification=verified,
        selected_kind=kind,
    )


@pytest.mark.parametrize("delta", [-200, 0, 500, None])
def test_cash_endpoint_or_prospective_quote_never_invents_a_resource_cause(delta):
    row = player_resource_attribution(_outcome(delta))
    assert row["supported_receipts"] == [] and not row["gross_spending_known"]
    assert row["unexplained_net_cash_change"] == delta


@pytest.mark.parametrize("verified,expected", [("succeeded", 2), ("failed", 0), (None, 0)])
def test_known_purchase_and_sale_receipt_attribution_requires_verification(verified, expected):
    row = player_resource_attribution(
        _outcome(
            -150,
            evidence=dict(money_spent=200, sale_proceeds=50),
            verified=verified,
        )
    )
    assert len(row["supported_receipts"]) == expected
    assert row["unexplained_net_cash_change"] == (0 if expected else -150)


def test_native_trainer_income_components_and_blackout_are_explicit_not_guessed():
    funding = dict(
        initial_money=10, final_money=110, payout=100, ordinary_victory_money=70, pay_day_money=30
    )
    row = player_resource_attribution(
        _outcome(
            100,
            evidence=dict(trainer_funding=funding),
            kind="advance_story",
        )
    )
    assert row["supported_receipts"][0]["kind"] == "trainer_income"
    funding["payout"] = 200
    assert not player_resource_attribution(
        _outcome(
            100,
            evidence=dict(trainer_funding=funding),
            kind="advance_story",
        )
    )["supported_receipts"]
    blackout = dict(blackout_verified=True, cash_before=101, cash_after=50, cash_lost=51)
    row = player_resource_attribution(
        _outcome(
            -51,
            evidence=dict(native_blackout_during_selected_restoration=blackout),
            verified="failed",
            kind="restore_team",
        )
    )
    assert row["supported_receipts"][0]["kind"] == "blackout_loss"
    assert row["unexplained_net_cash_change"] == 0
    blackout["cash_after"] = 70
    assert not player_resource_attribution(
        _outcome(
            -31,
            evidence=dict(native_blackout_during_selected_restoration=blackout),
        )
    )["supported_receipts"]


def test_league_income_does_not_double_count_nested_battles_or_guess_mixed_debits():
    receipt = dict(
        schema="pokemon.red.repeatable-league-funding-execution.v2",
        observed_gross_income=1000,
        sale_proceeds=0,
        purchase_cost=200,
        starting_money=500,
        ending_money=1300,
        battles=[dict(payout=1000)],
    )
    row = player_resource_attribution(
        _outcome(750, evidence=dict(outcome=receipt), kind="resupply")
    )
    assert len(row["supported_receipts"]) == 3
    assert row["explained_net_cash_change"] == 800
    assert row["unexplained_net_cash_change"] == -50


@pytest.mark.parametrize("nested", [False, True])
def test_routed_evolution_preserves_cost_receipt_without_private_identity_or_controller_changes(
    nested,
):
    receipt = dict(
        procurement_executed=True,
        money_spent=2100,
        completed_training_battles=4,
        healing_trips=1,
        private_source="must-not-be-copied",
    )
    if nested:
        receipt = dict(execution_diagnostics=dict(diagnostic_only=True, **receipt))
    _, binding, meter, events = _composer(
        evolution_evidence=receipt,
        destination_kind=GoalKind.EVOLVE_SPECIES,
        offered_kind=GoalKind.EVOLVE_SPECIES,
    )
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert (meter.actions, meter.frames) == (5, 50)
    assert events == [
        "route_execute",
        "route_verify",
        "fresh_bind",
        "destination_execute",
        "destination_verify",
    ]
    diagnostic = report.evidence["execution_diagnostics"]
    assert diagnostic["money_spent"] == 2100
    assert "private_source" not in diagnostic
    row = player_outcome_diagnostics(
        _outcome(-2100, evidence=report.evidence, kind="evolve_species")
    )
    assert row["resource_attribution"]["supported_receipts"][0]["kind"] == "purchases"
    assert row["resource_attribution"]["unexplained_net_cash_change"] == 0
    assert row["preparation_efficiency"]["reported_training_battles"] == 4
    assert row["preparation_efficiency"]["reported_healing_trips"] == 1


def test_paid_admission_and_coin_procurement_are_not_renamed_item_purchases():
    row = player_resource_attribution(
        _outcome(
            -500,
            kind="acquire_species",
            evidence=dict(
                admission=dict(status="ok", single_admission=True, admission_fee_paid=500)
            ),
        )
    )
    assert row["supported_receipts"][0]["kind"] == "admission_fee"
    assert row["unexplained_net_cash_change"] == 0 and not row["gross_spending_known"]
    row = player_resource_attribution(
        _outcome(
            -1000,
            evidence=dict(
                mechanic="game_corner_coin_procurement",
                cash_debit=1000,
            ),
        )
    )
    assert row["supported_receipts"][0]["kind"] == "coin_procurement"
    assert row["unexplained_net_cash_change"] == 0


def test_unknown_receipt_mechanic_is_not_a_currency_cause_or_a_logging_failure():
    row = player_resource_attribution(
        _outcome(-1000, evidence=dict(mechanic={"unknown": True}, cash_debit=1000))
    )
    assert row["supported_receipts"] == []
    assert row["unexplained_net_cash_change"] == -1000


@pytest.mark.parametrize("verified", ["succeeded", "failed", None])
def test_paid_safari_receipt_survives_failed_or_censored_capture(verified):
    evidence = dict(
        admission=dict(status="ok", single_admission=True, admission_fee_paid=500),
        captures=0,
        failed_capture_attempts=1,
        paid_session_departure=dict(passed=True, resource_renewals=0),
    )
    original = copy.deepcopy(evidence)
    row = player_resource_attribution(
        _outcome(-500, evidence=evidence, verified=verified, kind="acquire_species")
    )
    assert evidence == original
    assert row["supported_receipts"] == [dict(
        kind="admission_fee", amount=500,
        evidence_path="evidence.admission.admission_fee_paid",
    )]
    assert row["explained_net_cash_change"] == -500
    assert row["unexplained_net_cash_change"] == 0
    assert not row["gross_spending_known"]


@pytest.mark.parametrize("receipt", [
    {},
    dict(status="failed", single_admission=True, admission_fee_paid=500),
    dict(status="ok", single_admission=False, admission_fee_paid=500),
    dict(status="ok", single_admission=True, admission_fee_paid=None),
    dict(status="ok", single_admission=True, admission_fee_paid=True),
    dict(status="ok", single_admission=True, admission_fee_paid=-500),
    dict(status="ok", single_admission=True, admission_fee_paid="500"),
])
def test_failed_search_debit_cannot_supply_a_missing_or_bad_admission(receipt):
    row = player_resource_attribution(
        _outcome(-500, evidence=dict(admission=receipt), verified="failed", kind="acquire_species")
    )
    assert row["supported_receipts"] == []
    assert row["unexplained_net_cash_change"] == -500


def test_explicit_zero_admission_and_unknown_cash_remain_separate():
    receipt = dict(status="ok", single_admission=True, admission_fee_paid=0)
    row = player_resource_attribution(
        _outcome(None, evidence=dict(admission=receipt), verified=None, kind="acquire_species")
    )
    assert row["supported_receipts"][0]["amount"] == 0
    assert row["observed_net_cash_change"] is None
    assert row["unexplained_net_cash_change"] is None


def test_listed_pre_entry_purchases_reconcile_without_duplicate_league_battles():
    funding = dict(
        schema="pokemon.red.repeatable-league-funding-execution.v2",
        observed_gross_income=29799, sale_proceeds=0, purchase_cost=0,
        starting_money=190774, ending_money=220573,
        battles=[dict(trainer_funding=dict(
            initial_money=190774, final_money=196318, payout=5544,
            ordinary_victory_money=5544, pay_day_money=0,
        ))],
    )
    row = player_resource_attribution(_outcome(
        20799,
        evidence=dict(
            pre_entry_support=[
                dict(evidence=dict(money_spent=6000)),
                dict(evidence=dict(money_spent=3000)),
            ],
            league_funding=funding,
        ),
    ))
    assert sum(r["amount"] for r in row["supported_receipts"]
               if r["kind"] == "purchases") == 9000
    assert sum(r["amount"] for r in row["supported_receipts"]
               if r["kind"] == "trainer_income") == 29799
    assert row["explained_net_cash_change"] == 20799
    assert row["unexplained_net_cash_change"] == 0


@pytest.mark.parametrize("verified", ["succeeded", "failed", None])
def test_listed_safari_fee_still_requires_its_own_valid_receipt(verified):
    row = player_resource_attribution(_outcome(
        -500, verified=verified, kind="acquire_species",
        evidence=dict(attempts=[
            dict(admission=dict(status="ok", single_admission=True, admission_fee_paid=500)),
            dict(admission=dict(status="failed", single_admission=True, admission_fee_paid=500)),
            "no receipt", None,
        ]),
    ))
    assert row["supported_receipts"] == [dict(
        kind="admission_fee", amount=500,
        evidence_path="evidence.attempts[0].admission.admission_fee_paid",
    )]
    assert row["unexplained_net_cash_change"] == 0


def test_prediction_native_units_and_individual_xp_are_separate_and_no_row_is_admitted():
    member = dict(specimen_ref="private-member", experience=10, level=5)
    before = dict(player_lesson=dict(party=[member]))
    after = dict(player_lesson=dict(party=[dict(member, experience=30, level=6)]))
    outcome = dict(
        _outcome(),
        before=before,
        after=after,
        choice=dict(selected_candidate_index=1),
        phase_seconds=dict(execution=2),
        measured_cost=dict(actions=9, frames=900, cash_spent=200),
    )
    diagnostics = dict(
        candidates=[
            dict(
                candidate_index=1,
                raw_predictions=dict(verified_success=3, action_cost=2),
                bounded_predictions=dict(verified_success=1, action_cost=1),
            )
        ]
    )
    originals = copy.deepcopy((outcome, diagnostics))
    row = player_outcome_diagnostics(
        outcome, resource_quote=dict(purchase_cost=200), selection_diagnostics=diagnostics
    )
    assert (outcome, diagnostics) == originals
    assert row["preparation_efficiency"]["retained_members"][0]["xp_per_execution_second"] == 10
    assert row["preparation_efficiency"]["battle_count"] is None
    assert row["preparation_efficiency"]["retained_members"][0]["combat_participation"] is None
    assert row["prediction_comparison"]["raw_predictions"]["verified_success"] == 3
    assert row["prediction_comparison"]["verified_success_residual"] == 0
    assert row["prediction_comparison"]["normalized_prediction_costs_are_not_native_units"]
    assert not row["training_admission"]


@pytest.mark.parametrize(
    "reason,category",
    [
        ("decision_budget", "allocation_limit"),
        ("wall_time_budget", "allocation_limit"),
        ("curriculum_complete", "objective_complete"),
        ("menu_unavailable", "missing_executable_option"),
        ("unsafe_terminal", "unclassified_requires_evidence"),
    ],
)
def test_stop_categories_never_authorize_inputs_or_resume(reason, category):
    row = player_stop_diagnostics(reason)
    assert row["category"] == category
    assert not row["resume_authorized"] and not row["additional_inputs_authorized"]


def test_native_action_counts_are_not_search_exposure_or_encounter_probability():
    row = survey_operation_diagnostics(
        dict(native_actions=10, native_frames=100, repel_remaining_steps=2),
        dict(
            native_actions=14,
            native_frames=900,
            repel_remaining_steps=1,
            battle_state=0,
            enemy_species_id=75,
        ),
        operation="seek_encounter",
        elapsed_seconds=1,
    )
    assert row["measured"]["native_actions"] == 4
    assert row["measured"]["eligible_search_steps"] is None
    assert not row["search_eligibility_known"] and row["search_likelihood_not_inferred"]
    assert row["target_after"]["enemy_species_id"] is None  # Stale, outside battle.


@pytest.mark.parametrize("observed", [True, False, None])
def test_survey_observers_preserve_all_operation_results_and_control_calls(observed):
    first, second = _RouteOneSurveySimulation((16, 19)), _RouteOneSurveySimulation((16, 19))
    baseline = run_red_area_survey("wild:Route1:grass", first)
    events = []
    report = run_red_area_survey(
        "wild:Route1:grass",
        second,
        observe_diagnostics=lambda: dict(search_exposure=dict(eligible_search_steps=observed)),
        record_diagnostic_event=lambda kind, row: events.append((kind, row)),
    )
    assert (report.captures, report.flees, report.actions_executed, report.encounters_seen) == (
        baseline.captures,
        baseline.flees,
        baseline.actions_executed,
        baseline.encounters_seen,
    )
    assert first.read_collection() == second.read_collection()
    operation_rows = [r for k, r in events if k == "survey_action_returned"]
    assert operation_rows and all(
        not r["diagnostic_review"]["search_eligibility_known"] for r in operation_rows
    )  # bool is not a step count.


@pytest.mark.parametrize("capture", [True, False])
def test_one_off_throw_journal_does_not_add_input_or_change_ball_accounting(monkeypatch, capture):
    first = Sim(monkeypatch, capture=capture)

    def attempt(sim):
        try:
            return sim.run(throws=1)
        except Exception as error:
            return type(error).__name__

    baseline = attempt(first)
    second = Sim(monkeypatch, capture=capture)
    events = []
    second.record_diagnostic_event = lambda kind, row: events.append((kind, row))
    assert attempt(second) == baseline
    assert (
        first.spends,
        first.commands,
        first.bag,
        first.raw,
        first.executor.actions_executed,
    ) == (second.spends, second.commands, second.bag, second.raw, second.executor.actions_executed)
    assert [k for k, _ in events] == ["capture_throw_started", "capture_throw_completed"]
    conditions = events[0][1]["conditions"]
    assert conditions["target_hp"] == conditions["target_max_hp"] == 150
    assert conditions["target_hp_fraction"] == 1 and conditions["ball_quantity"] == 3
    assert conditions["critical_hit_observed"] is None
    assert events[1][1]["measured_cost"]["actions"] == second.executor.actions_executed


@pytest.mark.parametrize("persist_capture", [True, False])
def test_ordinary_throw_journal_preserves_success_and_nonretention(monkeypatch, persist_capture):
    def run(recording):
        runtime = NS(
            raw=replace(_raw(), battle_state=1),
            box_count=0,
            confirmations=0,
            bag={ItemId.POKE_BALL: 3},
            frame_count=0,
        )
        runtime.read = lambda: runtime.raw
        runtime.read_all_box_states = lambda: NS(counts=(runtime.box_count,) + (0,) * 11)
        events, trace = [], []
        executor = NS(actions_executed=0)
        if recording:
            executor.record_diagnostic_event = lambda kind, row: events.append((kind, row))

        def pulse(_ex, kind, *args, **kwargs):
            trace.append((kind, args, kwargs))
            executor.actions_executed += 1
            runtime.frame_count += 1
            if kind is surge.MacroActionKind.CONFIRM:
                runtime.confirmations += 1
                if runtime.confirmations == 2:
                    runtime.bag[ItemId.POKE_BALL] -= 1
                    runtime.raw = replace(runtime.raw, battle_state=0)
                    runtime.box_count += int(persist_capture)

        monkeypatch.setattr(surge, "_bag", lambda _: runtime.bag)
        monkeypatch.setattr(surge, "_navigate_main", lambda *args: None)
        monkeypatch.setattr(surge, "_select_bag_item", lambda *args: None)
        monkeypatch.setattr(surge, "_confirm_kind", lambda *args: None)
        monkeypatch.setattr(surge, "_pulse", pulse)
        caught = surge._try_catch_wild(runtime, executor, runtime, 0xA3, "parity", max_throws=5)
        return caught, trace, runtime.bag, events

    before, after = run(False), run(True)
    assert before[:3] == after[:3] and after[0] is persist_capture
    assert len(after[3]) == 2
    assert after[3][1][1]["conditions"]["target_fields_live"] is False
    assert after[3][1][1]["conditions"]["target_species_id"] is None


@pytest.mark.parametrize("capture", [True, False])
def test_fishing_journal_preserves_casts_flees_captures_and_private_public_split(capture):
    outcomes = [
        (FishingCastOutcome.NO_BITE, None),
        (FishingCastOutcome.WILD_ENCOUNTER, 129),
        (FishingCastOutcome.WILD_ENCOUNTER, 72),
    ]
    ports = [_Port(frozenset({129}), list(outcomes), capture_succeeds=capture) for _ in range(2)]
    baseline = run_red_fishing_capture(_offer(), ports[0], maximum_casts=3)
    events = []
    report = run_red_fishing_capture(
        _offer(),
        ports[1],
        maximum_casts=3,
        record_diagnostic_event=lambda kind, row: events.append((kind, row)),
        observe_diagnostics=lambda: dict(repel_remaining_steps=0),
    )
    assert report == baseline and ports[0] == ports[1]
    assert report.public_dict()["private_species_fields"] == 0
    casts = [r for k, r in events if k == "fishing_cast_observed"]
    assert len(casts) == 3 and [r["selected_target_seen"] for r in casts] == [False, False, True]
    assert casts[0]["cartridge_slots"] and casts[0]["state"]["repel_remaining_steps"] == 0


@pytest.mark.parametrize("known", [True, False])
def test_corridor_exposure_counts_only_search_movement_and_known_tiles(monkeypatch, known):
    traces = []
    reader = NS(raw=replace(_raw(), battle_state=0, player_x=10, player_y=20))
    reader.read = lambda: reader.raw

    def step(_ex, _reader, direction, *_args):
        traces.append(direction)
        reader.raw = replace(
            reader.raw, player_y=reader.raw.player_y + (1 if direction == "down" else -1)
        )
        return reader.raw

    monkeypatch.setattr(surge, "_survey_step", step)
    area = surge.LiveWildCorridorSurveyExecutor(
        NS(frame_count=0),
        CountingExecutor(NS()),
        reader,
        surge.DEFAULT_SURGE_TIMING,
        label="diagnostic corridor",
        forward_directions=("up",),
        starting_endpoint="south",
        max_legs=8,
        observe_search_conditions=(
            (lambda raw: dict(eligible_encounter_tile=True)) if known else None
        ),
    )
    area.seek_encounter()
    area.finish_at_starting_endpoint()
    row = area.search_diagnostics()
    assert traces == ["up", "down"]
    assert row["search_requests"] == row["movement_steps"] == 1
    assert row["eligible_search_steps"] == (1 if known else None)
    assert row["normalization_steps_excluded"]


def test_absent_cartridge_world_is_an_explicit_search_coverage_gap():
    row = _wild_search_diagnostic_observer(NS())(_raw())
    assert row["eligible_encounter_tile"] is None
    assert row["cartridge_table"] is None and row["coverage_gap"] == "no_cartridge_terrain_world"


def test_search_tile_diagnostic_reuses_live_blocks_and_cartridge_slots_without_inputs(monkeypatch):
    import pokemon_red_completion.gen1_cartridge as cartridge
    import pokemon_red_completion.gen1_terrain as terrain

    current = NS(blocks=NS(map_id=13, rows=((0,),)))
    decoded = []

    def decode(_rom, _map, rows, _sets, **kwargs):
        decoded.append(rows)
        return NS(
            width=2,
            height=2,
            tileset=0,
            grass=((False, rows[0][0] == 0), (False, False)),
            water=((False, False), (False, False)),
        )

    monkeypatch.setattr(terrain, "terrain_from_blocks", decode)
    monkeypatch.setattr(
        cartridge,
        "wild_encounter_tables",
        lambda _rom: {
            13: (cartridge.WildEncounterTable("grass", 25, ((5, 16), (6, 19))),),
        },
    )
    runtime = NS(
        reader=NS(
            read_current_map_blocks=lambda: current.blocks, read_overworld_movement_mode=lambda: 0
        ),
        trainer_story_world=NS(rom=b"fixture", tilesets={}, water_tilesets=frozenset()),
    )
    observe = _wild_search_diagnostic_observer(runtime)
    raw = replace(_raw(), map_id=13, player_x=1, player_y=0)
    row = observe(raw)
    assert row["eligible_encounter_tile"] is True
    assert row["cartridge_table"]["rate_byte"] == 25
    assert row["cartridge_table"]["ordered_slots"][1] == dict(slot=1, level=6, internal_species=19)
    assert row["actual_engine_encounter_checks"] is None
    observe(raw)
    assert len(decoded) == 1
    current.blocks = NS(map_id=13, rows=((1,),))
    assert observe(raw)["eligible_encounter_tile"] is False
    assert len(decoded) == 2  # An observed changed block must not reuse old grass.


@pytest.mark.parametrize("capture,flee", [(True, False), (False, False), (False, True)])
def test_safari_throw_journal_preserves_paid_balls_inputs_and_exact_retention(capture, flee):
    first = _SafariSimulation(capture_on_throw=capture, flee_on_throw=flee)
    second = _SafariSimulation(capture_on_throw=capture, flee_on_throw=flee)
    events = []
    second.record_diagnostic_event = lambda kind, row: events.append((kind, row))
    assert _live(first).capture_encounter(red_species_ref(30)) == _live(second).capture_encounter(
        red_species_ref(30)
    )
    assert (first.actions, first.balls, first.raw, first.collection) == (
        second.actions,
        second.balls,
        second.raw,
        second.collection,
    )
    assert [k for k, _ in events] == [
        "capture_throw_started",
        "capture_throw_completed",
        "safari_capture_retention_verified",
    ]
    assert events[0][1]["source"] == "safari"
    assert events[0][1]["conditions"]["ball_quantity"] == 3
    assert events[-1][1]["retained"] is capture


def test_journal_coverage_does_not_turn_unknown_search_checks_into_zero_or_probability():
    def event(kind, payload):
        return dict(kind=kind, payload=payload)

    events = [
        event("capture_throw_started", {}),
        event("capture_throw_started", {}),
        event(
            "capture_throw_completed",
            dict(source="ordinary_wild", outcome="specimen_retained", conditions=dict(ball_id=4)),
        ),
        event(
            "survey_action_returned",
            dict(
                operation="seek_encounter",
                diagnostic_review=dict(measured=dict(eligible_search_steps=2)),
            ),
        ),
        event(
            "survey_action_failed",
            dict(
                operation="seek_encounter",
                diagnostic_review=dict(measured=dict(eligible_search_steps=None)),
            ),
        ),
        event("fishing_cast_observed", dict(outcome="no_bite", selected_target_seen=False)),
        event("fishing_cast_observed", dict(outcome="wild_encounter", selected_target_seen=True)),
    ]
    original = copy.deepcopy(events)
    row = summarize_player_diagnostic_events(events)
    assert events == original and row["capture"]["incomplete"] == 1
    assert row["search"]["known_tile_exposure"] == 2
    assert row["search"]["total_eligible_search_steps"] is None
    assert row["search"]["step_probability"] is None
    assert row["fishing"] == dict(observed_casts=2, selected_target_sightings=1, no_bites=1)
    assert not row["training_admission"] and not row["automatic_fit"]


def test_battle_hp_drop_and_no_pp_spend_do_not_invent_miss_crit_or_immunity():
    before = replace(
        _raw(),
        battle_state=2,
        active_party_hp=100,
        enemy_hp=50,
        active_party_index=0,
        enemy_party_position=0,
        player_disabled_move_slot=1,
        player_disable_turns=3,
        player_confused=True,
    )
    after = replace(before, active_party_hp=1)
    row = battle_failure_diagnostics(dict(outcome=dict(move_executed=False)), before, after)
    assert row["observed_player_hp_decrease"] == 99
    assert row["disabled_move_slot_before"] == 1 and row["confused_before"]
    assert row["critical_hit_observed"] is row["miss_observed"] is None
    assert row["immunity_message_observed"] is row["unexecuted_move_reason"] is None
    assert not row["training_admission"]
    switched = battle_failure_diagnostics({}, before, replace(after, active_party_index=1))
    assert switched["observed_player_hp_decrease"] is None


def test_future_train_attempt_links_only_executed_outcome_and_declared_source(
    tmp_path, monkeypatch
):
    store, emulator, args = fixture(tmp_path, monkeypatch)
    result = record_native_player_lesson(store, **args)
    row = result["selection_context"]
    assert row["source_sha256"] == canonical_sha256(args["source"])
    assert row["source_state_sha256"] == args["source"]["state_sha256"]
    assert row["source_partition"] == "train"
    chosen = [r for r in row["alternatives"] if r["execution_status"] == "attempted"]
    assert len(chosen) == 1 and chosen[0]["candidate_index"] == result["selected_index"]
    assert chosen[0]["outcome_reference_sha256"] == canonical_sha256(result["outcome"])
    assert all(
        r["outcome_reference_sha256"] is None
        for r in row["alternatives"]
        if r["execution_status"] == "unexecuted"
    )
    assert not row["comparative_labels_created"] and not row["automatic_training_admission"]
    assert result["actions_completed"] > 0  # Simulated input only.
    assert emulator.frame_count == result["frames"]


def test_automatic_outcome_review_preserves_actual_selection_and_execution(tmp_path, monkeypatch):
    original = copy.deepcopy(_model().model_sha256)
    results = []
    for instrumented in (False, True):
        output = tmp_path / str(instrumented)
        state, snapshot, observe = _environment(output)
        with monkeypatch.context() as scoped:
            if not instrumented:
                scoped.setattr(
                    "pokemon_red_completion.red_player_lesson_runtime.player_outcome_diagnostics",
                    lambda *args, **kwargs: {},
                )
            result = autonomous.run_autonomous_options(
                model=_model(),
                output=output,
                snapshot=snapshot,
                observe=observe,
                seed=17,
                provenance={},
                maximum_decisions=1,
            )
        results.append(
            (state, result, json.loads((output / "step-000/decision.json").read_bytes()))
        )
    assert results[0][0] == results[1][0]
    assert results[0][2] == results[1][2]
    before, after = [r[1]["outcomes"][0] for r in results]
    for key in ("choice", "verification", "measured_cost", "observed_cost", "before", "after"):
        assert before[key] == after[key]
    assert after["diagnostic_review"]["prediction_comparison"]["raw_predictions"] is not None
    assert not after["diagnostic_review"]["training_admission"]
    assert results[1][1]["model_sha256"] == original
