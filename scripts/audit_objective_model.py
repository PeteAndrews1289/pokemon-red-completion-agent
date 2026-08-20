#!/usr/bin/env python3
"""Audit an authenticated objective model across reachable branching states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.planner_evaluation import audit_objective_ranker
from pokemon_red_completion.planner_model import load_objective_model_artifact
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.quest import quest_graph_payload
from pokemon_red_completion.route import COMPLETION_QUEST


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded counterfactual audit for a private planner model."
    )
    parser.add_argument("model", type=Path, help="Authenticated private planner artifact.")
    parser.add_argument(
        "--include-cases",
        action="store_true",
        help="Include every synthetic branching evaluation in the JSON output.",
    )
    args = parser.parse_args()
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    model = load_objective_model_artifact(
        args.model,
        expected_feature_names=projector.feature_names,
        expected_objective_graph_sha256=collection_document_sha256(
            objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
        ),
    )
    report = audit_objective_ranker(model, COMPLETION_QUEST)
    print(
        json.dumps(report.public_dict(include_cases=args.include_cases), indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
