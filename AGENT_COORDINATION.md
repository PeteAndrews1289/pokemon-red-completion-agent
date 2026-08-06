# Three-agent coordination

Read [MISSION.md](MISSION.md) first. This document is about *who does what* and *how not to collide*.

Three agents work this repository: **Claude**, **Codex**, and **Antigravity**. Most collisions
between them are mechanical rather than intellectual, and the rules below exist because the
mechanical ones are what actually cost time.

## Repository topology

There is more than one checkout. Know which you are in before you touch anything.

| Worktree | Branch | Role |
| --- | --- | --- |
| `pokemon-red-completion-agent` | `agent/battle-evaluation-protocol` | Original checkout. Stale, ~90 commits behind. Do not work here. |
| `pokemon-red-completion-agent-claude` | `agent/balanced-team-curriculum` | **Trunk.** All integration lands here. |
| `pokemon-red-completion-agent-v44-eval` | detached at `c0dbbc6` | Frozen source for the v44 evaluation campaign. Never edit or check out. |
| `pokemon-red-learning-next` | `agent/learned-navigation` | Learning lane. Its work through `7dffe30` is now integrated into trunk. |

**Git forbids two worktrees sharing one branch**, so "everyone in one worktree" and "agents working
in parallel" cannot both be true. The workable arrangement is one *trunk branch* plus short-lived
side branches that integrate often:

- `agent/balanced-team-curriculum` is trunk. Everything lands here.
- Work directly on trunk when you are the only agent active. It is the simplest thing that works.
- When two agents are active at once, the second takes a short-lived branch in its own worktree and
  integrates **before it exceeds roughly five commits or one working day**.

That threshold is not arbitrary. `agent/learned-navigation` branched off trunk and was left alone
while trunk moved 90 commits ahead. Integrating four commits then required skipping two of them and
resolving conflicts across six files. Four commits, integrated the same day, would have been a
fast-forward.

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

`tests/test_collection_protocol.py` is therefore the highest-collision file in the repo, and any two
branches that both touched `src/` **will** conflict there by construction.

**Never resolve a golden-hash conflict by hand.** Take either side, then re-run
`regenerate_collection_registry.py` and update the four values from its output. The hashes are
derived, not authored, so hand-merging them produces a plausible file that fails the check. This
turns a frightening conflict into a mechanical step.

The same applies to the registry-version bump commits (`Freeze … collection source`, which rename
`configs/red-battle-collection-vNN.json` and update the matching identifiers). Those are bookkeeping
local to whichever branch made them. When integrating, **skip them and regenerate once at trunk's
current version** rather than replaying a version the trunk has already passed.

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

## Do not

- **Do not restore the multi-target Route 22 continuation loop.** It was implemented, replayed
  against the exposed seed, and reverted after it cycled every reserve into Venusaur until the party
  reached `(0, 0, 0, 0, 0, 0)`. "Continue until the living roster is exhausted" is the failure, not
  the fix. The V35 receipt preserves it as `rejected_repair_direction`.
- **Do not treat a green `passed` as evidence the thing it is named after happened.** Two examples
  are already in the record: `team_development.passed` never looked at five of six party members,
  and twelve receipts reported the opponent's party levels as ours.
- **Do not use the party as disposable HP.** Switching to a healthy teammate is strategy; feeding
  a weak one in to absorb a hit is the behaviour V35 exposed. `ROUTE_22_PIVOT_MIN_HP_RATIO` and
  `ROUTE_22_MAX_TEAM_PIVOTS` make the wipe structurally unreachable — keep it that way.
- **Do not describe the objective ranker as an autonomous player.** It runs as
  `model_authorized_fixed_specialists`: it selects among 36 objectives while fixed code executes
  them. Zero teacher fallbacks is a real result and is not the same claim.

## Private inputs

The ROM, the private artifact root, and the objective-model path are supplied per session by the
repository owner and must never appear in a tracked or untracked file. Ask if you do not have them.

## Honest status

The deterministic teacher completes Pokémon Red repeatedly with genuine Champion and Hall-of-Fame
evidence in the same run. The objective ranker authorizes all 36 objectives with zero fallbacks. The
team can now be trained to League parity at a measured cost of roughly 1,878 battles.

The team still does not participate in battles — the escort does everything. No learned policy has
completed the game, no cross-game transfer has been measured, and the living Pokédex has not been
started. The blocker is not game completion; it is that the demonstrations contain very few real
decisions, and more Red reliability does not change that.

## The full gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/pytest -m "not integration"
```

Current state: **1830 passed, 3 deselected**, all checks green, on trunk
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
