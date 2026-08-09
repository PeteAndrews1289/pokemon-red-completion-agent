# Crystal transfer benchmark

## Decision

Do not build a second full deterministic teacher before testing transfer. Finish and qualify the
reserve-aware Red battle controller, then give Crystal the smallest adapter and teacher surface
needed to answer three questions:

1. Does Red's semantic matchup policy choose a useful reserve in a Crystal battle?
2. Does a learned local navigation skill survive a different map and interface implementation?
3. Does the trainee/venue ranker remain useful when the available species and encounter bands
   change?

A complete Crystal teacher would take substantial route work before discovering whether the shared
representations transfer at all. These microbenchmarks are designed to fail early and explain why.

The August 9 Red controller makes this dependency sharper. Its two-lineage action model improved to
98.2394% held-out accuracy and 94.7537% balanced accuracy, but causal execution proved that switch
timing and switch-target binding are different learned decisions. The first target head improves an
untouched lineage from 10/13 to 11/13 and still misses the exact Agatha Golbat role that triggered
the work. Crystal should therefore begin after the Red target head has enough randomized late-game
data to pass its offline and causal gates. It should not wait for the ten-root Red reliability
campaign, and it should not begin as a second 300-plus-checkpoint route.

## What Crystal needs first

- A lawfully obtained, emulator-compatible Crystal ROM supplied only through the environment.
- A revision identity and private ROM hash; neither the ROM nor its filesystem path enters Git.
- A thin semantic observation adapter for party members, moves and PP, opponent state, battle menu,
  local position, and input readiness.
- A pinned mechanics catalog containing Crystal species, moves, the Generation II type chart, and
  the added Dark and Steel types.
- Three bounded teacher tasks rather than a whole-game route:
  - one battle with at least two genuinely useful reserve candidates;
  - one Pokémon Center-to-adjacent-area round trip with a perturbed starting tile; and
  - one short training lesson with at least two viable trainees or venues.
- Fresh observations and action labels recorded through the same actor/referee separation used for
  Red.

This does require new teacher code, but initially it is a **thin Crystal task adapter**, not a full
Crystal walkthrough script. The adapter only has to create and verify the three microtasks, expose
the shared semantics, and record synchronized state/action labels. A complete route teacher is a
later decision informed by the transfer result.

The benchmark compares the frozen Red model zero-shot, a small preregistered few-shot adaptation,
and an identical model trained from scratch on the same Crystal examples. Transfer means the Red
initialization needs less Crystal teaching to reach the same held-out and causal performance. A
single successful demo does not establish transfer.

## How a YouTube playthrough helps

A full playthrough video is useful as teacher-design reference material. It can identify:

- the game's major progression dependencies;
- mandatory versus optional mechanics;
- sensible capture and evolution opportunities;
- areas worth turning into bounded navigation or training tasks; and
- confusing menus, scripted sequences, and recovery points worth testing deliberately.

It is not a drop-in behavioral-cloning dataset. Normal video does not provide synchronized emulator
state, exact controller timings, menu cursor state, party PP, or causal action labels. We can use it
to draft the route graph and teacher curriculum, then collect actual training examples from the
emulator under the repository's typed observation contract.

The most helpful owner-provided material will be:

1. one complete, commentary-light Crystal playthrough URL;
2. confirmation of the cartridge revision or ROM filename, supplied privately rather than written
   into the repository;
3. any preferred completion definition—Hall of Fame only, Red at Mt. Silver, Pokédex milestones,
   or a broader 100% checklist; and
4. permission to create private local checkpoint states for rapid adapter development.

For the first benchmark, the most useful scope choice is **Red at Mt. Silver** as the long-term
Crystal completion target, while the implementation remains limited to the three microtasks. That
keeps the destination ambitious without confusing a route reference with training data.

Timestamps are welcome but not required. The video should be treated as disclosed teacher
reference, not proof that the model learned the demonstrated behavior.

## Dependency order

1. Collect more complete, timing/RNG-varied Red demonstrations with explicit late-game targets.
2. Train and qualify switch-class and switch-target behavior offline, including the held-out
   Agatha Golbat choice.
3. Pass the strict canonical Red rehearsal and one perturbation rehearsal.
4. Add Crystal's mechanics catalog and semantic battle observer.
5. Run the battle microbenchmark zero-shot, few-shot, and from scratch.
6. Add the local navigation and trainee/venue tasks only after the battle representation can be
   compared honestly.
7. Decide whether a full Crystal teacher is warranted from those results.

This sequence gives the model new context without spending weeks rebuilding a complete answer key
before testing whether anything learned in Red is portable.
