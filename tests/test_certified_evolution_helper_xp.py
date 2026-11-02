"""No-ROM bounds and fresh native-admission checks; no controller or model."""
import ast
import inspect
import textwrap
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_evolution_helper_xp as xp
from pokemon_red_completion import red_team_training as training
from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.observation import ItemId


def guard():
    # Explicit synthetic mechanics fixture, not a cartridge qualification.
    return xp.EvolutionHelperXPGuard(
        ((1, 36, tuple(level ** 3 for level in range(1, 101))),),
        frozenset({1, 2, 3}), frozenset({1}), xp._QUALIFIED_ROM)


def member(level=20, experience=8000, species_id=1):
    return N(species_id=species_id, level=level, experience=experience)


def raw(**changes):
    return N(**dict(dict(bag_items=(), battle_state=0, enemy_species_id=None,
                        enemy_level=None), **changes))


def excluded(g=None, members=None, observation=None):
    return (g or guard()).exclusions(
        N(members=members if members is not None else (member(),)),
        observation or raw())


def test_integer_bound_dominates_every_participant_and_bonus_case():
    maximum = 0
    for base in range(1, 256):
        for level in range(1, 101):
            upper = xp.ordinary_red_xp_upper_bound(base, level)
            maximum = max(maximum, upper)
            for participants in range(1, 7):
                amount = (base // participants) * level // 7
                for boosts in range(3):
                    actual = amount
                    for _ in range(boosts):
                        actual += actual // 2
                    assert actual <= upper
    assert maximum == 8194 == xp._MAXIMUM_SINGLE_AWARD


@pytest.mark.parametrize("base,level", [
    (None, 1), (True, 1), (0, 1), (256, 1), (1, None), (1, True), (1, 0), (1, 101),
])
def test_unknown_or_out_of_range_cartridge_facts_reject(base, level):
    with pytest.raises(ValueError):
        xp.ordinary_red_xp_upper_bound(base, level)


def test_guard_is_about_evolution_not_ordinary_level_up():
    assert 8000 + 8194 >= 21 ** 3  # The helper may legally gain ordinary levels.
    assert excluded() == frozenset()
    assert context.RedGoalContextRuntime.__dataclass_fields__[
        "certified_evolution_helper_xp"].default is False
    assert inspect.signature(training.run_red_team_balancing).parameters[
        "collection_helper_xp_guard"].default is None


@pytest.mark.parametrize("delta,expected", [(-1, frozenset()), (0, frozenset({1})), (1, frozenset({1}))])
def test_next_evolution_threshold_is_strict(delta, expected):
    experience = 36 ** 3 - 8194 + delta
    assert 33 ** 3 <= experience < 34 ** 3
    assert excluded(members=(member(33, experience),)) == expected


@pytest.mark.parametrize("m", [
    member(36, 36 ** 3), member(37, 37 ** 3), member(20, None),
    member(20, True), member(20, 7999), member(20, 21 ** 3),
    member(0, 0), member(101, 1000000),
])
def test_overdue_unknown_or_inconsistent_helper_retains_exclusion(m):
    assert excluded(members=(m,)) == frozenset({1})


@pytest.mark.parametrize("observation", [
    raw(bag_items=None), raw(bag_items=((int(ItemId.EXP_ALL), 1),)),
    raw(bag_items=((4, 1), (4, 2))), raw(bag_items=((4, 0),)),
    raw(bag_items=((4, True),)), raw(bag_items=((None, 1),)),
    raw(battle_state=None), raw(battle_state=True), raw(battle_state=2),
    raw(battle_state=1, enemy_species_id=None, enemy_level=10),
    raw(battle_state=1, enemy_species_id=255, enemy_level=10),
    raw(battle_state=1, enemy_species_id=2, enemy_level=None),
    raw(battle_state=1, enemy_species_id=2, enemy_level=101),
])
def test_unknown_environment_exp_all_or_nonwild_keeps_old_exclusion(observation):
    assert excluded(observation=observation) == frozenset({1})


def test_known_single_wild_and_trade_or_participation_uncertainty_are_covered():
    # No assumption about which party members participated or their OT equality.
    assert excluded(observation=raw(battle_state=1, enemy_species_id=2, enemy_level=100)) == frozenset()


def test_duplicate_species_cannot_smuggle_an_unsafe_helper():
    assert excluded(members=(member(), member(36, 36 ** 3))) == frozenset({1})
    assert excluded(members=(member(), member(experience=None))) == frozenset({1})


def test_scope_rejects_forged_or_mismatched_guard():
    good = guard()
    good.require_scope(frozenset({1}))
    with pytest.raises(ValueError):
        good.require_scope(frozenset())
    with pytest.raises(ValueError):
        replace(good, _qualification_token=None).require_scope(frozenset({1}))
    with pytest.raises(ValueError, match="canonical Red"):
        xp.EvolutionHelperXPGuard.from_rom(b"unqualified ROM", frozenset({1}))


def test_actual_loop_prefix_rechecks_xp_and_environment_each_iteration():
    # Execute the actual production loop prefix only; no battle/controller port.
    fn = ast.parse(textwrap.dedent(inspect.getsource(
        training.run_red_team_balancing))).body[0]
    loop = next(node for node in fn.body if isinstance(node, ast.While)
                and isinstance(node.test, ast.Constant) and node.test.value is True)
    assert isinstance(loop.body[0], ast.Assign)
    assert ast.unparse(loop.body[0]) == "party = party_reader.read()"
    gate = loop.body[1]
    assert isinstance(gate, ast.If)
    assert ast.unparse(gate.test) == "collection_helper_xp_guard is not None"
    body = ast.Module(body=loop.body[:2], type_ignores=[])
    ast.fix_missing_locations(body)
    code = compile(body, "actual-live-helper-guard-prefix", "exec")
    observations = iter((raw(), raw(bag_items=((int(ItemId.EXP_ALL), 1),))))
    parties = iter((N(members=(member(),)), N(members=(member(36, 36 ** 3),))))
    namespace = dict(collection_helper_xp_guard=guard(),
                     excluded_collection_helper_species=frozenset({1}),
                     party_reader=N(read=lambda: next(parties)),
                     reader=N(read=lambda: next(observations)))
    exec(code, namespace)
    assert namespace["excluded_collection_helper_species"] == frozenset()
    exec(code, namespace)
    assert namespace["excluded_collection_helper_species"] == frozenset({1})


def test_disabled_loop_prefix_does_not_read_extra_native_facts():
    fn = ast.parse(textwrap.dedent(inspect.getsource(training.run_red_team_balancing))).body[0]
    loop = next(node for node in fn.body if isinstance(node, ast.While)
                and isinstance(node.test, ast.Constant) and node.test.value is True)
    body = ast.Module(body=loop.body[:2], type_ignores=[])
    ast.fix_missing_locations(body)
    def forbidden():
        pytest.fail("default path read new native facts")
    namespace = dict(collection_helper_xp_guard=None,
                     excluded_collection_helper_species=frozenset({1}),
                     party_reader=N(read=lambda: N(members=())),
                     reader=N(read=forbidden))
    exec(compile(body, "default-helper-guard-prefix", "exec"), namespace)
    assert namespace["excluded_collection_helper_species"] == frozenset({1})


def test_selected_evolution_stock_and_safety_referee_is_unchanged():
    from pokemon_red_completion import red_native_boxed_evolution as native
    source = ast.parse(textwrap.dedent(inspect.getsource(native.bind_native_boxed_evolution))).body[0]
    inner = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "train")
    # Only the new typed productive-pause aggregator differs; the old
    # exact selected-transformation/stock/progress verifier remains unchanged.
    catches = [node for node in ast.walk(inner) if isinstance(node, ast.ExceptHandler)
               and isinstance(node.type, ast.Name) and node.type.id == "EvolutionHelperXPExhausted"]
    assert len(catches) == 1
    class RemoveKnownHeadroomPause(ast.NodeTransformer):
        def visit_ExceptHandler(self, node):
            return None if node in catches else self.generic_visit(node)
    inner = RemoveKnownHeadroomPause().visit(inner)
    from hashlib import sha256
    assert sha256(ast.dump(inner, include_attributes=False).encode()).hexdigest() == (
        "576fb2d8acee209e4eb720ee014715f87991479cf4d32096e9fed9087f3acbf0"
    )
