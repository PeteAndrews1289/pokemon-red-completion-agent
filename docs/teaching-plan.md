# Teaching and data plan

## A complete run is not the starting requirement

The deterministic teacher can be built and verified one chapter at a time. It needs an exact ROM,
route knowledge, maps and transitions, semantic state predicates, bounded controller routines, and
recovery rules. It does not need a human video or an existing Hall-of-Fame trajectory to begin.

A complete clean teacher run is this project's promotion gate before:

- calling the deterministic teacher finished;
- training or evaluating a student on full-game composition; or
- promoting the learned stack to official full-game evaluation.

This is a project policy, not a logical claim that another system could not complete the game
without a teacher completion. Any completion claim still stands or falls on the frozen evaluation
contract and its own clean-run evidence.

One successful trace is also not enough for reliability. It contains little evidence about wrong
turns, shifted menu cursors, battle variance, blackouts, or other learner-induced states.

## Reference stack

The teacher may use these disclosed references:

1. the repository's 36-objective dependency graph;
2. a deliberately safe route for starter, team, items, HMs, healing, and badge order;
3. collision maps, warps, interactions, and declared read-only symbols;
4. bounded preconditions, success predicates, timeouts, and recovery rules for every skill; and
5. the predecessor's public clean-power-on bootstrap routine.

The bootstrap sequence was adapted from
[`pokemon-red-ai`](https://github.com/PeteAndrews1289/pokemon-red-ai) commit
`0e2df37720eec7d148187eb1001bf2d9502aa4f6`. Private blind-run checkpoints and screenshots are not
completion demonstrations and are not loaded by this project.

The qualified bedroom-to-Brock route is new successor work. Its map dimensions, collision-safe
corridors, warps, Pallet Town, Route 1, Viridian Forest, Pewter Gym, and story, party, battle,
badge, and inventory gates are derived from
[`pret/pokered`](https://github.com/pret/pokered) commit
`1e96034092686d006e863cace09e87273051a3d8`, then independently exercised against the exact
supported ROM. The teacher checks the resulting semantic phase after each bounded action rather
than treating the source route as proof of runtime success.

## Current qualified teaching segment

The deterministic teacher currently verifies all **21/21 qualified checkpoints** through Brock
and therefore **6/36 completion objectives**. Three clean runs were identical at the
122,999-frame / 1,573-action boundary, including the live Brock battle, concurrent Boulder Badge
plus TM34 evidence, and an accepted overworld movement probe after the reward text. No
behavioral-cloning, DAgger, or full-game result is implied. The next teaching segment crosses
Route 3 and Mt. Moon to Cerulean City.

The same segment can run headlessly or be observed locally with:

```bash
pokemon-red-completion play --watch --speed 4
```

Watch mode does not provide a human controller, record the screen, expose the ROM path, load a
save, or change the teacher. It renders the same bounded execution while checkpoint progress is
printed to the terminal.

## What each learning stage needs

### Behavioral cloning

Action-aligned examples for individual skills:

- semantic observation and current objective;
- macro-action plus button press/release duration;
- resulting observation and event delta;
- success, retry, recovery, or terminal label; and
- both nominal and deliberately perturbed starts.

### DAgger

A queryable teacher, not a fixed recording. For learner-visited states the dataset records the
learner action, teacher correction or abstention, disagreement, confidence, intervention, and
reason. This supplies recovery examples that a perfect-path movie cannot.

### Selective reinforcement learning

Private snapshots may seed bounded skill curricula during training only. They are never valid
official-evaluation starts. RL is reserved for measured weaknesses that remain after imitation and
DAgger rather than applied to the entire game at once.

## Private trajectory schema

Three versioned artifact types remain outside Git:

- **Episode manifest:** ROM, source, configuration, teacher and policy hashes; assistance class;
  seed; start type; outcome; terminal reason; attempt denominator; and completion evidence.
- **Decision table:** emulator frame; structured observation; objective and skill; macro and
  primitive action; duration; teacher label; next-state hash; event delta; and recovery state.
- **Sparse event log:** map, objective, badge, party, item, battle, checkpoint, recovery, and
  terminal transitions.

Decision tables should use Parquet. Manifests and sparse events should use canonical JSON or JSONL.
Screens, ROMs, saves, snapshots, and recordings remain private and content-addressed.

## Collection order

1. Freeze the trajectory schema and logger.
2. Record and exactly replay the clean-start bedroom trace.
3. Preserve the qualified **6/6** checkpoint segment through verified Squirtle. **Done.**
4. Extend the same clean session through the lab rival, Oak's Parcel, and the Pokédex. **Done.**
5. Extend and replay-qualify the route through Pewter City and Brock. **Done.**
6. Add perturbed starts and recoverable mistakes for each qualified skill.
7. Train a small behavior-cloning baseline per skill.
8. Run DAgger until there are zero teacher interventions across 20 preregistered held-out rollouts
   from the frozen perturbation suite for that skill.
9. Extend the teacher chapter-by-chapter through the remainder of the game.
10. Produce multiple clean teacher completions with timing and RNG variation.
11. Train full-game composition only after that coverage exists.

The first current evaluation gate remains three intervention-free clean-power-on runs through
Brock. A first Hall-of-Fame success is a milestone; reliability requires at least 8/10 frozen
clean-start runs.
