"""Session 32 (F30): fresh runs must not stop on an exhausted catch, circling travel or a hopeless battle."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)

PAUSE = "throw budget exhausted; live encounter retained without Run"
FAINT_PAUSE = "throw budget exhausted at catcher faint"


def _binding(ref, kind=GoalKind.RECOVER_CONTROL):
    return ExecutableGoalBinding(
        ref, kind, 0.0, 0.0, lambda: pytest.fail("inspection cannot execute"),
        lambda _: GoalVerification.succeeded(),
    )


def _inventory(*bindings):
    opportunities = tuple(b.opportunity for b in bindings)
    if len(opportunities) == 1:
        opportunities += (
            GoalOpportunity("blocked", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET),
        )
    return GoalBindingSet(opportunities, bindings)


def _paused_result(state_sha, error=PAUSE, kind="acquire_species"):
    return dict(
        released=True, field_ready=False, state_sha256=state_sha,
        episode=dict(stop_reason="execution_failed", outcomes=[dict(
            selected_kind=kind, failure_phase="execution", safe_terminal=False,
            error_type="OneOffCapturePaused", error=error, terminal_state_sha256=state_sha)]),
    )


@pytest.mark.parametrize("fault", [
    None, "catcher_faint", "other_pause", "wrong_kind", "field", "blackout", "wrong_ref", "extra",
    "prior_error", "ready", "mutated",
])
def test_exhausted_one_off_catch_hands_off_only_to_its_exact_retained_capture(monkeypatch, fault):
    import run_configured_red_player as script

    payload = [b"paused-snorlax"]
    state_sha = sha256(payload[0]).hexdigest()
    raw = N(battle_state=0 if fault == "field" else 1,
            party_hp=(0, 0, 0) if fault == "blackout" else (0, 43, 70))
    runtime = N(emulator=N(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: payload[0]),
                reader=N(read=lambda: raw))
    result = _paused_result(
        state_sha,
        error=FAINT_PAUSE if fault == "catcher_faint"
        else "ball settlement bound exhausted" if fault == "other_pause" else PAUSE,
        kind="advance_story" if fault == "wrong_kind" else "acquire_species",
    )
    if fault == "prior_error":
        result["episode"]["outcomes"].insert(
            0, dict(selected_kind="advance_story", error_type="RuntimeError", error="unrelated"))
    monkeypatch.setattr(script, "_field_ready", lambda _: fault == "ready")
    calls = []

    def inspect():
        calls.append(True)
        if fault == "mutated":
            payload[0] = b"changed"
        ref = ("pokemon.red:interrupted-wild:" if fault == "wrong_ref"
               else "pokemon.red:retained-capture:") + state_sha
        bindings = (_binding(ref),)
        if fault == "extra":
            bindings += (_binding("other", GoalKind.EXPLORE),)
        return _inventory(*bindings)

    if fault == "mutated":
        with pytest.raises(ValueError, match="changed state"):
            script.qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inspect)
        return
    receipt = script.qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inspect)
    if fault in {None, "catcher_faint"}:
        assert receipt["qualified"] is True and receipt["retained_capture_pause"] is True
        assert receipt["binding_ref"] == "pokemon.red:retained-capture:" + state_sha
        assert receipt["inputs"] == receipt["frames"] == receipt["model_queries"] == 0
        assert receipt["strategic_substitution"] is False and receipt["original_terminal_safe"] is False
    else:
        assert receipt is None
    assert calls == ([True] if fault in {None, "catcher_faint", "wrong_ref", "extra"} else [])


@pytest.mark.parametrize("fault", [None, "raises", "other_error"])
def test_paused_capture_inspection_reads_the_failed_segment_not_the_stale_menu(monkeypatch, tmp_path, fault):
    import run_configured_red_player as script

    from pokemon_red_completion import red_player_configuration as configuration

    emulator = N(frame_count=0, pressed_buttons=set(), save_state_bytes=lambda: b"unchanged")
    runtime = N(emulator=emulator, adapter=N(observe=lambda: object()),
                reader=N(read=lambda: N(battle_state=1)))
    result = _paused_result("a" * 64, error="map or money changed" if fault == "other_error" else PAUSE)
    seen, expected, stale = [], object(), object()

    def retained(rt, actions, *, parent, output):
        seen.append((parent, output))
        assert rt is runtime and actions.actions_executed == 0
        if fault == "raises":
            raise ValueError("capture continuation live state/allocation differs")
        return expected

    monkeypatch.setattr(configuration, "_retained_capture_inventory", retained)
    monkeypatch.setattr(script, "qualified_native_control_handoff",
                        lambda row, *, runtime, inspect_bindings: inspect_bindings())
    inspected = script.qualified_menu_control_handoff(
        result, runtime=runtime, menu=N(enumerate_base=lambda *a: stale), retained_parent=tmp_path)
    if fault == "other_error":
        assert inspected is stale and not seen
    else:
        assert seen == [(tmp_path, tmp_path / "capture-handoff-inspection")]
        assert inspected is (None if fault == "raises" else expected)
    assert not (tmp_path / "capture-handoff-inspection").exists()
    assert emulator.frame_count == 0 and not emulator.pressed_buttons


def test_fresh_readiness_adjudicates_a_confirmed_capture_handoff():
    from run_fresh_red_player import model_handoff_verified

    state = "c" * 64
    episodes = [dict(model_decisions=1, outcomes=[dict(
        error_type="OneOffCapturePaused", error=PAUSE, selected_kind="acquire_species",
        terminal_state_sha256=state)])]
    receipt = dict(
        schema="pokemon.red.qualified-native-control-handoff.v1", state_sha256=state,
        binding_ref="pokemon.red:retained-capture:" + state, qualified=True, inputs=0, frames=0,
        model_queries=0, failed_transport_preserved=True, strategic_substitution=False,
        retained_capture_pause=True)
    assert not model_handoff_verified(episodes)
    assert model_handoff_verified(episodes, recovered_control_handoffs=(receipt,))
    assert not model_handoff_verified(
        episodes, recovered_control_handoffs=(dict(receipt, retained_capture_pause=False),))
    other = deepcopy(episodes)
    other[0]["outcomes"][0]["error"] = "map or money changed"
    assert not model_handoff_verified(other, recovered_control_handoffs=(receipt,))


def _snorlax_fixture(monkeypatch, *, party_hp):
    from pokemon_red_completion import red_player_wild_recovery as w
    from pokemon_red_completion import red_snorlax_capture as snorlax
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget

    target = RedStaticCaptureTarget(143, 132, 30, 23, 1, 67, (62, 10), 164)
    count = len(party_hp)
    before = RawGameState(
        True, 23, 10, 61, count, 1, badge_bits=47, bag_items=((1, 1),), event_flags=bytes(256),
        party_species_ids=(186,) * count, party_levels=(27,) * count, party_hp=party_hp,
        party_max_hp=(79,) * count, party_status=(0,) * count, party_moves=((79,),) * count,
        party_pp=((10,),) * count, first_party_hp=party_hp[0], enemy_level=30, player_money=8841,
    )
    raws, state = [before], [b"source"]
    rt = N(
        reader=N(
            read=lambda: raws[0],
            read_wild_capture_identity=lambda: N(original_species_id=132),
            read_pokedex_state=lambda: N(owned_species=frozenset((44,))),
            read_current_map_objects=lambda: (N(sprite_index=1, visible=False),),
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: state[0]),
    )
    monkeypatch.setattr(snorlax, "route12_snorlax_target", lambda _: target)
    monkeypatch.setattr(w, "_field_ready", lambda _: raws[0].battle_state == 0)
    return w, target, before, raws, state, rt


@pytest.mark.parametrize("fault", [None, "extra_event", "blackout", "pp"])
def test_exhausted_snorlax_catch_can_be_lost_with_fainted_members(monkeypatch, fault):
    from pokemon_red_completion import wild_party_flee

    w, target, before, raws, state, rt = _snorlax_fixture(monkeypatch, party_hp=(0, 43, 70))
    actions = N(actions_executed=0)
    with pytest.raises(ValueError, match="exact live supported encounter"):
        w.interrupted_wild_binding(rt, actions, consumed_static_target=target, rom=b"rom")
    used = []

    def flee(executor, reader, encounter, **options):
        used.append(options)
        events = bytearray(before.event_flags)
        events[164 // 8] |= 1 << (164 % 8)
        if fault == "extra_event":
            events[0] |= 1
        raws[0] = replace(
            before, battle_state=0, event_flags=bytes(events),
            party_hp=(0, 0, 0) if fault == "blackout" else (0, 0, 61),
            party_pp=((9,),) * 3 if fault == "pp" else before.party_pp,
        )
        state[0] = b"terminal"
        actions.actions_executed, rt.emulator.frame_count = 5, 400
        return N(verified=True, public_dict=lambda: {"verified": True})

    monkeypatch.setattr(wild_party_flee, "flee_with_fainted_lead", flee)
    monkeypatch.setattr(w, "flee_wild", lambda *a, **k: pytest.fail("lead-only escape is not usable here"))
    binding = w.interrupted_wild_binding(
        rt, actions, consumed_static_target=target, rom=b"rom", allow_static_party_faints=True)
    assert not actions.actions_executed
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
        return
    report = binding.execute()
    assert used[0]["emulator"] is rt.emulator and used[0]["allow_new_faints"] is True
    assert used[0]["consumed_static_event_flags"] == raws[0].event_flags
    assert "allow_opponent_ko_exit" not in used[0]
    assert report.evidence["captured"] is False
    assert report.evidence["lost_static_target"]["species_number"] == 143
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_static_party_faint_escape_is_an_explicit_static_only_permission():
    from pokemon_red_completion import red_player_wild_recovery as w

    with pytest.raises(TypeError):
        w.interrupted_wild_binding(N(), N(), allow_static_party_faints=1)
    with pytest.raises(ValueError, match="consumed static target"):
        w.interrupted_wild_binding(N(), N(), allow_static_party_faints=True)
    with pytest.raises(ValueError):
        w.interrupted_wild_binding(N(), N(), allow_static_party_faints=True, allow_fainted_active=True,
                                   consumed_static_target=object())


def test_consumed_static_event_is_admitted_only_exactly_and_only_after_the_battle(monkeypatch):
    from pokemon_red_completion.wild_party_flee import validate_flee_party

    _, _, before, _, _, _ = _snorlax_fixture(monkeypatch, party_hp=(0, 43, 70))
    events = bytearray(before.event_flags)
    events[164 // 8] |= 1 << (164 % 8)
    consumed = bytes(events)
    after = replace(before, battle_state=0, event_flags=consumed)
    with pytest.raises(ValueError, match="protected state changed"):
        validate_flee_party(before, after)
    validate_flee_party(before, after, consumed_static_event_flags=consumed)
    with pytest.raises(ValueError, match="protected state changed"):
        validate_flee_party(before, replace(after, battle_state=1), consumed_static_event_flags=consumed)
    events[0] |= 1
    with pytest.raises(ValueError, match="protected state changed"):
        validate_flee_party(before, replace(after, event_flags=bytes(events)),
                            consumed_static_event_flags=consumed)
    with pytest.raises(TypeError):
        validate_flee_party(before, after, consumed_static_event_flags=list(consumed))


@pytest.mark.parametrize("party_hp,active,whole_party", [
    ((50, 40), 0, False), ((0, 40), 1, True), ((50, 0), 0, True), ((50, 40), 1, True), (None, None, False)])
def test_retained_capture_loss_uses_the_whole_party_escape_only_when_needed(monkeypatch, party_hp, active, whole_party):
    import hashlib

    import pokemon_red_completion.red_player_wild_recovery as recovery
    from pokemon_red_completion.observation import ItemId

    source = Path(__file__).parents[1] / "runtime_helpers/red_earned_run_completion_20261005.py"
    fn = next(n for n in ast.parse(source.read_text()).body
              if isinstance(n, ast.FunctionDef) and n.name == "_retained_capture_loss_binding")
    calls = []
    original = _binding("original")
    monkeypatch.setattr(recovery, "interrupted_wild_binding", lambda *a, **kw: (calls.append(kw) or original))
    raw = N(bag_items=((40, 1),))
    if party_hp is not None:
        raw.party_hp, raw.active_party_index = party_hp, active
    rt = N(reader=N(read=lambda: raw), emulator=N(save_state_bytes=lambda: b"exact"))
    ns = dict(ItemId=ItemId, c=N(ROM=N(read_bytes=lambda: b"rom"), sha256=hashlib.sha256),
              GoalVerification=GoalVerification, GoalFailureReason=GoalFailureReason, replace=replace)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), ns)
    result = ns[fn.name](rt, object(), N(species_number=143))
    assert ("allow_static_party_faints" in calls[0]) is whole_party
    assert result.binding_ref == "pokemon.red:retained-capture:" + hashlib.sha256(b"exact").hexdigest()


def test_wild_settlement_evidence_is_an_ordinary_copyable_dictionary(monkeypatch):
    from pokemon_red_completion import red_player_field_item as field
    from pokemon_red_completion import red_player_wild_recovery as recovery

    raws = [N(battle_state=0, map_id=147, player_y=5, player_x=10)]
    runtime = N(reader=N(read=lambda: raws[0]))

    def wait(action):
        raws[0] = replace_ns(raws[0], battle_state=1)

    report = GoalExecutionReport(3, 200, dict(escape=dict(verified=True), learned_recovery=False))

    def execute():
        raws[0] = replace_ns(raws[0], battle_state=0)
        return report

    monkeypatch.setattr(recovery, "interrupted_wild_binding", lambda *a, **k: N(
        execute=execute, verify=lambda r: GoalVerification.succeeded()))
    monkeypatch.setattr(field, "_field_ready", lambda _: True)
    evidence = field.settle_story_interaction(runtime, N(execute=wait))
    with pytest.raises(TypeError):
        deepcopy(report.evidence)
    assert type(evidence) is dict and deepcopy(evidence) == dict(report.evidence)


def replace_ns(namespace, **changes):
    return N(**dict(vars(namespace), **changes))


def _struggle_row(visible_pp):
    from pokemon_red_completion.battle_actions import BattleAction

    return dict(
        authority="learner", semantic_action=BattleAction.struggle().public_dict(), policy_elapsed_ns=5,
        legal_party_slots=[2],
        outcome=dict(schema="pokemon.red.model-struggle-turn.v1", authority="learner", pp_spent=0,
                     move_slot=None, departed_main_menu=True, cartridge_selection_observed=True,
                     suppression=None, selected_move_ref="pokemon.red.gb.us.rev0:move:165",
                     execution_claim="attempt_only"),
        model_diagnostics=dict(control_choice="struggle", struggle_proposal=dict(
            schema="pokemon.red.model-struggle-proposal.v1", semantic_action="pokemon.core:battle:struggle",
            public_move_ref="pokemon.red.gb.us.rev0:move:165", source_visible_pp=visible_pp,
            projection_pp=[0.0], ordinary_move_legal_mask=[False], observation_modified=False,
            supplied_action=False)),
    )


@pytest.mark.parametrize("visible_pp,accepted", [
    ([0, 0, 0, 0], True), ([0, 0, 0], True), ([0], True), ([], False), ([0, 1, 0], False),
    ([0, 0, 0, 0, 0], False), ([0, False], False), (None, False)])
def test_model_struggle_evidence_accepts_members_with_fewer_than_four_moves(visible_pp, accepted):
    from pokemon_red_completion.red_post_battle_strategy import _model_struggle_evidence

    before = ([48, 43], [60, 60], [20, 20], [[0, 0, 0, 0], [35, 40, 30, 15]])
    row = _struggle_row(visible_pp)
    if accepted:
        _model_struggle_evidence(row, before, 0, wild=False, roster_faints=0)
    else:
        with pytest.raises(ValueError, match="model Struggle learned execution evidence required"):
            _model_struggle_evidence(row, before, 0, wild=False, roster_faints=0)


def _stalled_result(state_sha, **changes):
    last = dict(selected_kind="advance_story", safe_terminal=True, error_type=None,
                verification="succeeded", terminal_state_sha256=state_sha)
    last.update(changes)
    return dict(released=True, field_ready=True, state_sha256=state_sha,
                episode=dict(stop_reason="repeated_movement_without_progress", outcomes=[last]))


@pytest.mark.parametrize("fault", [
    None, "other_reason", "error", "failed", "unsafe", "stale", "battle", "pressed", "not_ready", "export"])
def test_circling_travel_is_a_bounded_setback_only_at_a_settled_field_state(monkeypatch, fault):
    import run_configured_red_player as script

    payload = b"settled-after-circling"
    state_sha = sha256(payload).hexdigest()
    runtime = N(
        emulator=N(pressed_buttons=("a",) if fault == "pressed" else (), save_state_bytes=lambda: payload),
        reader=N(read=lambda: N(battle_state=1 if fault == "battle" else 0, party_hp=(30, 0))),
        adapter=N(party_guard=None),
    )
    monkeypatch.setattr(script, "_field_ready", lambda _: fault != "not_ready")
    result = _stalled_result(
        "0" * 64 if fault == "stale" else state_sha,
        **(dict(error_type="RuntimeError") if fault == "error" else {}),
        **(dict(verification="failed") if fault == "failed" else {}),
        **(dict(safe_terminal=False) if fault == "unsafe" else {}),
    )
    if fault == "stale":
        result["state_sha256"] = "0" * 64
    if fault == "export":
        result["checkpoint_export_error"] = dict(error="x")
    reason = "verification_failed" if fault == "other_reason" else "repeated_movement_without_progress"
    signature = script.qualified_movement_stall_setback(result, runtime=runtime, reason=reason)
    if fault is None:
        assert signature == ("advance_story", "movement_recurrence", "repeated_movement_without_progress")
        assert GoalKind(signature[0]) is GoalKind.ADVANCE_STORY
        assert script.qualified_safe_stop_setback(result, runtime=runtime, reason=reason) is None
    else:
        assert signature is None


def test_commitment_never_forces_a_revisited_leg_and_releases_when_circling(monkeypatch):
    from test_story_branch_value import _index, _options, _parent, _story

    from pokemon_red_completion import red_story_kind_commitment as kc

    monkeypatch.setattr(kc, "party_fit", lambda readiness: True)
    options = _options([_story("s-far", "reach_fuchsia"), _story("s-near", "reach_fuchsia"),
                        _story("s-erika", "defeat_erika")])
    far, near = _index(options, "s-far"), _index(options, "s-near")
    commitment = kc.StoryKindCommitment("reach_fuchsia", overrides=2)

    def revisited(*indices):
        candidates = tuple(
            replace(candidate, movement_revisit=True) if i in indices else candidate
            for i, candidate in enumerate(options.menu.candidates))
        return replace(options, menu=replace(options.menu, candidates=candidates))

    one = revisited(min(far, near))
    choice, receipt = kc.commit_story_kind(_parent(one, "private:restore"), commitment)
    assert receipt["overridden"] and receipt["committed_movement_revisit"] is False
    assert choice.selected_candidate_index == max(far, near)
    assert kc.commitment_after_choice(commitment, receipt).overrides == 3

    both = revisited(far, near)
    parent = _parent(both, "private:restore")
    choice, receipt = kc.commit_story_kind(parent, commitment)
    assert choice is parent and receipt["overridden"] is False and receipt["party_fit"] is True
    assert receipt["committed_movement_revisit"] is True
    assert receipt["selected_candidate_index"] == parent.selected_candidate_index
    assert kc.commitment_after_choice(commitment, receipt) is None

    assert kc.commitment_after_movement_return(commitment, None) is commitment
    assert kc.commitment_after_movement_return(commitment, dict(stop_required=False)) is None
    assert kc.commitment_after_movement_return(None, dict(stop_required=True)) is None
    with pytest.raises(TypeError):
        kc.commitment_after_movement_return("reach_fuchsia", None)
