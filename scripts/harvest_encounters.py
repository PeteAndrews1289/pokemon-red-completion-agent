"""Turn a harvest log into a dated evidence file of measured encounter bands.

This deliberately writes data, not code.  The version it replaces generated a
Python module into ``src/``, which had three separate reasons never to work —
it imported ``MapId`` from a module that does not define it, constructed
``GrindingArea`` with three keyword arguments it does not accept, and read a
log path nothing ever wrote to.  None of that surfaced, because generating the
file and importing the file were different acts and only the first was ever
performed.

Writing evidence instead also keeps the source-binding rule intact: generated
code under ``src/`` would restale the collection registry on every harvest,
so a measurement would be indistinguishable from a change in behaviour.

Usage::

    POKEMON_RED_ENCOUNTER_LOG=<path> ...take a run...
    python scripts/harvest_encounters.py <path> [--out docs/evidence/...]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.encounters import (  # noqa: E402
    MINIMUM_TRUSTED_SAMPLES,
    TYPICAL_ENCOUNTER_SHARE,
    EncounterLogError,
    read_encounter_log,
    summarize_encounters,
)
from pokemon_red_completion.observation import MapId  # noqa: E402

SCHEMA = "pokemon-encounter-band-measurement-v1"


def area_name(map_id: int) -> str:
    try:
        return MapId(map_id).name.lower()
    except ValueError:
        return f"unmapped_{map_id:#04x}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="the harvest log written during a run")
    parser.add_argument("--out", type=Path, default=None, help="evidence file to write")
    parser.add_argument("--recorded-on", default=date.today().isoformat(), help="measurement date")
    args = parser.parse_args(argv)

    try:
        bands = summarize_encounters(read_encounter_log(args.log))
    except EncounterLogError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if not bands:
        print("error: the log holds no wild encounters", file=sys.stderr)
        return 1

    trusted = [band for band in bands if band.is_trusted]
    evidence = {
        "schema": SCHEMA,
        "recorded_on": args.recorded_on,
        "method": (
            "Measured from wild encounters the agent really had. Trainer battles are "
            "excluded because they share the battle flag but not the level distribution, "
            "and reads taken before battle memory settles are excluded because they "
            "report species zero at level zero."
        ),
        "typical_encounter_share": TYPICAL_ENCOUNTER_SHARE,
        "minimum_trusted_samples": MINIMUM_TRUSTED_SAMPLES,
        "areas_measured": len(bands),
        "areas_trusted": len(trusted),
        "bands": [{"area": area_name(b.map_id), **b.as_record()} for b in bands],
    }

    out = args.out or Path("docs/evidence") / f"encounter-bands-{args.recorded_on}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print(f"{len(bands)} areas measured, {len(trusted)} with enough samples to trust:")
    for band in bands:
        mark = " " if band.is_trusted else "?"
        rare = f" (rare to {band.observed_maximum_level})" if band.has_rare_ceiling else ""
        print(
            f" {mark} {area_name(band.map_id):<26} n={band.samples:<4} "
            f"{band.minimum_level}-{band.typical_maximum_level}{rare}"
        )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
