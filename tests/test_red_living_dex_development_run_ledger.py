from __future__ import annotations

from pathlib import Path

from test_red_living_dex_clustered_development_execution import _fixture, _model

from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    run_red_living_dex_clustered_development_assignment,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RedLivingDexDevelopmentBatchAssignment,
)
from pokemon_red_completion.red_living_dex_development_run_ledger import (
    find_red_living_dex_development_run_terminal,
    retain_red_living_dex_development_run_terminal,
)


def test_development_run_terminal_closes_one_root_idempotently(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )
    model = _model()
    receipt = run_red_living_dex_clustered_development_assignment(
        selection=frozen.selection,
        binding=frozen.binding,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        producer_execution_identity=frozen.producer_execution_identity(),
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )
    assignment = RedLivingDexDevelopmentBatchAssignment(
        frozen.binding,
        frozen.selection.ordinal,
        capability.root.root,
    )

    retained = retain_red_living_dex_development_run_terminal(
        store,
        assignment,
        receipt,
    )
    again = retain_red_living_dex_development_run_terminal(
        store,
        assignment,
        receipt,
    )

    assert retained == again
    assert find_red_living_dex_development_run_terminal(store, assignment) == retained
    assert retained.retry_allowed is False
    assert retained.public_dict()["path_fields"] == 0
