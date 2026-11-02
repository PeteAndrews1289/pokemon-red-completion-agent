"""ROM-free repair for the saved overnight audit's historical context classifier.

The frozen experiment source and collected outcomes are untouched. Historical
prompt/forced records have no move head, so they must be classified separately.
"""

from __future__ import annotations

import json
from collections import Counter
from statistics import fmean

import run_red_damage_proposal_overnight as packet

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel


def classify_retention_record(record: dict, catalog: PokemonRedBattleCatalog) -> str:
    head = record.get("heads", {}).get("move")
    if head is None:
        return "no_move_head:" + record["decision_context"]
    flags = set()
    moves = record["observation"]["features"]["party"]["lead"]["moves"]
    for ref in head["choice_refs"]:
        if ":move:" not in ref:
            flags.add("non_move_action")
            continue
        slot = int(ref.rsplit(":", 1)[1])
        if not 1 <= slot <= len(moves):
            flags.add("unresolved_slot")
            continue
        move_ref = moves[slot - 1].get("move_ref")
        if not isinstance(move_ref, str):
            flags.add("unresolved_move")
        elif not catalog.recovery_attack_supported(move_ref):
            flags.add("excluded_mechanic_or_status")
        elif catalog.resolve_move(move_ref).effect_flags & packet.EXCLUDED_FLAGS:
            flags.add("excluded_mechanic")
    return "+".join(sorted(flags)) if flags else "supported_damage_inventory"


def retention_audit_fixed() -> dict:
    catalog = PokemonRedBattleCatalog()
    _, _, _, k, _ = packet.inputs()
    candidate = TrainerPracticeThreeHeadModel.from_dict(
        json.loads((packet.OUTPUT / "candidate-model.json").read_bytes())
    )
    diagnostic_dir = packet.PRIVATE / "red-damage-ranking-diagnostic-20260922-v1"
    diagnostic = json.loads((diagnostic_dir / "result.json").read_bytes())
    rows = []
    for item in diagnostic["results"]:
        vectors = tuple(tuple(v) for v in item["vectors"])
        values = tuple(item["mean_damage"])
        rows.append(
            {
                "id": item["id"],
                "baseline_regret": max(values) - values[k.move.predict_index(vectors)],
                "candidate_regret": max(values)
                - values[candidate.damage_reference.predict_index(vectors)],
            }
        )
    baseline = fmean(row["baseline_regret"] for row in rows)
    fitted = fmean(row["candidate_regret"] for row in rows)
    diagnostic_group = {
        "records": len(rows),
        "outcome_unit": "foe maximum HP fraction",
        "baseline_mean_regret": baseline,
        "candidate_mean_regret": fitted,
        "regression": fitted - baseline,
        "historical_opened_TRAIN_not_unseen": True,
        "passes_0_02_regression_limit": fitted - baseline <= 0.02,
        "source_sha256": packet.sha(diagnostic_dir / "result.json"),
        "cases": rows,
    }
    corpus_path = packet.PRIVATE / "red-trainer-J-canonical-20260920-v1/audited-targets.json"
    corpus = json.loads(corpus_path.read_bytes())
    groups = {}
    totals = Counter()
    for group, records in corpus["retention"].items():
        counts = Counter()
        for record in records:
            category = classify_retention_record(record, catalog)
            counts[category] += 1
            totals[category] += 1
        groups[group] = {
            "records": len(records),
            "classification": dict(counts),
            "outcome_unit": "historical battle utility",
            "comparable_foe_hp_damage_regret": False,
        }
    return {
        "supported_domain_groups": {
            "prior_damage_diagnostic": diagnostic_group,
            "historical_utility_groups": groups,
        },
        "excluded_mechanic_groups": dict(totals),
        "historical_corpus_sha256": packet.sha(corpus_path),
        "gate": (
            "unmet_missing_comparable_damage_groups"
            if diagnostic_group["passes_0_02_regression_limit"]
            else "failed_prior_damage_diagnostic_regression"
        ),
        "mixed_units_kept_separate": True,
        "unsupported_domain_general_replacement_blocked": True,
        "new_native_runs": 0,
    }


def main() -> None:
    if (packet.OUTPUT / "AUDIT.json").exists():
        raise ValueError("saved audit already exists")
    # Both preflights are read-only. The packet writes each final audit artifact once.
    retention_audit_fixed()
    packet.failure_trace()
    packet.retention_audit = retention_audit_fixed
    audit = packet.audit_saved()
    packet.write_once(
        packet.OUTPUT / "AUDIT_REPAIR_RECEIPT.json",
        {
            "schema": "pokemon.red.damage-audit-repair.v1",
            "cause": "historical prompt and forced records have no move head",
            "repair_cycles_for_cause": 1,
            "experiment_source_unchanged": True,
            "new_native_runs": 0,
            "fit_attempts_added": 0,
            "original_audit_failure_preserved": packet.sha(packet.OUTPUT / "audit-failure.json"),
            "audit_sha256": packet.sha(packet.OUTPUT / "AUDIT.json"),
        },
    )
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
