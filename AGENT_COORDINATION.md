# Three-agent coordination

> **2026-08-11 Lane A strategic-rehearsal checkpoint:** preserve two source-bound uncounted failed
> partials; both stopped before Tower-versus-Eevee and contain zero strategic decisions. Source
> `ab69be7` failed at 16/312 when the Forest Bug Catcher survived with 6/27 HP after Tackle reached
> zero. Source `1904b59` proved that repair, Brock and Route 3 trainer 0, then failed at checkpoint
> 23 with Squirtle at 0/35, the last opponent at 2/30, twelve protected Potions and Bubble at 30 PP.
> The first repair selects a usable Tackle/Bubble on every actionable turn and separates transient
> faint dialogue. The second removes trainer 1's lone handwritten exclusion from the required Route
> 3 Bubble policy. Exact schedule `1710001` now clears checkpoints 17 and 24 in uncounted in-memory
> diagnostics. Next: full gate, publish, exact-commit CI, then run only the newly regenerated
> rehearsal assignment. Train remains 0/5, validation 0/2, test 0/5; never overwrite either failed
> identity or open a learning root for debugging.

> **2026-08-10 Lane A Cut checkpoint:** staged Cut is live-qualified at source `8a0b794`. The
> adapter reads Red's mutable unpadded map blocks, capability requires Cascade plus a complete party
> with a living Cut holder, and cartridge swaps may select only the cutting stance. The field macro
> accepts one exact block/tile mutation with restored input; terrain and the crossing route are
> rebuilt from the observed post-action RAM grid. Celadon changed block `$35 → $4C` and tile
> `$3D → $2C`, crossed former tree `(20,47)`, returned to Center `(3,3)`, acknowledged 60/60 route
> movements, released controls and wrote no ROM-adjacent artifact. Record:
> `docs/evidence/celadon-staged-cut-route-probe-2026-08-10.json`. Next: Strength player/boulder
> search, one independently proved closed/open story gate, and targeted multi-tree Cut coverage.
> Generated routing remains outside completion-run authority; counted v95 remains sealed at 0/10.

> **2026-08-10 Lane A visible-object checkpoint:** direct current occupancy is live-qualified at
> source `1c6eb31`. The Gen I adapter reads visible non-player sprite slots and the neutral executor
> treats them as temporary replan constraints before input; settled failed steps remain the durable
> fallback. The adversarial Cinnabar probe used no ROM object positions as blockers, observed the
> stationary `(6,14)` NPC from `(6,15)`, sent no input toward it, replaced the suffix, reached
> `(6,13)`, and returned to `(12,11)`: 43/43 acknowledged movement requests, no interruption,
> released controls and no ROM-adjacent writes. Record:
> `docs/evidence/cinnabar-visible-object-route-probe-2026-08-10.json`. Next: Cut as an observed map
> mutation, then Strength and one closed/open story gate. Generated routing remains outside
> completion-run authority and counted v95 remains sealed at 0/10.

> **2026-08-10 Lane A Surf checkpoint:** stateful cartridge routing is live-qualified at source
> `0d1fc43`. The planner now searches `(coordinate, movement mode)`, enables boarding only from an
> observed Soul Badge plus a complete party with a living Surf holder, and compiles the field move
> through bounded Gen I menus. The clean post-Blaine probe exited Cinnabar Center, boarded at
> `(13,11)`, traversed two true water edges to `(16,11)`, disembarked, and returned to the exact
> `(12,11)` shore origin in land mode: 13/13 acknowledged route steps, no wild, no replan, released
> controls and no ROM-adjacent writes. Live falsification also fixed boundary-return geometry and a
> premature-replan race; do not revert the settle-before-blocker order. Record:
> `docs/evidence/cinnabar-cartridge-surf-route-probe-2026-08-10.json`. Next: direct visible-object
> projection, then Cut, Strength and one closed/open story gate. Generated routing remains outside
> completion-run authority and counted v95 remains sealed at 0/10.

