# Three-agent coordination

Read [MISSION.md](MISSION.md) first. This document is about *who does what* and *how not to collide*.

Three agents work this repository: **Claude**, **Codex**, and **Antigravity**. They share one branch
and one emulator, which means most collisions are mechanical rather than intellectual. The rules
below exist because those mechanical collisions are the expensive ones.

## Lanes

Pick a lane per session and say which one you are in. Lanes are about *ownership of files*, not
about who is smart enough to do what.

### Lane A — Route and emulator

Owns `src/pokemon_red_completion/` chapter modules (`blaine.py`, `victory_road.py`, `champion.py`,
`fuchsia.py`, and every other chapter), and owns emulator runs.

Only Lane A launches the emulator. A clean-power replay currently takes 6–7 minutes for the baseline
route and roughly 25 minutes with the balancing pass enabled. Two concurrent runs contend for CPU and
make every timing measurement meaningless.

### Lane B — Contracts and policy

Owns the game-neutral modules: `party.py`, `team_training.py`, `capture.py`, `pokedex.py`,
`training.py`, and their adapters `red_party.py`, `red_pokedex.py`.

This lane never needs the ROM. Everything here is ROM-free and unit-testable, so it can run in
parallel with a long Lane A replay.

### Lane C — Evidence, measurement and documentation

Owns `docs/`, `docs/evidence/`, receipts, narrative, and audits of what the metrics actually claim.

This lane found the largest defect in the project so far (see MISSION.md). Treat it as real work, not
as writing up someone else's.

## Collision rules

**The registry restales on any `src/` change.** Adding or editing a source file changes
`source_bundle_sha256`. Whoever touches `src/` must, in the *same commit*:

```bash
.venv/bin/python scripts/regenerate_collection_registry.py
# then update the four golden values in tests/test_collection_protocol.py:
#   registry_sha256, source_bundle_sha256, teacher_execution_sha256, first assignment_id
```

Verify only the two source-digest fields moved and all twelve slot records stayed byte-identical.
`tests/test_collection_protocol.py` is therefore the highest-collision file in the repo — expect to
rebase, and never merge two branches that both touched it without re-regenerating afterward.

**Never open a counted evaluation seed.** Preregistered validation and sealed test seeds are
one-attempt-only. Exposed diagnostic seeds are unlimited. V35 is retired: do not touch validation
seeds `1810002`–`1810005` or sealed test seeds `1820001`–`1820005`. Seed `1810001` is exposed and
diagnostic-only.

**Do not preregister a new evaluation version yet.** V33, V34 and V35 each died on a different
specialist boundary within one or two validation seeds. That gate currently measures route
brittleness, not learned capability, and each version burns ten sealed seeds to discover one bug.
Use exposed batches until the tail thins.

**Keep private paths out of the tree.** `scripts/check_public_artifacts.py` scans the whole working
tree with `rglob` and ignores `.gitignore`, so an *untracked* note containing a home-directory path
fails the gate with exit 1. Supply the ROM path, private artifact root, and objective-model path via
environment, never in a file.

## The full gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/pytest -m "not integration"
```

Current state: **1819 passed, 3 deselected**, all checks green, branch
`agent/balanced-team-curriculum`.

## Open work, in priority order

These are ordered by how much they serve the mission, not by difficulty.

**1. Cap the escort. (Lane A)** The switch-participation mechanism trains a weak member by sending
it in beside a strong escort, but the escort gains experience from every one of those battles. A
measured run left the Mansion with the escort at 83 and reached the Champion at 87, one-shotting the
entire League team in six turns. Training the team currently *widens* the gap it is meant to close.
Until the escort stops gaining at parity — or trainees fight unescorted once safe — no amount of
levelling produces decisions.

**2. Measure participation directly. (Lane C)** Turns-per-party-member across the Elite Four is a
one-line metric and it would have caught the above on the first run. Six turns, one member, is
visible immediately. Add it beside the existing `team_balance` block.

**3. Resolve the tolerance conflict. (Lane B)** `MANSION_LEVEL_PARITY` uses `max_levels_behind=10`
(target 55) while `CHAMPION_LEVEL_PARITY` uses `5` (required 60), so the receipt reports a team that
*won the game* as five levels short. One contract, one number.

**4. Turn the balance assertion on. (Lane B, after 1)** `DevelopedTeamReport.passed` asserts a
complete roster, one trained workhorse, and zero faints — nothing about the other five members. It
is deliberately reporting-only today because enabling it fails every run. That failure is correct,
but switch it on knowingly.

**5. Distribute training across the route. (Lane A)** Members acquired at Fuchsia, Saffron and the
Dojo should earn experience from acquisition onward instead of closing the whole gap in one late
block. Cheaper, and closer to how the game is actually played.

**6. Start the second-game adapter — battle layer only. (Lane B)** `party.py`, `team_training.py`,
`capture.py` and `pokedex.py` all *claim* game-neutrality and nothing has ever falsified that claim.
Moving the battle observation contract to one other title will teach more about transfer readiness
than another ten Red runs.

**7. Plan multi-run dex coverage. (Lane B/C)** `red_target(RedRunChoices(...))` and
`plan_next_run()` exist. Two opposed Red runs reach 132 of 151; the remaining nineteen are ten Blue
exclusives, four trade evolutions, Mew, the third starter line and the third Eevee stone. Red alone
needs three runs. Wire the planner to an actual run schedule.

## Recent history

Twelve commits on `agent/balanced-team-curriculum` after `5696121`. Highlights:

- `f67f690` Route 22 pivot gated on a battle-ready reserve — V35's party wipe made structurally
  unreachable rather than merely untriggered.
- `ec70c10` Twelve receipts relabelled: they recorded the Champion's fixed party levels as ours.
- `2feafcf` The balanced-team training pass was never called. Only the evolution pass ran.
- `9c2fc60` Training target derived from the League (55) rather than an internal spread that
  anchored to an overlevelled escort and cost 4,570 battles to overshoot parity by nineteen levels.
- `c5882c4`, `510a478` Pokédex contract, and the target made a function of a run's choices.
