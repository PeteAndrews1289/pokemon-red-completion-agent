"""Reconcile retained natural qualification outcomes with zero gameplay inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from continue_red_natural_party import bound
from run_red_natural_six_qualification import MODELS, SOURCES, actual_slots, summarize
from run_red_six_party_assisted_pilot import binding, write_new
from run_red_trainer_earned_switch import completion_ledger
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


def audit(directory):
    freeze = json.loads((directory / "execution-freeze.json").read_bytes())
    original = json.loads((directory / "plan.json").read_bytes())
    sources = {s["boot"]: s for s in original["sources"]}
    rows, proofs = [], []
    for ref in freeze["cells"]:
        plan = json.loads(bound(Path(ref["path"]), ref["sha256"]))
        output = Path(plan["output"])
        parts = output.name.split("-")
        boot, timing, arm = int(parts[0][4:]), int(parts[1][6:]), parts[2]
        if (plan["outcome_model"]["sha256"] != MODELS[arm]
                or plan["capture_state"]["sha256"] != SOURCES[boot][0]
                or plan["opening_idle_frames"] != timing):
            raise ValueError("frozen source/model/cell differs")
        for name in ("rom", "outcome_model", "capture_state", "capture_manifest"):
            bound(Path(plan[name]["path"]), plan[name]["sha256"])
        row = json.loads((output / "outcome.json").read_bytes())
        log = verify_trainer_practice_event_log(output / "events")
        terminal = json.loads(sorted((output / "events").glob("event-*.json"))[-1].read_bytes())
        if (terminal["payload"]["outcome"]["outcome_sha256"] != canonical_sha256(row)
                or row["source_commit"] != plan["source_commit"]
                or log["completed_decisions"] != row["decision_count"]
                or row["final_state_sha256"] != binding(output / "final.state")["sha256"]):
            raise ValueError("retained log/outcome/endpoint binding differs")
        row["log_verified"] = log["terminal_event"] == "run_finished" and log["incomplete_decisions"] == 0
        row["final_state_verified"] = True
        row["actual_slots"] = actual_slots(row)
        with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
            emulator.load_state_bytes((output / "final.state").read_bytes())
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            row["final_ledger"] = completion_ledger(reader)
            row["cash_delta"] = raw.player_money - sources[boot]["before"]["cash"]
            if row["battle_won"] and (raw.battle_state != 0 or row["cash_delta"] != 210):
                raise ValueError("claimed victory differs from actual field/payout")
            if tuple(raw.party_hp).count(0) != row["metrics"]["party_faints"]:
                raise ValueError("retained persistent faints disagree")
            assert emulator.frame_count == 0
        row.update(boot=boot, timing=timing, arm=arm)
        write_new(directory / f"verified-cell-{len(rows)+1:02}.json", row)
        rows.append(row)
        proofs.append({"boot": boot, "timing": timing, "arm": arm,
            "outcome": binding(output / "outcome.json"), "endpoint": binding(output / "final.state"),
            "events": log["event_count"], "terminal_event_chain_sha256": log["last_record_sha256"],
            "decisions": row["decision_count"], "actual_slots": row["actual_slots"],
            "cash_delta": row["cash_delta"], "final_hp": row["final_ledger"]["party_hp"]})
    result = {**summarize(rows), "execution_freeze": binding(directory / "execution-freeze.json"),
        "original_postprocessing_failure": binding(directory / "result.json"),
        "postprocessing_correction": "Ignore the empty active slot after battle exit; audit original logs and endpoints. No replay or outcome mutation.",
        "audit_frames": 0, "audit_controller_actions": 0, "proofs": proofs}
    write_new(directory / "verified-result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    audit(parser.parse_args().directory)
