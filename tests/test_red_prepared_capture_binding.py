from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from test_red_capture_preparation import runtime, swap_raw
from test_red_routed_capture_support import unavailable

import pokemon_red_completion.red_capture_preparation as prep
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_routed_recovery import (
    RedRoutedRecoveryError,
    guarded_collection_route_handler,
)

SOURCE = "pokemon.red:acquisition:wild:Route24:grass"


@dataclass
class Router:
    runtime: object
    actions: object
    selected: object
    calls: list
    prepare_capture_escort: bool = True

    def enumerate(self, fresh):
        assert not self.prepare_capture_escort
        self.calls.append("rebind")
        assert fresh.party.members[0].level == 55
        return GoalBindingSet((self.selected.opportunity, unavailable()), (self.selected,))


def fixture(monkeypatch):
    state = runtime()
    state.reader.raw = replace(state.reader.raw, party_hp=(180, 180))
    state.emulator = SimpleNamespace(frame_count=0)
    state.profile = SimpleNamespace(providers=(SimpleNamespace(
        kind=GoalKind.ACQUIRE_SPECIES, parameters={"source_id": "wild:Route24:grass"},
    ),))
    actions, calls = SimpleNamespace(actions_executed=0), []
    def swap(*_args, **_kwargs):
        calls.append("swap")
        swap_raw(state.reader)
        actions.actions_executed += 2
        state.emulator.frame_count += 4
    monkeypatch.setattr(prep, "close_menu", lambda *_: None)
    monkeypatch.setattr(prep, "swap_party_slots", swap)
    def execute():
        calls.append("capture")
        actions.actions_executed += 3
        state.emulator.frame_count += 6
        return GoalExecutionReport(3, 6, {"source": SOURCE})
    def verify(report):
        assert (report.actions_executed, report.frames_executed) == (3, 6)
        calls.append("verify")
        return GoalVerification.succeeded()
    selected = ExecutableGoalBinding(
        "fresh", GoalKind.ACQUIRE_SPECIES, .2, .1, execute=execute, verify=verify,
        search_source_ref=SOURCE,
    )
    original = replace(selected, binding_ref="old",
                       execute=lambda: pytest.fail("stale binding executed"))
    router = Router(state, actions, selected, calls)
    return router, GoalBindingSet((original.opportunity, unavailable()), (original,)), calls


def test_selected_source_prepared_rebound_and_verified_without_extra_label(monkeypatch):
    router, bindings, calls = fixture(monkeypatch)
    prepared = prep.bind_capture_escort(router, bindings, router.runtime.adapter.observe())
    assert calls == []
    assert prepared.opportunities == bindings.opportunities
    binding = prepared.bindings[0]
    report = binding.execute()
    assert calls == ["swap", "rebind", "capture"]
    assert (report.actions_executed, report.frames_executed) == (5, 10)
    assert report.evidence["escort_preparation"]["setup_training_rows"] == 0
    binding.verify(report)
    assert calls[-1] == "verify"
    with pytest.raises(RedCaptureLeadError, match="consumed"):
        binding.execute()


def test_fainted_party_masks_only_capture_without_input(monkeypatch):
    router, bindings, calls = fixture(monkeypatch)
    router.runtime.reader.raw = replace(router.runtime.reader.raw, party_hp=(0, 180))
    result = prep.bind_capture_escort(router, bindings, router.runtime.adapter.observe())
    assert not result.bindings
    assert result.opportunities[0].availability is GoalAvailability.UNAVAILABLE
    assert calls == []


def test_source_change_after_preparation_refuses_before_capture(monkeypatch):
    router, bindings, calls = fixture(monkeypatch)
    router.selected = replace(router.selected, search_source_ref="different")
    prepared = prep.bind_capture_escort(router, bindings, router.runtime.adapter.observe())
    binding = prepared.bindings[0]
    with pytest.raises(RedCaptureLeadError, match="selected source"):
        binding.execute()
    assert calls == ["swap", "rebind"]


def test_stale_party_refuses_before_any_input(monkeypatch):
    router, bindings, calls = fixture(monkeypatch)
    prepared = prep.bind_capture_escort(router, bindings, router.runtime.adapter.observe())
    binding = prepared.bindings[0]
    router.runtime.reader.raw = replace(router.runtime.reader.raw, party_hp=(180, 170))
    with pytest.raises(RedCaptureLeadError, match="before input"):
        binding.execute()
    assert calls == []


def test_arrival_provider_qualifies_and_rebinds_after_swap(monkeypatch):
    router, bindings, calls = fixture(monkeypatch)
    offers = []
    def offer(observation):
        offers.append(observation.party.members[0].level)
        return RedGoalBindingOffer.available(
            bindings.bindings[0] if len(offers) == 1 else router.selected,
        )
    provider = prep.EscortPreparedCaptureProvider(
        SimpleNamespace(offer=offer), router.runtime, router.actions,
    )
    binding = provider.offer(router.runtime.adapter.observe()).binding
    report = binding.execute()
    binding.verify(report)
    assert offers == [10, 55]
    assert calls == ["swap", "capture", "verify"]


@pytest.mark.parametrize("bad_move", [120, 153])
def test_actual_recovery_battle_policy_never_selects_self_destruct(monkeypatch, bad_move):
    router, _bindings, _calls = fixture(monkeypatch)
    raw = replace(
        router.runtime.reader.raw, battle_state=2, active_party_species_id=179,
        active_party_moves=(bad_move, 55, 0, 0), active_party_pp=(5, 20, 0, 0),
        enemy_species_id=165,
    )
    handler = guarded_collection_route_handler(
        router.actions, router.runtime.reader, route_name="test recovery",
    )
    assert handler.inner.move_slot_policy(raw) == 2
    assert raw.active_party_pp == (5, 20, 0, 0)
    with pytest.raises(RedRoutedRecoveryError, match="sustainable"):
        handler.inner.move_slot_policy(replace(raw, active_party_pp=(5, 0, 0, 0)))
