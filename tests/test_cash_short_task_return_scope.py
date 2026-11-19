from dataclasses import replace
import pytest
from test_funded_task_return_scope import candidate
from pokemon_red_completion.player_sequence_policy import SequencePolicy

@pytest.mark.parametrize("cash", [0, 8, 999, 1000, 1001, 36625])
def test_cash_support_boundary_preserves_all_actions_and_existing_scopes(cash):
    model, menu, context, prior, old, v2 = candidate()
    v3 = replace(v2, task_return_scope="cash-short-resource-pressure-with-earning-peer-v3")
    menu = replace(menu, context=replace(menu.context,
        economy_snapshot=replace(menu.context.economy_snapshot, cash=cash), target_cash=1000))
    context = replace(context, menu_sha256=menu.policy_sha256)
    v2_scores = v2.scores(model, menu, context)
    retained = prior.scores(model, menu, context.for_history_contract(menu, prior.head.history_contract))
    assert v3.scores(model, menu, context) == (v2_scores if cash < 1000 else retained)
    assert menu.available_indices == (0, 1, 2, 3)
    assert v3.head == v2.head and v3.retained_policy == v2.retained_policy
    assert SequencePolicy.from_document(v3.document(), expected_sha256=v3.model_sha256) == v3
    if cash >= 1000: assert v2_scores != retained

@pytest.mark.parametrize("fault", ["pressure", "earning", "economy"])
def test_cash_short_scope_still_requires_all_prior_public_support(fault):
    model, menu, context, prior, old, v2 = candidate()
    v3 = replace(v2, task_return_scope="cash-short-resource-pressure-with-earning-peer-v3")
    if fault == "pressure": menu = replace(menu, context=replace(menu.context, resource_pressure=0.))
    if fault == "economy": menu = replace(menu, context=replace(menu.context, economy_snapshot=None, target_cash=None), candidates=tuple(replace(c, economy_offer=None)for c in menu.candidates))
    if fault == "earning": menu = replace(menu, candidates=(menu.candidates[0], *menu.candidates[2:]))
    context = replace(context, menu_sha256=menu.policy_sha256, histories=context.histories[:len(menu.candidates)])
    assert v3.scores(model, menu, context) == prior.scores(model, menu, context.for_history_contract(menu, prior.head.history_contract))