> **2026-08-10 Lane A checkpoint:** the game-neutral closed-loop route executor is live-qualified at
> source `6b2cf65`. The 86-step Pallet → Viridian Center control acknowledged every movement and
> authenticated three natural wild interruptions with zero replans. The independent Mart probe
> disclosed a two-request artificial first-step block, changed its Pallet/Route 1 connection after
> replanning, then naturally routed around Route 1's moving youngster, authenticated one wild and
> entered the Mart after 108 acknowledged steps / 112 requests. The failed pre-evidence attempt also
> exposed Gen I's staggered map/coordinate transition and produced a bounded settling contract. See
> `HANDOFF.md` and `docs/traversal-audit-2026-08-10.md`. Next: Surf as explicit movement mode, then
> visible-object projection, Cut, Strength and one story gate. Do not authorize generated routing in
> a completion run yet, edit `src/` during an emulator run, or open counted v95; status remains 0/10.

> **2026-08-09 active lane:** fresh canonical seed `990015` completed 36/36 objectives and Hall of
> Fame with the exact six authenticated model roles, 3,315 battle decisions, 21/21 learned target
> bindings, both training heads in causal control, and zero battle-teacher query or fallback. The
> paired derived-timing seed `990016` then failed before any learned battle decision: its legitimate
> lab-rival win produced a legal 23-HP level-6 Squirtle while the old verifier required exactly 21,
> and 56 dialogue pulses stopped at script 13 before controls released. The gate now accepts only
> the legal 21–23 DV range while retaining the win/event/map/script/control proof, and its bounded
> pulse cap is 96. Seed `990017` passed that gate, then a normal Route 1 wild encounter hit the old
> zero-encounter corridor. Route 1 now permits eight evidence-bearing flees across the round trip
> while preserving party, level, max HP, PP, status, coordinate, and released control. Seed
> `990018` accepted two flees, then proved that the first ready-looking overworld frame could still
> swallow movement. The shared Oak/Pewter helper now waits 120 frames and revalidates the full
> receipt before returning. The 2,165-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry
> checks passed at `d3461f0`. Seed `990019` still counted one ignored north input and ended a tile
> short after five verified flees. Route 1 now acknowledges every step from directional coordinate
> progress or a map transition and retries an unchanged safe boundary under a finite envelope.
> The 2,167-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry checks passes. Commit,
> `869e9a8` passed CI. Seed `990020` then triggered a wild at the unchanged pre-step tile; the
> helper now authenticates and flees it, counts a movement retry, and reissues the same direction.
> The 2,168-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry checks passed at
> `60d0842`. Seed `990021` then remained outside the running game after its shifted fixed intro.
> A bounded state-authenticated `Start,A,A,A` recovery reached the exact input-ready bedroom in 18
> inputs plus one input-free settling wait on the same root and obtained Squirtle; any other started
> map fails closed. The full 2,180-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry
> checks passed at `3f11647`, which also passed CI. Seed `990022` qualified the intro recovery and
> then hit an incidental battle at Route 2 forest-gate step 25. The shared traversal now takes an
> explicit expected map; only that Route 2 corridor opts into four authenticated flees, while
> trainers and drift remain fatal. The 2,181-test ROM-free gate plus Ruff, mypy, docs, privacy, and
> registry checks passes. Commit, push, then run a fresh uncounted
> perturbation. Seed `990023` qualified Route 2 and then met an incidental Forest wild at training
> step 65 before the first planned Kakuna. Every Forest travel segment now shares one cumulative
> authenticated flee budget while the three Kakuna and Bug Catcher remain fight contracts; upper
> and lower Route 2 share their own cumulative budget. The 2,182-test ROM-free gate plus Ruff,
> mypy, docs, privacy, and registry checks passed at `26fd5e6`. Seed `990024` then proved those
> repairs but the fixed first-Kakuna wait produced no battle. All three lessons now seek observed
> species `0x71` under a bounded origin-return loop, budget non-target flees, and publish attempts
> and identities. The 2,185-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry checks
> passed at `e579e76`. Seed `990025` then reached the source-known Route 1 youngster block at
> `(14,14)`. The shared traversal now reuses the exact east-yield/restore/north-cross maneuver under
> a 24-attempt bound while preserving wild receipts. The 2,186-test ROM-free gate plus Ruff, mypy,
> docs, privacy, and registry checks passes. Commit, push, then use a fresh root. Do
> not add `990007` to fitting, rerun retired model-test roots, build a complete Crystal route, weaken
> the curriculum lesson, or consume a counted v95 root. Counted status remains 0/10. See the
> [current audit](docs/current-audit-2026-08-09.md).

