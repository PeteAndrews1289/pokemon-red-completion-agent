from dataclasses import replace

import numpy as np
import pytest
from audit_red_outcome_value_pilot import verify_frozen
from test_red_outcome_value_learning import setup


@pytest.mark.parametrize("mutation", ["hidden", "bias", "effect", "control", "ancestry"])
def test_audit_rejects_changed_frozen_components(mutation):
    _, actor, targets, _, _ = setup()
    assert actor.damage_reference is not None
    candidate = replace(actor, train_capture_ids=(*actor.train_capture_ids, "new"))
    verify_frozen(candidate, actor, targets)
    if mutation == "hidden":
        candidate = replace(candidate, move=replace(candidate.move,
            weights1=candidate.move.weights1+np.ones_like(candidate.move.weights1)*.01))
    elif mutation == "bias":
        candidate = replace(candidate, move=replace(candidate.move, bias1=candidate.move.bias1+.01))
    elif mutation == "effect":
        candidate = replace(candidate, move=replace(candidate.move,
            effect_weights=tuple(x+.01 for x in candidate.move.effect_weights)))
    elif mutation == "control":
        candidate = replace(candidate, control=replace(candidate.control,
            weights2=candidate.control.weights2+.01))
    else:
        candidate = replace(candidate, train_capture_ids=(*candidate.train_capture_ids, "heldout"))
    with pytest.raises(ValueError, match="frozen components"):
        verify_frozen(candidate, actor, targets)
