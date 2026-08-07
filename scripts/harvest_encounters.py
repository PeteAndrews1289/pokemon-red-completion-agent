import json
from collections import defaultdict
from pathlib import Path


def main():
    encounters_file = Path("encounters.jsonl")
    if not encounters_file.exists():
        print(f"Error: {encounters_file} not found.")
        return

    # Map map_id -> min_level, max_level
    map_levels = defaultdict(lambda: {"min": 100, "max": 0})

    with encounters_file.open("r") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            map_id = entry["map_id"]
            enemy_level = entry["enemy_level"]
            
            if enemy_level < map_levels[map_id]["min"]:
                map_levels[map_id]["min"] = enemy_level
            if enemy_level > map_levels[map_id]["max"]:
                map_levels[map_id]["max"] = enemy_level

    # Generate Python code
    out_lines = [
        '"""Harvested encounter bands from instrumented run."""',
        "",
        "from pokemon_red_completion.domain import MapId",
        "from pokemon_red_completion.team_training import GrindingArea",
        "",
        "HARVESTED_AREAS: tuple[GrindingArea, ...] = (",
    ]

    for map_id, levels in sorted(map_levels.items()):
        out_lines.append("    GrindingArea(")
        out_lines.append(f"        map_id=MapId({map_id}),")
        out_lines.append(f"        min_enemy_level={levels['min']},")
        out_lines.append(f"        max_enemy_level={levels['max']},")
        out_lines.append("    ),")
    
    out_lines.append(")")
    out_lines.append("")

    out_path = Path("src/pokemon_red_completion/encounter_bands.py")
    out_path.write_text("\n".join(out_lines))
    print(f"Successfully wrote {len(map_levels)} areas to {out_path}.")

if __name__ == "__main__":
    main()
