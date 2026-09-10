from dataclasses import dataclass, replace
from types import SimpleNamespace

import inspect_red_owned_evolution as module
import pytest
from test_red_owned_evolution_inventory import observation
from test_red_regional_acquisition import _candidate

from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_collection import red_species_ref


@dataclass
class Runtime:
    profile: object


def fixture(
    monkeypatch, *, credited=(), protected=None, mutate=None, unavailable=(), mixed_cap=False,
):
    obs = observation(17, 48, owned=(17, 48))
    obs = replace(obs, specimens=tuple(replace(s, level=28) for s in obs.specimens))
    if mixed_cap:
        capped = replace(obs.specimens[-1], level=100, slot_index=2)
        obs = replace(obs, specimens=(*obs.specimens, capped), box_counts=(3, 0))
    state = SimpleNamespace(frame_count=0, pressed_buttons=(), saved=b"original")
    state.load_state_bytes = lambda b: None
    state.save_state_bytes = lambda: state.saved

    class Emulator:
        def __enter__(self):
            return state

        def __exit__(self, *args):
            return False

    actions = SimpleNamespace(actions_executed=0)
    policy = SimpleNamespace(
        targets=frozenset(map(red_species_ref, (18, 49))),
        protected_counts=protected or {},
        registered=lambda current: (
            current.owned_species | frozenset(map(red_species_ref, credited))
        ),
    )
    ready = SimpleNamespace(
        continuation=SimpleNamespace(record_sha256="c" * 64),
        registration_policy=policy,
        training_plan=SimpleNamespace(maximum_actions=30_000, maximum_frames=3_000_000),
        completion_dose=True,
        rom_path=object(),
        capture=SimpleNamespace(state_bytes=b"original"),
        profile=_candidate().profile,
        routed_recovery=True,
    )
    restored, checked = [], []
    monkeypatch.setattr(module.base, "_route_world", lambda r: SimpleNamespace(rom=b"fixture"))
    monkeypatch.setattr(module.base, "PyBoyAdapter", lambda *a, **kw: Emulator())
    monkeypatch.setattr(
        module.base, "_verify_continuation_restore", lambda r, e: restored.append(r)
    )
    monkeypatch.setattr(module.base, "ReadOnlyController", lambda e: e)
    monkeypatch.setattr(module.base, "PokemonRedStateReader", lambda e: object())
    monkeypatch.setattr(
        module.base, "build_red_goal_context_runtime", lambda **kw: Runtime(kw["profile"])
    )
    monkeypatch.setattr(module.base, "_registered_runtime", lambda r, runtime: runtime)
    monkeypatch.setattr(
        module.base, "_training_observation", lambda r: SimpleNamespace(collection_observation=obs)
    )
    monkeypatch.setattr(module.base, "FrameSafeExecutor", lambda *a: object())
    monkeypatch.setattr(module.base, "CountingExecutor", lambda a: actions)
    monkeypatch.setattr(
        module,
        "evolution_graph",
        lambda rom: {
            17: (Evolution(17, 18, EvolutionMethod.LEVEL, 36),),
            48: (Evolution(48, 49, EvolutionMethod.LEVEL, 31),),
        },
    )

    def native(runtime, world, **kw):
        assert kw == {"maximum_quanta": 128, "allow_cross_box": True}
        return runtime

    def router(runtime, act, world, **kw):
        spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
        target = spec.parameters["target_species_ref"]
        checked.append(target)
        assert kw["maximum_controller_actions"] == 30_000
        assert kw["maximum_emulator_frames"] == 3_000_000
        assert kw["routed_recovery"] and not kw["include_recovery_offers"]

        def enumerate_(observed):
            if mutate == "frame":
                state.frame_count += 1
            elif mutate == "state":
                state.saved = b"changed"
            elif mutate == "button":
                state.pressed_buttons = ("a",)
            elif mutate == "action":
                actions.actions_executed += 1
            count = 0 if target in unavailable else (2 if mutate == "ambiguous" else 1)
            return SimpleNamespace(
                bindings=tuple(SimpleNamespace(kind=GoalKind.EVOLVE_SPECIES) for _ in range(count))
            )

        return SimpleNamespace(enumerate=enumerate_)

    monkeypatch.setattr(module, "bind_native_boxed_evolution", native)
    monkeypatch.setattr(module, "RedResourceGoalRouter", router)
    return ready, checked, restored


def test_actual_inventory_prioritizes_level_gap_not_identity_and_preserves_old_profile(monkeypatch):
    ready, checked, restored = fixture(monkeypatch)
    profile = ready.profile
    result = module.inspect_owned_evolution(ready)
    assert result["selected_transition"] == "evolution:48:49:31"
    assert result["missing_owned_level_objectives"] == 2
    assert result["checked"] == [
        {"transition": "evolution:48:49:31", "available": True, "minimum_level_gains": 3}
    ]
    assert checked == [red_species_ref(49)] and restored == [ready]
    assert ready.profile is profile and result["checkpoint_sha256"] == "c" * 64
    assert result["controller_actions"] == result["emulator_frames"] == 0
    assert not result["learned_target_selection"]


def test_unavailable_shortest_option_does_not_hide_next_real_binding(monkeypatch):
    ready, checked, _ = fixture(monkeypatch, unavailable=(red_species_ref(49),))
    result = module.inspect_owned_evolution(ready)
    assert result["selected_transition"] == "evolution:17:18:36"
    assert checked == [red_species_ref(49), red_species_ref(18)]
    assert [r["available"] for r in result["checked"]] == [False, True]


def test_mixed_capped_stock_is_not_claimed_executable_from_lower_level_alternative(monkeypatch):
    ready, checked, _ = fixture(monkeypatch, mixed_cap=True)
    result = module.inspect_owned_evolution(ready)
    assert result["selected_transition"] == "evolution:17:18:36"
    assert checked == [red_species_ref(18)]
    assert result["checked"][0]["reason"] == "mixed_level_cap_stock_unqualified"


def test_global_credit_and_protected_stock_remove_targets_before_runtime_qualification(monkeypatch):
    ready, checked, _ = fixture(monkeypatch, credited=(49,), protected={red_species_ref(17): 1})
    result = module.inspect_owned_evolution(ready)
    assert result["selected_transition"] is None and not checked
    assert result["missing_owned_level_objectives"] == 1
    assert result["native_stock_eligible_objectives"] == 0


@pytest.mark.parametrize("mutate", ["frame", "state", "button", "action", "ambiguous"])
def test_inspection_rejects_changed_state_or_ambiguous_binding(monkeypatch, mutate):
    ready, _, _ = fixture(monkeypatch, mutate=mutate)
    with pytest.raises(ValueError, match="changed|ambiguous"):
        module.inspect_owned_evolution(ready)


@pytest.mark.parametrize(
    "field", ["continuation", "registration_policy", "training_plan", "completion_dose"]
)
def test_inventory_requires_registered_saved_bounded_scope(monkeypatch, field):
    ready, checked, restored = fixture(monkeypatch)
    setattr(ready, field, None)
    with pytest.raises(ValueError, match="registered bounded"):
        module.inspect_owned_evolution(ready)
    assert not checked and not restored
