"""Training receipts for the first semantic whole-game planner."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.planner_dataset import PlannerEpisodeDataset
from pokemon_red_completion.planner_model import (
    ObjectiveRanker,
    planner_accuracy,
)
from pokemon_red_completion.trajectory import canonical_sha256


class PlannerTrainingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlannerTrainingResult:
    model: ObjectiveRanker
    model_sha256: str
    training_accuracy: float
    decisions: int
    promotion_eligible: bool = False

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "planner-diagnostic-training-receipt-v1",
            "model_sha256": self.model_sha256,
            "decisions": self.decisions,
            "training_accuracy": self.training_accuracy,
            "promotion_eligible": self.promotion_eligible,
            "limitations": [
                "single_unassigned_lineage",
                "no_held_out_full_game_evaluation",
            ],
        }


def train_diagnostic_objective_ranker(
    dataset: PlannerEpisodeDataset,
    *,
    seed: int = 1289,
    epochs: int = 2500,
) -> PlannerTrainingResult:
    """Fit one diagnostic model without claiming autonomous promotion."""

    if not isinstance(dataset, PlannerEpisodeDataset):
        raise TypeError("dataset must be a PlannerEpisodeDataset")
    if dataset.partition != "unassigned":
        raise PlannerTrainingError("diagnostic planner training requires an unassigned lineage")
    examples = tuple(
        (example.features.candidate_vectors, example.chosen_candidate_index)
        for example in dataset.examples
    )
    model = ObjectiveRanker.fit(
        feature_names=dataset.feature_names,
        examples=examples,
        seed=seed,
        epochs=epochs,
    )
    return PlannerTrainingResult(
        model=model,
        model_sha256=canonical_sha256(model.to_dict()),
        training_accuracy=planner_accuracy(model, examples),
        decisions=len(examples),
    )
