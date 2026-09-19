"""Read-only cohort report for authenticated trainer-practice run directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.red_trainer_practice_analysis import (
    summarize_trainer_practice_runs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps(summarize_trainer_practice_runs(args.runs), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
