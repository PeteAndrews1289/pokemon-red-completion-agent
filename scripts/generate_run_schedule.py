import argparse
import itertools
import json
import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_path))

from pokemon_red_completion.pokedex import LivingDex, plan_next_run  # noqa: E402
from pokemon_red_completion.red_pokedex import (  # noqa: E402
    DOJO_PRIZES,
    EEVEE_EVOLUTIONS,
    FOSSIL_LINES,
    STARTER_LINES,
    RedRunChoices,
    red_target,
)


def generate_schedule(output_dir: Path | None = None) -> list[dict]:
    starters = list(STARTER_LINES.keys())
    fossils = list(FOSSIL_LINES.keys())
    dojo_prizes = list(DOJO_PRIZES.keys())
    eeveelutions = list(EEVEE_EVOLUTIONS.keys())

    candidates = {}

    for s, f, d, e in itertools.product(starters, fossils, dojo_prizes, eeveelutions):
        choices = RedRunChoices(starter=s, fossil=f, dojo_prize=d, eevee_evolution=e)
        name = f"{s}-{f}-{d}-{e}"
        candidates[name] = red_target(choices)

    living = LivingDex()
    schedule = plan_next_run(living, candidates)

    runs = []
    total_caught = 0
    for i, (name, gain) in enumerate(schedule, 1):
        total_caught += len(gain)
        s, f, d, e = name.split("-")
        run_config = {
            "run_index": i,
            "choices": {
                "starter": s,
                "fossil": f,
                "dojo_prize": d,
                "eevee_evolution": e,
            },
            "expected_gain": len(gain),
            "total_caught_after_run": total_caught,
        }
        runs.append(run_config)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        schedule_path = output_dir / "red_multi_run_schedule.json"
        with schedule_path.open("w") as f:
            json.dump({"runs": runs}, f, indent=2)
        print(f"Schedule written to {schedule_path}")

    return runs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate multi-run schedule for Pokédex completion"
    )
    parser.add_argument(
        "--out", type=Path, default=Path("configs"), help="Output directory for schedule"
    )
    args = parser.parse_args()
    runs = generate_schedule(args.out)
    for run in runs:
        print(f"Run {run['run_index']}: {run['choices']} -> {run['expected_gain']} new species")
