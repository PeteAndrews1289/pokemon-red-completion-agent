# Handoff

Written 2026-08-07 for the agent taking over. Read this once, completely, before touching anything.
It is meant to make you *actually* oriented, not politely briefed — which means most of it is about
what is wrong, what is unproven, and what this codebase has repeatedly fooled people into believing.

Then read, in order: [MISSION.md](MISSION.md) (why the project exists),
[AGENT_COORDINATION.md](AGENT_COORDINATION.md) (rules and lanes), and
[docs/story.md](docs/story.md) (the narrative, which doubles as a record of the failure modes).

---

## 1. What this project is for

**Build a model that can actually play Pokémon, and fill a living Pokédex across the mainline
titles.** Not "beat Red reliably." The Pokédex is the forcing function: it is the constraint that
makes route tricks useless and real decisions necessary.

The deterministic teacher exists to *produce demonstrations a model can learn from*. Its value is
therefore measured by how many real decisions its demonstrations contain — not by whether it wins.
A run that wins with one overleveled Pokémon sweeping is a run that teaches nothing, and that is the
condition the current work is trying to escape.

Keep this in view. It is easy — I did it repeatedly — to spend a day on menu plumbing and lose track
of whether it serves this.

---

## 2. What is actually true, as of this handoff

**Working and verified:**

- The deterministic teacher completes Red repeatedly, with genuine Champion and Hall-of-Fame
  evidence in the same run.
- A trained model authorizes all 36 objectives with zero fallbacks. It *selects* objectives; fixed
  code executes them. Do not describe it as an autonomous player — it runs as
  `model_authorized_fixed_specialists`.
- Encounter bands for five areas are measured with sample counts and reproduce exactly across runs
  (the route is deterministic).
- A party member too weak for where the run happens to be is now routed to a venue that suits it,
  travels there, and gains levels. This is new as of 2026-08-07 and is the mechanism everything
  downstream depends on.

**Not true, however it may look:**

- The training block has **never reached the level floor of 55 in a full run.** Every run gets
  further and none has got there. Do not let "it trains now" stand in for this.
- The team still does not choose its own battles. The escort still does most of the fighting.
- No learned policy has completed the game. No cross-game transfer has been measured. The living
  Pokédex has not been started.
- `max_enemy_level_delta=2` is recorded as **unvalidated**. It survived 64 live encounters without a
  faint. That is evidence, not proof.

**Gate state:** 1886 tests, 3 skipped; ruff, mypy (103 files), artifacts, docs and registry all
clean. Thirty-three commits on 2026-08-07.

---

## 3. Start here

**Take a run, read the phase list, fix what it says.** The chain currently stops at:

```
Battle menu did not settle before switching to Blastoise PP-exhaustion escape escort in 48 attempts.
```

The trainee spends its attacking power points after about seven battles and the escape path tries to
switch the escort in. That path is newly reachable — nothing had ever fought long enough to run dry.
The error now reports the distinct battle-menu phases it saw, the last eight in order, and whether
it was stuck in one phase or cycling between several. That distinction is the diagnosis; do not
guess past it.

Then continue down [AGENT_COORDINATION.md](AGENT_COORDINATION.md) § *Open work, in priority order*.

---

## 4. How to work here without burning hours

### Iterate against a captured state, not a full run

A run reaches the training block in about six minutes. A captured state reaches it in about one.
Twelve runs in one session were spent replaying the same 275 checkpoints before this existed.

```bash
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Returned safely from Mansion" --out <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --swap-only
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --max-steps 40
```

`--max-steps` shrinks the policy's step budget so a spinning loop fails in seconds instead of
burning 500,000 steps.

A capture is **one starting point**, and its starting position is part of what it captures — the
Mansion capture leaves the player on the nurse's tile, where a button press feeds her dialogue.
Iterate against it; confirm with `cli play`.

State files are ROM-derived and private exactly as the ROM is. Keep them in scratch, never commit
them. This does not weaken the adapter's no-save property, which is about PyBoy never writing files
beside the user's ROM — see `PyBoyAdapter.save_state`.

