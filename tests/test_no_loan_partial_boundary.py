"""No-loan partials retain failed evolution semantics and exact native custody."""

from types import SimpleNamespace as NS

import pytest
from test_no_loan_evolution_settlement import retained_guard

from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution


@pytest.mark.parametrize(
    "fault", ["battle", "unready", "fainted", "training_error", "no_guard", None]
)
def test_only_exact_settled_fault_free_roster_gets_custody_evidence(fault):
    guard = retained_guard()
    observation = NS(
        raw=NS(battle_state=int(fault == "battle")),
        input_ready=fault != "unready",
        party=NS(fainted_count=int(fault == "fainted")),
    )
    runtime = NS(
        evolution_settlement=None,
        adapter=NS(party_guard=None if fault == "no_guard" else guard, observe=lambda: observation),
    )
    kwargs = {"training_error": RuntimeError("native error")} if fault == "training_error" else {}
    evidence = settle_native_evolution(runtime, object(), **kwargs)
    assert evidence == ({"retained_active_roster_restored": True} if fault is None else {})


def test_missing_or_substituted_native_individual_still_rejects():
    guard = retained_guard()
    guard.reader.preparation_specimen_refs = lambda: ("substituted",)
    runtime = NS(
        evolution_settlement=None,
        adapter=NS(
            party_guard=guard,
            observe=lambda: NS(raw=NS(battle_state=0), input_ready=True, party=NS(fainted_count=0)),
        ),
    )
    with pytest.raises(ValueError, match="lost|duplicated|restored"):
        settle_native_evolution(runtime, object())
