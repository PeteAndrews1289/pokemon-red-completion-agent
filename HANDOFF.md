# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Teacher-only battle practice factory: first slice verified

Pete authorized teacher interventions for training and asked for a reusable
battle factory. The [factory evidence](docs/evidence/red-teacher-battle-practice-factory-2026-09-17.json)
records a title-neutral practice specification, a private Red adapter, an
authenticated generated capture, and one four-way cartridge outcome measurement.
The supported controls are actor move IDs/PP and opponent current HP. Species,
levels, derived stats, status, opponent moves, items and trainer AI are not yet
supported and fail closed. The model never receives a state-edit action.

One generated train battle preserved the original species/levels and set four
moves (Tackle, Strength, Ice Beam, Guillotine) with declared PP. Materialization
used zero controller actions and frames. With identical 2,048-frame pre-attack
timing, Tackle dealt about 79.2% of the opponent's HP; the other three moves
knocked it out. The frozen model chose Guillotine, which succeeded at this one
RNG timing. This is an informative assisted configuration, not evidence of a
model gain, reliable Guillotine judgment, a new independent root, or transfer.
No fit or promotion occurred. The source save was unchanged.

Next: expand one coherent battle axis, preferably a species/level/stat package,
with strict cartridge readback and bounded execution before generating a
curriculum. Then vary configurations and RNG, fit only on train data, and
compare against frozen and fixed-heuristic controls on untouched natural
development roots. Do not relabel sibling generated configurations as
independent roots or use assisted results for Red completion. No full run or
GitHub push.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. Recommended next: Sol High, Fast off, 90–120 minutes for
one coherent additional generation axis and a bounded real-ROM qualification.