### The gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/python -m mypy
.venv/bin/pytest -m "not integration"
```

Any `src/` change restales the collection registry. Regenerate and update the four golden values in
`tests/test_collection_protocol.py` **in the same commit**. Never hand-merge those hashes — they are
derived; take either side and regenerate.

### Two hard rules

- **Never edit `src/` while an emulator run is in flight.** A run loads its source at launch, so a
  mid-run edit does not change the run — it changes what the tree claims the run was.
- **Never open a counted evaluation seed.** Validation `1810002`–`1810005` and sealed test
  `1820001`–`1820005` are one-attempt-only. `1810001` is exposed and diagnostic-only.

The ROM path, private artifact root and objective-model path come from the environment per session
and must never appear in any file, tracked or not — `check_public_artifacts.py` scans the working
tree including untracked files.

---

## 5. Measured facts. Do not re-derive these, and do not contradict them without a measurement

Each cost at least one emulator run to establish. Each has an evidence file.

| Fact | Evidence |
| --- | --- |
| The Mansion fields levels **28–39**, not the 30–32 an old note claimed from 8 samples | `encounter-bands-2026-08-07.json` |
| Diglett's Cave is **15–21** typical with a rare Dugtrio at 31 | same |
| The **town map has no readable cursor** — five candidate addresses all stay frozen. Fly must be judged by the map underfoot | `town-map-cursor-not-observable-2026-08-07.json` |
| The party submenu is ordered **field moves, STATS, SWITCH, CANCEL**, so SWITCH is at `field_move_count + 1` | `party-submenu-layout-2026-08-07.json` |
| Menu signatures: start menu `max=7, top=(11,2)`; party list `max=5, top=(0,1)`; member submenu `max=4, top=(10,8)` | same |
| `watched=0x03` does **not** mean the d-pad is ignored — the party list reports it and its cursor moves | same |
| A **blocked press is not a step**, so a walk into a wall never rolls for an encounter | `cave-pacing-and-training-2026-08-07.json` |

---

## 6. How this codebase fools people

These are not hypotheticals. Each happened, more than once, and cost runs.

### Green tests that test nothing

The test file written to prevent never-executed code contained one test asserting objects construct
and one ending in `pass`. Both green. A later test monkey-patched away the exact method that was
broken, so the suite stayed green over a module whose entry point raised `AttributeError` on its
first call.

**Practice:** after writing a test, break the code it covers and confirm the test fails. If it does
not, the test is decoration. This caught four separate defects today that would otherwise have
shipped.

### A belief that nothing available can contradict

The SWITCH row was guessed wrong four times across five runs. Every check was derived from the same
assumption as the guess, so no amount of care could falsify it. One measurement did, in five lines —
and the answer was the formula the code had *before* I changed it.

**Practice:** when a guard and the code it guards come from the same assumption, the guard only
agrees. Recognise success by the game's own state: the map underfoot, the party order in memory, the
levels that rose. Where an observable exists, read it; where none does, act and check what happened.

### A process that looks like work

A run went ten minutes without failing. That looks exactly like training. It was pressing left
against a wall: 500,000 steps, fewer than 250 battles, no level gained. The number that separates
training from spinning is the ratio of steps to battles, and nothing was reporting it.

**Practice:** for any loop, ask what number would distinguish progress from motion, and report it.

### Constants that were true by accident

Field Dig addressed Diglett as the third party member with Dig in move slot two. Both held only
while nothing ever reordered the party. The moment the party swap started working, it broke.

**Practice:** making the party movable was the point. Anything that remembers a slot is a latent
bug. Find the Pokémon, do not remember where it was.

### Copies that drift from their originals

Three times a helper was copied from a proven module and lost the constant that made it work: the
matchup gate, the cursor selector, and a walk bounded at 12 steps where the proven version allows 24.

**Practice:** before writing a navigation helper, grep for one that already works. `surge.py` in
particular has proven paths for Vermilion, Route 11 and Diglett's Cave.

### Failures that carry no evidence

Five failures today produced messages with no state: `Could not select menu item.`,
`Fly to Vermilion failed.`, `Failed to enter Route 11`, a silent 500,000-step exhaustion, and
`Battle menu did not settle.` Each needed a run spent purely on instrumenting it before it could be
fixed.

**Practice:** this is the cheapest available change to this codebase. When you write a raise, put
the readings in it.

---

## 7. Predict before you run

Every run this session was preceded by a written prediction in `docs/evidence/predicted-*.json`
stating what should happen and, crucially, **what would refute it**. This is not ceremony. One
prediction assumed the party arrived as `[68, 20, 26, 30, 25, 30]`; it arrived as
`[55, 20, 26, 30, 25, 30]`, and the divergence was only legible because the assumption had been
written down. A run compared against no prediction can only be interpreted after the fact — which is
how a wrong band survived 155 samples that contradicted it.

---

## 8. Do not

- Do not restore the multi-target Route 22 continuation loop. It cycled every reserve into Venusaur
  until the party read `(0, 0, 0, 0, 0, 0)`.
- Do not treat a green `passed` as evidence the thing it names happened.
  `team_development.passed` never looked at five of six party members, and twelve receipts reported
  the opponent's levels as ours.
- Do not use the party as disposable HP. Switching to a healthy teammate is strategy; feeding a weak
  one in to absorb a hit is the V35 failure.
- Do not reintroduce a hand-derived Fly hop sequence. Two runs died to one.
- Do not describe the objective ranker as an autonomous player.
- Do not commit ROMs, saves, emulator states, trajectories, secrets, or absolute paths.

---

## 9. Loose ends you are inheriting

- **`global_router.py` and `collection_chapter.py` are scaffolding.** The router has a correct
  Dijkstra, three tests, no call site, a hand-written five-node graph, and edges carrying no warp
  coordinates — it cannot drive navigation as it stands. `run_collection` reads the collection
  correctly then raises `NotImplementedError` at routing. Give them a job or park them.
- **Participation is measured for one of five League battles.** `turns_per_member` exists in
  `champion.py` only; `agatha.py` records the per-turn index without aggregating; Lorelei, Bruno and
  Lance record neither. And a raw list does not embarrass anyone — `[6, 0, 0, 0, 0, 0]` needs
  reading carefully before it bothers you, which is roughly how the escort problem survived.
- **The ROM path is in git history.** `a9d0bb4` added it in source, `371be10` removed it. Not in the
  current tree; `a9d0bb4` is on no remote, so exposure is local only. Rewriting history is
  destructive and belongs to the repository owner.
- **Two tolerance contracts disagree.** `MANSION_LEVEL_PARITY` uses `max_levels_behind=10` (target
  55) and `CHAMPION_LEVEL_PARITY` uses 5 (required 60), so a receipt reports a team that won the
  game as five levels short.

---

## 10. The standard to hold

Report what happened, not what was hoped for. Two claims I made today were wrong and needed
retracting: that a ten-minute run was "training" when it was spinning, and that `watched=0x03` meant
the d-pad was dead. Both were corrected in the record rather than quietly dropped, and the evidence
files say so.

That is the standard. This project's whole value is that its numbers can be trusted, and the only
way that stays true is if being wrong in public is cheaper than being vague.
