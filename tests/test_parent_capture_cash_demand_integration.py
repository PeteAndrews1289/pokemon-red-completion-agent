"""Real option-observer integration, using existing inert snapshot fixtures."""
from dataclasses import replace
import pytest
from test_red_player_lesson_runtime import fixture
from test_red_live_option_menu import _ordinary_bindings,_situation
import pokemon_red_completion.red_player_lesson_runtime as lesson
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
from pokemon_red_completion.living_dex_option_value import pure_income_success_saturated
from test_parent_capture_cash_demand import funding


@pytest.mark.parametrize("target,known",[(4800,True),(0,True),(None,False)])
def test_real_observer_bound_inventory_cash_metadata_reaches_parent_menu(tmp_path,monkeypatch,target,known):
    _, emulator, kwargs=fixture(tmp_path,monkeypatch)
    runtime=kwargs["runtime_factory"](emulator)
    original_capture=lesson.capture_player_lesson_snapshot
    def capture(rt):
        observation,snapshot=original_capture(rt)
        observation.situation=_situation(resources=1.0)
        observation.raw.player_money=107
        observation.raw.bag_items=((1,1),)  # protected Master Ball, no ordinary balls
        return observation,snapshot
    monkeypatch.setattr(lesson,"capture_player_lesson_snapshot",capture)
    actions=object();calls=[];cash_calls=[];ordinary=_ordinary_bindings(calls)
    base=lambda *_:ordinary
    baseline_inventory=NativeStoryBranchInventory(base,lambda *_:())
    def quote(rt,observed_actions):
        assert rt is runtime and observed_actions is actions
        cash_calls.append((rt,observed_actions))
        return target
    inventory=NativeStoryBranchInventory(base,lambda *_:(),observe_cash_target=quote)
    args={n:kwargs[n] for n in ("battle","combat_specimen_refs","remaining_budget")}
    before=emulator.save_state_bytes()
    baseline=lesson.observe_native_player_options(runtime,actions,**args,target_cash=0,
        ordering_seed_sha256="a"*64,model_feature_version=16,force_resource_safety=False,
        **baseline_inventory.native_callbacks())
    observed=lesson.observe_native_player_options(runtime,actions,**args,target_cash=0,
        ordering_seed_sha256="a"*64,model_feature_version=16,force_resource_safety=False,
        **inventory.native_callbacks())
    assert len(cash_calls)==1
    assert observed.bindings==baseline.bindings
    assert observed.menu.candidates==baseline.menu.candidates
    assert observed.menu.available_indices==baseline.menu.available_indices
    assert observed.menu.context==replace(baseline.menu.context,
        target_cash=0 if target is None else target,cash_target_known=known)
    assert observed.menu.context.economy_snapshot.cash==107
    assert pure_income_success_saturated(observed.menu.context,funding()) is (known and target==0)
    assert emulator.save_state_bytes()==before and emulator.frame_count==0
    assert not emulator.pressed_buttons and not calls


def test_real_observer_still_rejects_cash_observation_that_mutates_state(tmp_path,monkeypatch):
    _, emulator, kwargs=fixture(tmp_path,monkeypatch)
    runtime=kwargs["runtime_factory"](emulator)
    original_capture=lesson.capture_player_lesson_snapshot
    def capture(rt):
        observation,snapshot=original_capture(rt)
        observation.situation=_situation(resources=.1)
        return observation,snapshot
    monkeypatch.setattr(lesson,"capture_player_lesson_snapshot",capture)
    def bad_quote(*_):
        emulator.tick(1)  # inert fixture only; demonstrates the existing purity guard
        return 4800
    inventory=NativeStoryBranchInventory(lambda *_:_ordinary_bindings([]),lambda *_:(),
        observe_cash_target=bad_quote)
    with pytest.raises(ValueError,match="menu changed state"):
        lesson.observe_native_player_options(runtime,object(),
            **{n:kwargs[n] for n in ("battle","combat_specimen_refs","remaining_budget")},
            target_cash=0,ordering_seed_sha256="a"*64,model_feature_version=16,
            force_resource_safety=False,**inventory.native_callbacks())
