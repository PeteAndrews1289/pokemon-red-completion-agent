# Current Audit — 2026-08-12

## Outcome first

Update after the initial audit: the teacher now qualifies Fly as an independent resource, Gold
Teeth without Surf, Strength before Surf, Koga on that Strength lineage, Silph on the same pre-Surf
party, and Pokémon Tower on both the pre- and post-Erika move lineages. Exact scenarios 010, 014,
019, 025, 026 and 037 are constructed and rehearsed. The static teacher-order gap fell from **21 to 12**. Counted
data and test access remain zero. See the [scenario 019 receipt](evidence/strategic-scenario-019-rehearsal-qualification-2026-08-12.json)
the [010/014 receipt](evidence/strategic-scenarios-010-014-rehearsal-qualification-2026-08-12.json),
the [025/026 receipt](evidence/strategic-scenarios-025-026-rehearsal-qualification-2026-08-12.json),
and the [scenario 037 receipt](evidence/strategic-scenario-037-rehearsal-qualification-2026-08-12.json).

The strategic-learning campaign made measurable progress, but model training should remain closed.
The private inventory now contains **58 authenticated capture envelopes, 40 distinct frontiers and
21 exact learning scenarios**. The exact contexts are thirteen train scenarios and eight validation
scenarios. Scenario 041's exact context has a preserved failed rehearsal; no failed row is promoted:
**counted train = 0, counted validation = 0, test
opened = 0**.

All six preregistered validation cost-baseline challenges are now live-qualified: scenarios 003,
007, 011, 015, 019 and 023. Scenario 015 is the widest context so far: five available choices with
route costs from 55 to 624, one teacher-selected Surf approach, 624 acknowledged movements, one
trainer interruption, one wild interruption and one visible-object replan. Its immutable episode
contains 1,400 records and no movement-imitation label. See the
[scenario 015 receipt](evidence/strategic-scenario-015-rehearsal-qualification-2026-08-12.json).
Across the six unique challenge contexts, the deterministic teacher disagrees with every unique
route-cost minimum. A perfect scorer would therefore have six paired wins and a best-case
two-sided exact p-value of 0.03125. This passes the experiment-capability gate, not the model-training
gate. See the [paired capability audit](evidence/strategic-validation-cost-baseline-capability-audit-2026-08-12.json).

The same frozen source also constructed and qualified train scenario 005. The bounded Saffron skill
added exactly `reach_saffron`, a cartridge route returned to the declared Celadon origin, and no
episode or label was created during construction. The later one-shot rehearsal produced one
successful two-candidate teacher choice in 31 movements with no interruption or replan. See the
[scenario 005 receipt](evidence/strategic-scenario-005-rehearsal-qualification-2026-08-12.json).

The path-free [inventory receipt](evidence/strategic-frontier-inventory-2026-08-12.json) is the
current measurement. It reports 15 missing learning scenarios and excludes one known invalid
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

The updated static curriculum-order audit records one operational contract that is stricter
than the game's public prerequisites. It checks all 36 learning scenarios without reading private
captures or opening test. It finds **2 exact learning frontiers incompatible with the current
qualified teacher order**, down from 21 after the alternate-order curricula. This is a
teacher-coverage result, not evidence that those cartridge states are impossible. See the
[curriculum-order receipt](evidence/strategic-curriculum-order-audit-2026-08-12.json).

Scenario 019 previously exposed the gap directly. It now proves the repaired composition: Fly and
Gold Teeth are resource lessons with no objective label, Strength and Koga complete before Surf,
Silph accepts the resulting move lineage, and construction returns to the exact Celadon origin.
The remaining paper-only one-skill matches include:

- scenarios 009, 010 and 014 are now qualified across the pre- and post-Erika Tower lineages;
- scenarios 017 and 021 still need Koga without either Surf or Strength; and
- scenario 013 is now exact: Jolteon and Snorlax are independent no-label resources, and Sabrina
  is qualified on the resulting pre-Surf six-member lineage;
- scenario 041 now has an exact pre-Sabrina Cinnabar capture, but its first immutable rehearsal
  failed after the generic route fighter exhausted the lead across two Route 21 trainers. See the
  [construction/failure receipt](evidence/strategic-scenario-041-construction-and-rehearsal-failure-2026-08-12.json).

This audit prevents a misleading loop: the inventory can still say “one objective differs,” but
the implementation now separately reports that the only qualified skill for that objective would
add a forbidden prerequisite or starts from an unavailable party boundary.

## Readiness for model training

Training is closer in infrastructure but not ready in experimental coverage. The scenario recorder,
identity binding, candidate permutation, no-movement-label contract, strict reload and sealed-test
controls are working. What is missing is a context-diverse dataset large enough to support the
claim.

Current exact coverage is:

- train: 13 of 24 planned contexts;
- validation: 8 of 12 planned contexts;
- validation cost-baseline challenges: 6 of 6;
- test: 0 of 12 opened, as required; and
- counted examples: 0.

Opening collection now would train primarily on the teacher's canonical order and then ask the
model to generalize to alternate orders it was never shown. That would be a weak transfer result
even if the code ran perfectly.

## Ordered next work

1. **Complete:** qualify Erika after Strength/before Koga, construct scenario 023, and complete its
   official uncounted rehearsal.
2. **Complete:** qualify Tower on the post-Erika Ice Beam lineage and construct/rehearse scenarios
   010 and 014 without weakening the move/PP evidence contract.
3. **Complete:** split Fly and Gold Teeth into independently verified resource lessons, teach
   Strength and Koga before Surf, and qualify Silph on that move lineage.
4. **Complete:** add a Celadon-to-Cinnabar pre-Sabrina lesson. Next add bounded route-battle
   recovery or Fly-aware return routing and requalify scenario 041 under a new rehearsal identity.
5. **Complete:** materialize and rehearse scenario 019 once. The paired capability audit now has
   six unique disagreements and a best-case two-sided exact p-value of 0.03125.
6. **Complete:** construct scenarios 025 and 026 from exact authenticated branches. Continue the
   remaining non-test contexts in dependency order while measuring unique policy inputs rather
   than repeated trajectories.
7. **Complete:** construct and rehearse scenario 037; its teacher chose Erika at cost 106 over the
   77-cost Cinnabar route with no interruption or replan.
8. **Complete:** split Jolteon and Snorlax into construction-only party resources, preserve the
   19-objective frontier, qualify Sabrina before Surf and rehearse exact scenario 013. Next build
   the independent Cinnabar-before-Sabrina chapter for scenario 041. The construction is complete;
   the return-route rehearsal recovery remains.
9. Open counted train/validation collection only after the published admission thresholds pass.
   Keep all 12 test situations sealed until the frozen model's final evaluation.

## Portfolio and research narrative

The strongest honest story is no longer “a script beat Pokémon.” It is that a deterministic
completion teacher was decomposed into authenticated semantic skills, then audited as a source of
model supervision. Cartridge-derived routing, immutable failures and sealed evaluation exposed a
research flaw that unit tests could not: a single successful play order does not teach alternate
valid orders. The project now has enough preregistered disagreements to evaluate a scorer against
route cost, but not enough train-context diversity to fit one honestly. The next phase fills the
remaining non-test contexts before counted collection opens.
