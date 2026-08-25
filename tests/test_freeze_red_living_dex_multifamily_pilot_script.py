# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    adapt_red_living_dex_dependencies,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_multifamily_pilot.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_multifamily_pilot_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _args() -> list[str]:
    return [
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        _sha("source"),
        "--registry-source-commit",
        "b" * 40,
        "--expected-registry-sha256",
        _sha("registry"),
        "--context-catalog",
        "/protected/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/protected/plan.json",
        "--expected-context-plan-sha256",
        _sha("plan"),
        "--private-root",
        "/protected/artifacts",
        "--rom",
        "/protected/red.gb",
    ]


def test_parser_requires_every_frozen_input_identity() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.registry_source_commit == "b" * 40
    assert parsed.private_root == Path("/protected/artifacts")
    with pytest.raises(SCRIPT["MultifamilyPilotFreezeError"]):
        SCRIPT["_parser"]().parse_args(_args()[:-4])


def test_source_failure_stops_before_private_inputs_and_receipt_is_path_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0

    def private(*_args: object, **_kwargs: object) -> object:
        nonlocal private_calls
        private_calls += 1
        raise AssertionError("private inputs opened")

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_authenticate_source",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["MultifamilyPilotFreezeError"]("source_authentication")
        ),
    )
    monkeypatch.setitem(SCRIPT["main"].__globals__, "_authenticate_inputs", private)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "source_authentication"
    assert result["controller_actions"] == 0
    assert result["roots_claimed"] == 0
    assert "/protected" not in json.dumps(result)


def test_freezer_has_no_controller_or_model_execution_seam() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "CountingExecutor" not in source
    assert "execute_route" not in source
    assert "score_red_living_dex_option" not in source
    assert "write_root_claim" not in source


def test_only_repeatable_item_free_level_evolutions_enter_boxed_inventory() -> None:
    catalog = SCRIPT["RED_ACQUISITION_CATALOG"]

    level_method = catalog.method_for("pokemon:national:012")
    item_method = catalog.method_for("pokemon:national:031")
    trade_method = catalog.method_for("pokemon:national:124")

    assert SCRIPT["_supported_level_evolution"](level_method)
    assert not SCRIPT["_supported_level_evolution"](item_method)
    assert not SCRIPT["_supported_level_evolution"](trade_method)


def test_freezer_family_key_is_the_adapters_complete_transformation_identity() -> None:
    method = SCRIPT["RED_ACQUISITION_CATALOG"].method_for("pokemon:national:012")
    precursor = red_species_ref(11)
    evolved = red_species_ref(12)
    specimens = (
        LivingSpecimen(
            precursor,
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=0,
        ),
        LivingSpecimen(
            precursor,
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=1,
        ),
    )
    observation = CollectionObservation(
        owned_species=frozenset({precursor}),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(2,),
        current_box_index=0,
        box_capacity=20,
    )
    adapted = adapt_red_living_dex_dependencies(
        observation,
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({precursor}),
            trainable_evolution_pairs=frozenset({(precursor, evolved)}),
        ),
    )
    opportunity = next(
        item
        for item in adapted.opportunities
        if item.binding.precursor_species_ref == precursor
        and item.binding.evolved_species_ref == evolved
    )

    assert SCRIPT["_family_identity"](method) == opportunity.binding.binding_sha256
    assert SCRIPT["_family_identity"](method) != SCRIPT[
        "RedDependencySpeciesBinding"
    ](precursor, evolved).binding_sha256