**New here? Read [HANDOFF.md](HANDOFF.md) first** — it is the complete orientation, including what
is unproven and how this codebase repeatedly fools people. Then [MISSION.md](MISSION.md) for why the
project exists. This document is about *who does what* and *how not to collide*.

Three agents work this repository: **Claude**, **Codex**, and **Antigravity**. Most collisions
between them are mechanical rather than intellectual, and the rules below exist because the
mechanical ones are what actually cost time.

## Where to work

**Every agent works in `pokemon-red-completion-agent-claude`, on `agent/balanced-team-curriculum`.**
That is trunk and it is the only working checkout. No side branches, no second worktree, no
duplicated effort.

The other checkouts on this machine exist but are not workspaces:

| Worktree | Branch | Status |
| --- | --- | --- |
| `pokemon-red-completion-agent` | `agent/battle-evaluation-protocol` | Stale, ~90 commits behind. Do not work here. |
| `pokemon-red-completion-agent-v44-eval` | detached at `c0dbbc6` | Frozen source for the v44 evaluation campaign. Never edit or check out. |
| `pokemon-red-learning-next` | `agent/learned-navigation` | Superseded. Its work is integrated into trunk as of `e7205ee`. Do not continue it. |

### One worktree means taking turns

Git forbids two worktrees from sharing a branch, so a single shared checkout is the simplest thing
that removes divergence entirely — at the cost of parallelism. **Only one agent edits at a time.**
Say which lane you are in when you start, and finish or commit before another agent begins.

This is deliberate. `agent/learned-navigation` branched off trunk and was left while trunk moved 90
commits ahead; integrating its four commits meant skipping two and resolving conflicts across six
files. The same four commits landed the same day would have been a fast-forward. The cost is not the
number of commits, it is how long they sit.

### The one rule that survives serialisation

**Do not edit `src/` while an emulator run is in flight.** A run loads its source at launch, so
edits mid-run do not change its behaviour — they change what the tree says the run *was*. The
receipt then describes a source commit that never produced it. Wait for the run, or work in `docs/`
and `tests/`.

If a genuine need for parallel work appears, take a short-lived branch in a fresh worktree and
integrate **within about five commits or one working day** — never longer.

## Lanes

Say which lane you are in when you start a session. Since only one agent edits at a time, lanes are
no longer about avoiding concurrent edits — they are about *who owns which concern*, so the same
question does not get re-answered three different ways in three sessions.

### Lane A — Route and emulator

**Status:** Clean route, v6 full-authority causal control, and portable Blaine integration are
qualified. Strategic candidate collection is the active emulator campaign.
**Owner:** @Codex

Owns `src/pokemon_red_completion/` chapter modules (`blaine.py`, `victory_road.py`, `champion.py`,
`fuchsia.py`, and every other chapter), and owns emulator runs.

Only Lane A launches the emulator. A clean-power replay takes 6–7 minutes for the baseline route and
roughly 25 minutes with the balancing pass enabled. Two concurrent runs contend for CPU and make
every timing measurement meaningless — and while a run is in flight, nobody edits `src/`.

### Lane B — Contracts and policy

Owns the game-neutral modules: `party.py`, `team_training.py`, `capture.py`, `pokedex.py`,
`training.py`, and their adapters `red_party.py`, `red_pokedex.py`.

This lane never needs the ROM. Everything here is ROM-free and unit-testable, which makes it the
safest work to pick up while a Lane A replay is finishing — as long as you stay out of `src/` until
the run reports.

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

The ROMs, the private artifact root, and the objective-model path are supplied per session by the
repository owner and must never appear in a tracked or untracked file. Ask if you do not have them.

**Two cartridges now exist.** The owner keeps both in one folder, which was renamed on 2026-08-09 —
if a remembered path stops working, that is why. Each title reads its own variable, because one
variable cannot name several cartridges and a campaign runs several:

| title | variable |
| --- | --- |
| Red | `POKEMON_RED_ROM` |
| Blue | `POKEMON_BLUE_ROM` |

