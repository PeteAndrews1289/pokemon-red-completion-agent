# Current Audit — 2026-08-12

## Outcome first

Update after the initial audit: early Erika is now live-qualified under published `fc2c47a` and
green CI run `31569081316`. Scenario 009 is also exactly constructed and rehearsed. The static
teacher-order gap fell from **21 to 14**, and validation scenario 023 is no longer blocked by
Erika's old post-Koga requirement. Counted data and test access remain zero. See the
[early-Erika](evidence/early-erika-curriculum-qualification-2026-08-12.json) and
[scenario 009](evidence/strategic-scenario-009-rehearsal-qualification-2026-08-12.json) receipts.

The strategic-learning campaign made measurable progress, but model training should remain closed.
The private inventory now contains **33 authenticated capture envelopes, 25 distinct frontiers and
11 exact learning scenarios**. The exact contexts are five train scenarios and six validation
scenarios. All are still unassigned rehearsals: **counted train = 0, counted validation = 0, test
opened = 0**.

Four of the six preregistered validation cost-baseline challenges are now live-qualified: scenarios
003, 007, 011 and 015. Scenario 015 is the strongest context so far: five available choices with
route costs from 55 to 624, one teacher-selected Surf approach, 624 acknowledged movements, one
trainer interruption, one wild interruption and one visible-object replan. Its immutable episode
contains 1,400 records and no movement-imitation label. See the
[scenario 015 receipt](evidence/strategic-scenario-015-rehearsal-qualification-2026-08-12.json).

The same frozen source also constructed and qualified train scenario 005. The bounded Saffron skill
added exactly `reach_saffron`, a cartridge route returned to the declared Celadon origin, and no
episode or label was created during construction. The later one-shot rehearsal produced one
successful two-candidate teacher choice in 31 movements with no interruption or replan. See the
[scenario 005 receipt](evidence/strategic-scenario-005-rehearsal-qualification-2026-08-12.json).

The path-free [inventory receipt](evidence/strategic-frontier-inventory-2026-08-12.json) is the
current measurement. It reports 25 missing learning scenarios and excludes one known invalid
diagnostic envelope.

## What the cartridge-routing work fixed

The route to scenario 015 repeatedly failed at Kanto gatehouses even though the map graph claimed
the maps were connected. The failure was not random emulator timing. Generation I uses several
different transition mechanisms on the same small set of maps:

- automatic door and warp tiles;
- top and bottom boundary returns with different arrival semantics;
- horizontal gate exits whose direction depends on the boundary entered; and
- directional carpet rows, including inert upper rows that look like warps but cannot be activated
  from the player's legal facing/action state.

The adapter now decodes those tables from the cartridge, projects automatic triggers into the map
graph, filters inert directional rows and tests return direction independently on all four map
edges. This replaced geometry-only guesses with cartridge evidence. Frozen source `fc3b91a` passed
2,707 tests with three skips and one expected failure, passed Ruff, and passed GitHub CI run
`31566363870` before the successful scenario 015 and 005 live work.

## The important audit finding

The remaining difficulty is no longer ordinary routing. The quest graph says what Pokémon Red
allows; the qualified teacher skills say what this particular teacher run knows how to demonstrate.
Those are not the same graph.

The updated static curriculum-order audit records three operational contracts that are stricter
than the game's public prerequisites. It checks all 36 learning scenarios without reading private
captures or opening test. It finds **14 exact learning frontiers incompatible with the current
qualified teacher order**, down from 21 after early Erika removed seven blockers. This is a
teacher-coverage result, not evidence that those cartridge states are impossible. See the
[curriculum-order receipt](evidence/strategic-curriculum-order-audit-2026-08-12.json).

The two remaining validation challenges expose the gap directly:

| Scenario | Exact frontier requires | Current teacher additionally requires | Missing curriculum |
|---|---|---|---|
| 019 | Koga and Strength while Surf is incomplete | Koga uses the Surf-ready party; Strength consumes Gold Teeth obtained by the Surf chapter | Koga-before-Surf and a Gold-Teeth/Strength path that does not award Surf |
| 023 | Erika while Koga is incomplete | Resolved by the qualified pre-Koga Celadon curriculum | No remaining Erika-order blocker |

The same issue explains the current paper-only one-skill matches:

- scenario 009 is qualified; 010 and 014 need the distinct post-Fuji Erika battle boundary;
- scenarios 017–019 need Koga and/or Strength before Surf; and
- scenario 041 needs a Cinnabar route before Sabrina instead of the current post-Sabrina/Fly
  chapter.

This audit prevents a misleading loop: the inventory can still say “one objective differs,” but
the implementation now separately reports that the only qualified skill for that objective would
add a forbidden prerequisite or starts from an unavailable party boundary.

## Readiness for model training

Training is closer in infrastructure but not ready in experimental coverage. The scenario recorder,
identity binding, candidate permutation, no-movement-label contract, strict reload and sealed-test
controls are working. What is missing is a context-diverse dataset large enough to support the
claim.

Current exact coverage is:

- train: 5 of 24 planned contexts;
- validation: 6 of 12 planned contexts;
- validation cost-baseline challenges: 4 of 6;
- test: 0 of 12 opened, as required; and
- counted examples: 0.

Opening collection now would train primarily on the teacher's canonical order and then ask the
model to generalize to alternate orders it was never shown. That would be a weak transfer result
even if the code ran perfectly.

## Ordered next work

1. Construct and rehearse scenario 023 from the now-qualified early-Erika frontier.
2. Extend or separately qualify early Erika for the post-Fuji Blastoise boundary used by 010/014;
   direct diagnostics showed a distinct deterministic leader battle schedule, so do not overclaim it.
   This unlocks three train contexts and is required by validation scenario 023.
3. Split the Safari teaching path into independently verified resource outcomes where the
   cartridge permits it: obtain Gold Teeth without claiming Surf, then teach Strength. Build a
   Koga-before-Surf battle boundary that does not depend on Surf as the battle move. Together these
   unlock validation scenario 019 and adjacent train contexts.
4. Add a Surf-from-Pallet or equivalent **Cinnabar-before-Sabrina** route rather than reusing the
   current post-Sabrina Fly chapter.
5. Materialize and rehearse scenarios 019 and 023 once each. Recompute the paired cost-baseline
   audit across all six challenges.
6. Continue the remaining non-test contexts in dependency order, measuring unique policy inputs
   rather than counting repeated emulator trajectories.
7. Open counted train/validation collection only after the published admission thresholds pass.
   Keep all 12 test situations sealed until the frozen model's final evaluation.

## Portfolio and research narrative

The strongest honest story is no longer “a script beat Pokémon.” It is that a deterministic
completion teacher was decomposed into authenticated semantic skills, then audited as a source of
model supervision. Cartridge-derived routing, immutable failures and sealed evaluation exposed a
research flaw that unit tests could not: a single successful play order does not teach alternate
valid orders. The next phase expands the teacher from one route through the game into a curriculum
that demonstrates the invariances a transferable Pokémon model is expected to learn.
