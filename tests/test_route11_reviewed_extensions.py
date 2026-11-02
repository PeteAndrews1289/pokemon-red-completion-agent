"""Prospective Route11 compatibility: exact predecessors and default behavior."""
import ast
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_party_development_venue_priors as prior
from pokemon_red_completion import red_team_training as training
from pokemon_red_completion.blaine import ROUTE_11_TRAINING_VENUE
from test_red_team_training import (
    DIGLETT_SPECIES_ID, FINAL_FORM_ROSTER, FakeExecutor, FakeMemory, FakeReader,
    balancing_kwargs, state,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_TRAINING_COMMIT = "ba9d32c9b84a1eefedce438023e9637b6d77f868"


def definition(file, name):
    tree = ast.parse((ROOT / "src/pokemon_red_completion" / file).read_text())
    return next(node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                and node.name == name)


def test_transport_extension_reconstructs_exact_reviewed_venue_class():
    node = definition("training_venue.py", "TrainingVenue")
    additions = [item for item in node.body if isinstance(item, ast.AnnAssign)
                 and isinstance(item.target, ast.Name) and item.target.id == "native_transport_ready"]
    assert len(additions) == 1
    node.body.remove(additions[0])
    init = next(item for item in node.body if isinstance(item, ast.FunctionDef)
                and item.name == "__post_init__")
    additions = [item for item in init.body if isinstance(item, ast.If)
                 and "native_transport_ready" in ast.unparse(item.test)]
    assert len(additions) == 1
    init.body.remove(additions[0])
    assert prior._ast_node_sha256(node, qualname="TrainingVenue") == (
        prior._ROUTE_11_REVIEWED_PREDECESSOR_AST_SHA256["training-venue.contract"])
    assert ROUTE_11_TRAINING_VENUE.native_transport_ready is None
    with pytest.raises(prior.RedPartyDevelopmentVenuePriorError, match="qualified operating seam"):
        prior._require_current_route_11_venue(replace(
            ROUTE_11_TRAINING_VENUE, native_transport_ready=lambda _: True))


def test_optional_cave_egress_reconstructs_exact_reviewed_healing_function():
    node = definition("blaine.py", "_route_11_heal_and_return")
    changed = [item for item in ast.walk(node) if isinstance(item, ast.BoolOp)
               and isinstance(item.op, ast.And) and len(item.values) == 2
               and ast.unparse(item.values[0]) == "ground_transition is not None"]
    assert len(changed) == 1
    extension = changed[0].values[1]
    assert isinstance(extension, ast.BoolOp) and isinstance(extension.op, ast.Or)
    changed[0].values[1] = extension.values[0]
    assert prior._ast_node_sha256(node, qualname="_route_11_heal_and_return") == (
        prior._ROUTE_11_REVIEWED_PREDECESSOR_AST_SHA256["red.route-11-heal-and-return"])


def reviewed_balancer():
    source = subprocess.check_output([
        "git", "show", REVIEWED_TRAINING_COMMIT + ":src/pokemon_red_completion/red_team_training.py",
    ], cwd=ROOT)
    assert prior._committed_element_ast_sha256(source, qualname="run_red_team_balancing") == (
        prior._ROUTE_11_REVIEWED_PREDECESSOR_AST_SHA256["red.run-team-balancing"])
    node = next(item for item in ast.parse(source).body if isinstance(item, ast.FunctionDef)
                and item.name == "run_red_team_balancing")
    module = ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(vars(training))
    exec(compile(module, "reviewed-route11-balancer", "exec"), namespace)
    return namespace["run_red_team_balancing"]


def run_legacy_case(function, case):
    memory = FakeMemory()
    flees = []
    if case == "finished":
        memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
        reader = FakeReader([state()])
    else:
        memory.set_party([(DIGLETT_SPECIES_ID, 20), (training.BLASTOISE_SPECIES_ID, 30)]
                         + [(training.DUGTRIO_SPECIES_ID, 25)] * 4, hp=30)
        reader = FakeReader([state(battle_state=1, enemy_level=32, enemy_species_id=0x21)])
    executor = FakeExecutor(memory)
    executor.execute_training_healing = lambda *_: pytest.fail("legacy path used native metering")
    options = balancing_kwargs(flee_func=lambda *_: flees.append(True))
    try:
        report, battles, heals = function(executor, reader, memory, **options)
        outcome = ("returned", report.passed, battles, heals)
    except RuntimeError as error:
        outcome = ("error", str(error))
    return outcome, flees, memory.swaps, [(x.species, x.level, x.hp) for x in memory.party]


@pytest.mark.parametrize("case", ["finished", "bounded-flee"])
def test_existing_balancer_defaults_match_exact_reviewed_predecessor(monkeypatch, case):
    def forbidden(*args, **kwargs):
        pytest.fail("legacy default entered an opt-in collection/bootstrap branch")
    for name in ("collection_finisher", "collection_escape_escort", "collection_damage_pp",
                 "collection_recipient_needs_recovery", "qualified_bootstrap_evolution_escort"):
        monkeypatch.setattr(training, name, forbidden)
    assert run_legacy_case(training.run_red_team_balancing, case) == (
        run_legacy_case(reviewed_balancer(), case))


def test_new_default_helpers_are_pinned_and_do_not_observe_or_meter():
    identifiers = {"red.helper-exclusion-validation", "red.evolution-no-win-boundary",
                   "red.evolution-healing-trip"}
    specs = {item.element_id: item for item in prior._ROUTE_11_SOURCE_ELEMENTS}
    waivers = {item.element_id: item for item in prior._ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS}
    for identifier in identifiers:
        spec = specs[identifier]
        assert waivers[identifier].observed_ast_sha256 is None
        assert prior._loaded_element_ast_sha256(spec.current_object, qualname=spec.qualname) == (
            waivers[identifier].current_ast_sha256)
    training.validate_collection_helper_exclusions(frozenset())
    reader = N(read=lambda: pytest.fail("ordinary training observed collection-only boundary"))
    assert training._bounded_no_win_evolution_pause(reader, collection_shared_experience=False,
        collection_encounters=None, evolution_target=None, battles=0, healing_trips=0) is None
    calls = []
    actions = N(execute_training_healing=lambda *_: pytest.fail("unmetered legacy used hook"))
    training.execute_evolution_healing_trip(actions, reader, None,
        lambda *ports: calls.append(ports), metered=False)
    assert calls == [(actions, reader, None)]