Point each at the file, not the folder. `scripts/check_public_artifacts.py` walks the whole working
tree including untracked files, so a note containing either path fails the gate.

## Honest status

The deterministic teacher completes Pokémon Red repeatedly with genuine Champion and Hall-of-Fame
evidence in the same run. The objective ranker authorizes all 36 objectives with zero fallbacks.
In the portable loop it has also selected and completed twelve sequential objectives—from Rocket
Hideout through the Mansion Secret Key—through registered fixed skills with independently observed
effects and no expected labels, fallbacks, or replans. Eleven were singleton dispatches; the one true executable
branch was Koga versus Strength, and the model selected Koga at 96.41% confidence.
The separately dispatched post-Mansion Blaine skill is also live-qualified: 469,232 actions /
31,883,961 frames, 1,716 team-development battles, 885 healing trips, final-form levels
60/55/55/55/55/55, TM38, Volcano Badge, healed terminal, and a fresh Giovanni frontier. This is a
captured-state one-objective qualification, not a contiguous thirteen-step claim.
The next captured-state dispatch also qualifies Giovanni: 1,409 actions / 156,305 frames, six
declared Gym lessons, two bypasses, TM27, Earth Badge, healed six-member terminal, and a fresh
Victory Road frontier. It is not yet a contiguous fourteen-step claim.
Victory Road is separately qualified in 3,857 actions / 453,733 frames with the Route 22 rival,
seven badge gates, five boulder switches, exact League supplies, a healed Indigo terminal, and a
fresh Lorelei frontier.
Successive captured-state skills now pass Lorelei (480 actions), Bruno (328), Agatha (466), and
Lance (582). Their participation vectors are `[5,0,0,0,3,0]`, `[6,0,0,0,0,1]`,
`[0,0,4,0,2,0]`, and `[6,0,0,0,0,0]`; do not describe Lance as a team lesson.
Champion is separately qualified in 567 actions / 45,216 frames. Red couples the Champion event and
Hall-of-Fame map, so `DefeatChampionObjectiveSkill` declares `game:hall_of_fame` as an automatic
effect; do not count a second model decision. The uninterrupted integration replay now also passes:
20 dispatches, 502,175 actions, 37,369,283 frames, all 36 objectives closed, and Hall of Fame from
the authenticated Celadon capture, with no labels, fallbacks, or replans. Nineteen dispatches were
singletons. The next authority replacement is the teacher-authored training controller, not another
fixed route extension.
That replacement seam is now instrumented: `training_control.py` projects 21 identity-free features
and five phase-masked actions, `run_red_team_balancing` emits decisions before mechanics, and
`replay_training.py --out-decisions` preserves the stream. No training-control model or qualified
dataset exists yet. Collect and split complete root lineages before fitting anything.
Diagnostic lineage 01 is complete but unassigned: 48,156 decisions and a zero-faint 55-all terminal.
Its v1 private artifact SHA is `6685c889c4e5ea55c56b0194074f0c4b6b82376d40dfb8f475f7d903856f5a64`.
Do not promote it: v2 now embeds source, dirty state, root-state digest, and partition, and the new
dataset audit rejects leakage. Future counted lineages must use v2.
The class-balanced, phase-masked candidate fitter is implemented in `training_control_model.py`.
It has only synthetic tests; do not report a real model, accuracy, or promotion until v2 lineages,
shadow execution, and model-controlled execution pass.
Do not create nominally distinct roots by changing `--seed-wait-frames`. The 43-frame attempt
matched the 17-frame root digest and exact 46,687-decision sequence, so it is retained only as a
private reproducibility control. Use a reversible movement perturbation, prove unchanged semantic
checkpoint state, and require a new serialized digest before collection. Retain every accepted
root state beside its raw private stream.
v2 train lineage 01 is qualified at source `4c885d8`: stream SHA `f13f9f10...17e1aca1`, root SHA
`62f7862e...25e80c9c`, 46,687 decisions, all five actions, zero faints, all level 55, and 99.85%
novel unique action-feature pairs versus diagnostic lineage 01. Do not fit a real candidate yet;
collect at least one more train root and one validation root first.
The sanitized rejection record is
`docs/evidence/training-control-idle-wait-equivalence-2026-08-08.json`; do not count that duplicate.
The first motion-root attempt is also unqualified: it failed after 11,122 decisions when the active
trainee fainted. Its stream is diagnostic only. The teacher now checks the same retreat floor before
every move, and `replay_training.py` rejects byte-identical or semantically changed derived roots.
The repaired replay of the same motion root is qualified at source `71205a8`: 60,192 decisions,
1,740 battles, 1,017 heals, zero faints, all level 55, and 99.89% novel unique pairs versus train 01.
Collect one disjoint validation root next; do not fit before it passes.
Validation root 01 failed after 17,751 decisions / 725 wins because 33 legitimate safe exits crossed
the 32-flee feature horizon. Never rerun or count it. The repaired source removes that later raise
while retaining the early no-win mismatch and global step budget. Use a fresh validation root 02.
Validation root 02 qualified with 60,459 decisions and an all-55 zero-faint terminal. The default
candidate scored 75.62% raw / 76.91% balanced held-out accuracy with no state overlap. It is still
offline-only. Next add authenticated loading and shadow inference; do not open test roots.
Authenticated model loading and teacher-authority shadow auditing are implemented on the current
source. The real private model file digest is `8088efbf...52307f`. Collect a new unassigned shadow
root next; never treat the shadow model's predictions as execution commands.
Shadow root 01 passed with 55,904 decisions and 75.57% raw / 76.73% balanced agreement. The model
still had no authority. Fight recall is only 42.05% and 12,285 seeks became heals; bounded control
must address those measured risks without silently substituting teacher actions.
Battle-only authority is now implemented. Safe model flee choices execute; unsafe model fights
abort. Overworld remains teacher-controlled. Do not call this full training control, and do not
permit teacher fallback on disagreement in the fresh controlled run.
Controlled root 01 failed closed after 480 decisions when exhausted/disabled attacks made `fight`
unavailable without changing the model's features or candidates. It is excluded from training. The
repair masks `fight` from the runtime candidate set at all unsafe boundaries; qualify that contract
on a fresh root before considering retraining or overworld authority.
Controlled root 02 passed that boundary but exhausted the healing budget after the model replaced
1,963 of 2,690 safe fights with real flees. It is excluded from training. The fitting loss now uses
the same candidate mask as inference; collect entirely fresh teacher-authority train/train/validation
lineages before fitting a replacement.
The replacement campaign passed: 119,328 fresh training decisions, 58,117 untouched validation
decisions, 78.06% raw / 89.25% balanced validation accuracy, a 57,342-decision shadow with 100%
battle agreement, and a 59,137-decision causal lesson with all six at level 55, zero faints, and no
fallback. This qualifies only battle `fight`/`flee` authority. The causal stream exposes 1,602
singleton forced flees and 1,984 safe two-candidate fights; do not describe that as tactical battle
learning. Overworld remains teacher-controlled and produced 12,405 seek-to-heal disagreements.
Before another collection campaign, make overworld selections execute causally and make its
candidate masks express only legality and hard safety, not the teacher's preferred action.
Overworld execution is now causal, but the first v4 campaign was stopped before artifact creation:
356 required heals in v3 train 01 came from an escort whose health/status/PP were absent from the
model observation. Feature schema v2 adds those game-neutral safety-reserve signals. The three
exposed roots in the observation-audit receipt are excluded from every later partition.
From a captured post-Mansion state, the team now reaches League parity at a measured combined cost
of 1,716 battles and 885 healing trips, with all six members exactly level 55 and zero faints. A full
uninterrupted route has not reproduced that result yet.

