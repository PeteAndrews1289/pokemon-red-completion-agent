from dataclasses import replace
import pytest
from test_task_return_resource_contract import fixture
from pokemon_red_completion.player_sequence_policy import SequencePolicy
from pokemon_red_completion.recorded_branch_history import PREPARATION_HISTORY


def candidate():
    model, menu, context, prior, old = fixture()
    new = replace(old, head=replace(old.head, history_contract=PREPARATION_HISTORY),
        task_return_scope="resource-pressure-positive-with-earning-peer-v2",
        supported_kinds=("acquire", "develop", "resupply"),
        sequence_utility=(old.sequence_utility[0], 0., *old.sequence_utility[2:]))
    context = replace(context, history_contract=PREPARATION_HISTORY)
    return model, menu, context, prior, old, new


def test_funded_critic_uses_observed_resource_need_and_preserves_other_choices():
    model, menu, context, prior, old, new = candidate()
    menu = replace(menu, context=replace(menu.context, resource_pressure=.25))
    context = replace(context, menu_sha256=menu.policy_sha256)
    legacy = context.for_history_contract(menu, prior.head.history_contract)
    before = prior.scores(model, menu, legacy)
    after = new.scores(model, menu, context)
    assert after[:3] != before[:3] and after[3:] == before[3:]
    assert old.scores(model, menu, legacy) == before
    assert menu.available_indices == (0, 1, 2, 3)
    assert SequencePolicy.from_document(new.document(), expected_sha256=new.model_sha256) == new
    assert new.sequence_utility[1] == 0.0


@pytest.mark.parametrize("fault", ["pressure", "earning", "economy"])
def test_unsupported_contexts_keep_exact_prior_scores(fault):
    model, menu, context, prior, old, new = candidate()
    if fault == "pressure": menu = replace(menu, context=replace(menu.context, resource_pressure=0.))
    if fault == "economy": menu = replace(menu, context=replace(menu.context, economy_snapshot=None, target_cash=None),
        candidates=tuple(replace(c, economy_offer=None) for c in menu.candidates))
    if fault == "earning": menu = replace(menu, candidates=(menu.candidates[0], *menu.candidates[2:]))
    context = replace(context, menu_sha256=menu.policy_sha256, histories=context.histories[:len(menu.candidates)])
    assert new.scores(model, menu, context) == prior.scores(model, menu, context.for_history_contract(menu, prior.head.history_contract))


def test_new_scope_cannot_impute_quests_or_silently_use_legacy_zero_history():
    *_, new = candidate()
    with pytest.raises(ValueError): replace(new, sequence_utility=(4., 4., *new.sequence_utility[2:]))
    with pytest.raises(ValueError): replace(new, head=replace(new.head, history_contract="story-branch-history-v1"))


def test_observed_capture_peers_share_the_task_return_and_legality_is_unchanged():
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
    model, menu, context, prior, old, new = candidate()
    menu = replace(menu, candidates=(replace(menu.candidates[0], preparation=None,
        features=replace(menu.candidates[0].features,kind=LivingDexOptionKind.ACQUIRE)), *menu.candidates[1:]))
    context = replace(context, menu_sha256=menu.policy_sha256)
    scores = new.scores(model,menu,context)
    forecast = new.head.score_menu(menu,histories=context.histories,utility=new.sequence_utility)
    assert scores[:3] == forecast[:3]
    assert menu.available_indices == (0,1,2,3)