The trainees now perform the balancing work rather than leaving every battle to the escort, but the
decisions remain teacher-authored. No learned policy has completed the game, no cross-game transfer
has been measured, and the living Pokédex has not been started.

### Training venues (2026-08-07)

Encounter bands are now measured rather than recalled. `MEASURED_TRAINING_VENUES` in
`red_team_training.py` is transcribed from `docs/evidence/encounter-bands-2026-08-07.json`, and a
test fails if the two drift. Harvest more with:

```bash
POKEMON_RED_ENCOUNTER_LOG=<path> ...take a run...
.venv/bin/python scripts/harvest_encounters.py <path>
```

Areas below twenty samples are dropped, not downgraded — nine of the first twenty-one areas had
four samples or fewer. A band records the level 90% of encounters stay under *separately* from the
rare ceiling, because Diglett's Cave summarised as "15-31" gets rejected for the level-20 trainee
its other twenty-nine encounters suit exactly.

Two things changed that anyone touching training should know:

- **The `max_enemy_level_delta=2` experiment is rejected.** A full-health level-23 Diglett fainted
  to a level-19 Diglett before dealing damage. The replacement uses a five-level direct advantage,
  refuses opponent STAB types that are super effective, evolves fragile precursors through shared
  participation, and prefers immediate Scratch or Slash over two-turn Dig. One captured-state replay
  completed; full-route validation remains. See
  `docs/evidence/training-margin-four-level-faint-2026-08-07.json` and
  `docs/evidence/measured-balanced-team-captured-state-success-2026-08-07.json`.
- **`RED_DIRECT_LEVEL_ADVANTAGE` is retired.** It silently outranked the policy margin for the three
  species that are the trainees. Values preserved in the same evidence file.

Routing now works end to end. A trainee too weak for where the run is gets sent somewhere that
suits it, travels there, and gains levels: Cinnabar nurse → Fly to Vermilion → east to Route 11 →
the gate → Diglett's Cave. Both venues have implemented heal-and-return paths.

Three things about that chain are worth knowing before touching it.

**The town map has no readable cursor.** Five candidate addresses were sampled after every move and
all five stayed frozen on values the previous menu left behind
(`docs/evidence/town-map-cursor-not-observable-2026-08-07.json`). Fly is therefore judged by the map
underfoot: try an offset, confirm, ask the game where you landed, try again if wrong. Do not
reintroduce a hand-derived hop sequence; two runs died to one.

**The party submenu is ordered field moves, STATS, SWITCH, CANCEL.** SWITCH is at
`field_move_count + 1`, measured one row at a time from a captured state
(`docs/evidence/party-submenu-layout-2026-08-07.json`). This was guessed wrong four times, at five
runs' cost, because every check was derived from the same assumption as the guess.

**A step is not a step unless the player moved.** A blocked press never rolls for an encounter, so a
walk into a wall burns the step budget while looking exactly like training. The ratio that
distinguishes them is steps-to-battles; report it when adding any new walk.

### Iterating without replaying the route (2026-08-07)

Runs reach the training block in about six minutes. A captured state reaches it in about one.

```bash
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Returned safely from Mansion" --out <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --swap-only
```

`--max-steps N` shrinks the policy's step budget so a spinning loop fails in seconds rather than
burning 500,000 steps.

State files are ROM-derived and private in exactly the way the ROM is. Keep them outside the
repository and never commit them; `trajectory` already refuses `savestate` keys in public artifacts.
This does not weaken the adapter's no-save property, which is about PyBoy never creating files
beside the user's ROM — see `PyBoyAdapter.save_state`.

A capture is one starting point, not a substitute for a run. Iterate against it; confirm with
`cli play`.

## The full gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/python -m mypy
.venv/bin/pytest -m "not integration"
```

`mypy` now runs over all of `src/`, clean. It got there via a debt register in
`pyproject.toml`: forty-four legacy modules carry per-module `ignore_errors`
overrides, and that list may only ever shrink. Do not add to it — fix the module
instead. Two patterns dominate what remains: twenty-eight modules each declaring
their own structurally identical `EmulatorState` (and five their own `_RunState`),
and `int | None` passed where `int` is required. Hoisting the duplicated Protocols
into one shared definition removes roughly forty-five of the entries at a stroke.

This matters more than it looks. Of nine defects found in the balanced-team work
in a single session, five were type or arity errors — a reader passed where a
species tuple was expected, `None` passed where a coordinate tuple was declared,
a call supplying 7 of 18 required arguments, `_move` given five positional
arguments where it takes four, and a typed progress sink called with `None`.
Each cost a 25-minute emulator run to discover. A type checker reports them in
seconds, and the neutral layer is now covered.

Current state: **2,110 passed, 3 deselected**, all checks green, on trunk
`agent/balanced-team-curriculum`.

## Open work, in priority order

These are ordered by how much they serve the mission, not by difficulty.

**1. Publish the passed target head. (Lane B/C)** Serialize the exact frozen two-unit,
plan-balanced, L2 0.003 candidate with model, feature-schema, source-lineage, and canonical-payload
authentication. Do not refit it or add seed 990007 to training.

**2. Bind learned target choice to execution. (Lane A/B)** Resolve the model's candidate index to
the live menu slot while preserving permutation equivariance and hard health/status/availability
constraints. Shadow evaluation precedes authority.

**3. Run a fresh causal completion. (Lane A/C)** Require the repaired live Agatha role receipt,
36/36 objectives, Hall of Fame, 100% target-head agreement or explicitly measured disagreements,
and no target fallback. Keep ordinary moves teacher-gated for this isolated target test.

**4. Repeat one strict canonical rehearsal. (Lane A)** Require 36/36 objectives, Hall of Fame, zero
target fallback/substitution, and every League chapter's existing role contract. Preserve any
failure and its partial receipt.

**5. Combine with teacher-free ordinary moves. (Lane A/C)** The reserve-control lane currently
teacher-gates ordinary move selection. Run the combined stack only after the target head passes.

**6. Harden the perturbation envelope. (Lane A)** Diagnose the lab-rival, Diglett-capture, and
Rocket-thief failures already exposed by uncounted probes. Keep route-timing brittleness separate
from learned-policy failures in the report.

**7. Open the counted campaign only after 1–6. (Lane A/C)** Freeze all source/model/root identities,
run the ten assignments once each, and let the independent checker enforce 8/10. Current status is
0/10; no root has been consumed.

**8. Start Crystal and learned navigation from the stable Red benchmark. (Lane B)** Compare
zero-shot, few-shot, and from-scratch behavior on one battle, local-navigation, and training task.
Use the result to revise the portable schema before expanding the living-Pokédex curriculum.

**9. Keep deferred maintenance visible.** Decide whether `global_router.py` and
`collection_chapter.py` should become real portable-loop components, shrink the 44-module mypy debt
register, and leave any history rewrite to the repository owner.

## Recent history

Roughly thirty commits on `agent/balanced-team-curriculum` after `5696121`. The 2026-08-07 session,
newest first:

- `528e661` The cave walk paced instead of pressing into a wall. A blocked press is not a step, so
  500,000 "steps" produced no encounters while looking exactly like training.
- `37dcec6` The party submenu measured a row at a time: SWITCH is at `field_move_count + 1`, which
  restores the formula an earlier commit in the same session had wrongly replaced.
- `5f64311`, `fd651f6` Mid-route state capture and replay. Six minutes to one second.
- `f8a4b7b` Fly judged by the map underfoot after five addresses proved the town-map cursor is not
  observable.
- `cf5b8bc` Gate repaired after the venue refactor: 124 ruff errors, 7 mypy errors and 3 failing
  tests to zero; 21 scratch scripts untracked; a module containing only `# Just a scratchpad`
  deleted from `src/`.
- `a87574c` A member may train in a band it can only partly fight — measured at 71% of the Mansion
  for a level-30 member, where the all-or-nothing rule had locked it out.
- `20c49f9` The venue trains whoever it can, not the weakest member outright — with the escort
  excluded, because "weakest that can train here" selects the escort and reinstates the very failure
  it was meant to fix.
- `17c3873` Relative training margin (+2) replacing a fifteen-level required advantage that let a
  level-20 trainee engage nothing above level 5.
- `3f7019e` Encounter bands measured rather than asserted. Our own Mansion note said 30-32 from
  eight samples; 155 samples said 28-39.
- `91ca43c` The training loop made runnable without an emulator, replacing two tests that asserted
  nothing.

Earlier highlights:

- `f67f690` Route 22 pivot gated on a battle-ready reserve — V35's party wipe made structurally
  unreachable rather than merely untriggered.
- `ec70c10` Twelve receipts relabelled: they recorded the Champion's fixed party levels as ours.
- `2feafcf` The balanced-team training pass was never called. Only the evolution pass ran.
- `9c2fc60` Training target derived from the League (55) rather than an internal spread that
  anchored to an overlevelled escort and cost 4,570 battles to overshoot parity by nineteen levels.
- `c5882c4`, `510a478` Pokédex contract, and the target made a function of a run's choices.
