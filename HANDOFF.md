# Current development handoff

Updated September 13, 2026. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). The North Star has not changed: build a
transferable hierarchical Pokémon player that finishes stories and contributes legitimate
registrations to one shared Pokédex across games.

## Current boundary: Model114 selected resupply / execution next

Execution and fit source `003612b8b505781a917bbbd416155f5b2defe2eb`, bundle
`cbd6651cf747f5e6bb0edcb136f21033f2d9893f8b5e0c42a8893416b2b6a86f`, passed exact-source
GitHub CI run `34750593606`.

Gemini 3.8 Flash High rejected the first private runner before gameplay because it bound the wrong
parent model and retained a stale selection seed. Both defects were fixed before controller input;
the re-audit and separate fit audit returned GO with zero P0/P1 findings.

Model113's exact frozen acquisition then ran once. It used **513 actions / 30,804 frames** and four
fishing casts, added one missing registration and retained **84 registered / 64 living / 68
specimens**. It made zero policy queries during execution, used zero teacher labels and was not
retried. The measured success became training row114. Model114 has **114 settled examples**, 78
successful. Model SHA-256:
`f503725e2153e7523d9be26a431c45782f1b473c3406e87dfa96a9450f190ec3`.

The input-ready Model114 state is checkpoint
`73836c65f54ab81ec357f5fffd68b3da799582d38546ea3eb8a722e664574f18`, state
`7025658c08948147f9798d45ea59c4d5eef1aaa1831b5d953348c6a409522797`. Its action-free menu has
six choices across three goal families: restore, four acquisitions and resupply/income. Model114
selected resupply candidate5 with probability `0.43869514182473374`. That exact choice is frozen but
unexecuted.

Next: execute the exact frozen Model114 resupply choice once without another policy query, retain
its actual result, fit Model115 only if the measured outcome is eligible, publish the terminal and
rebuild the next menu. Do not retry consumed attempts or move into Blue/Crystal.

[Latest report](docs/work-sessions/2026-09-13-model114-frozen-fishing-learning.md) ·
[Latest evidence](docs/evidence/red-model114-frozen-fishing-learning-2026-09-13.json)

## Prior measured endpoint: capture, failure and online update / model111

The prior input-ready restart had **83 registered / 63 living / 67 specimens** and model111 with
111 examples. It followed a model-selected capture with a second model-selected route failure,
then recovered that earlier dialogue terminal as zero-label support. Cross-box capture preparation
was subsequently qualified. These remain valid historical steps; model112 supersedes the model111
learner and its new terminal now requires recovery.

[Prior report](docs/work-sessions/2026-09-12-model111-fishing-learning-loop.md) · [Prior evidence](docs/evidence/red-model111-fishing-learning-loop-2026-09-12.json)

## Prior measured endpoint: Safari capture / model105

The latest standard registered-player checkpoint remains
`red-collection-20260912-cg-owned-evolution-01-causal`, record SHA-256
`ff0f3f3268712efca4015c9538f3625b8cf736eae1bef3cfaa3c839f743a2677`. A later private Safari
capability chain retains a measured terminal state SHA-256
`9f33ca2de0f87fc469896e014b3a3774e902ede46f58237127be6570382ab4d6`. It supplied one explicit
development-measured training row but has not yet been imported as a standard traced-player
checkpoint.

- Registered-objective model: **105 settled examples**
- Model SHA-256: `00e1ae35eb296caa3956f5f766f6a10f4410ee026c1c58bb030e1d0c4d466bae`
- Latest measured collection: **80 registered / 60 living species / 64 specimens**
- Required Red registrations remaining: **44**
- Latest collection result: one model-selected Safari area produced a retained missing registration
  after a generic cartridge-derived patrol; the successful patrol saw 12 encounters, 11 flees and
  one capture
- Latest learning result: model104→105 through one training-only measured-choice row; all 104 prior
  row hashes remain present

The prior three-option learned result remains Psyduck-to-Golduck. The fossil transaction needed a
bounded retained-state recovery because the game had entered its nickname editor before writing the
full box structure. The original fossil choice was not retried.

## Funding and support boundary

The immediate resource dead end is closed in practice. A controlled blackout retained half of the
money earned during the incomplete League sequence, healed the party and enabled deterministic
resupply of 19 capture balls. The support chain totals 2,556 historical actions / 232,774 frames.
Its registered import sent zero input, advanced zero frames and created zero training examples.

The retained support wrappers authenticate declarations, claims, results, source commits and state
transitions, but do not contain an action trace. Public code therefore gives them a separate
`registered recorded support` type and may not represent them as native traced play or learned
authority. The successful import checkpoint is
`a3ba144e9a897b7bd32246985523059d0a7d126cba446e9edc74d8b3d01b2565`.

Do not repeat the League rematch merely to strengthen this support history. Fossil acquisition is
now one qualified acquisition-family provider; the next product constraint is broader acquisition.

## Historical Safari result and superseded gate

The Safari candidate layer is now live-tested. Cartridge data produced four productive areas that
jointly covered six missing registrations. Model104 selected candidate1 from an identity-free menu
with zero teacher labels; that choice controlled the played attempt. Generic transport, one paid
admission, a terrain-derived patrol and observed Safari commands added one registration. The full
retained chain used 1,271 counted actions / 152,580 frames and left 23 Safari Balls / 235 steps.

Four failed continuation identities remain preserved: full step-counter reading, encounter handoff,
two-column command observation and post-throw settlement were each repaired without replaying the
admission or resampling the model. These are now generic tested mechanics.

The measured-choice gate is closed. The adapter recomputed model104's scores and sampled choice,
verified the exact declaration/claim/result chain, checked every parent/terminal state transition,
reconstructed the 79→80 registration and 63→64 specimen outcome with zero controller input, and
admitted exactly one row. Model105's corpus SHA-256 is
`28722d391b5f1aff8dfc9733a7357f006f17f554b7457d9264047ffedc8e9f0d`.

The row is permanently lower trust than a native episode: no action trace, training only, no
independent evaluation and no authority promotion. The next gate is to preserve the 80-registration
terminal through the ordinary restart path and expose at least two physically executable,
identity-free item-procurement or fishing alternatives for model105.

The ordinary regional candidate layer and already-owned level evolutions were exhausted at the
standard 79-registration checkpoint. After the Safari result, 44 Red registrations remain. Rebuild
the exact method census from the retained terminal before quoting per-family counts; the prior
79-registration census was:

| Method | Missing registrations |
| --- | ---: |
| evolution | 13 |
| ordinary wild/water | 8 |
| fishing | 7 |
| Safari | 6 |
| static encounter | 4 |
| in-game trade | 3 |
| prize | 2 |
| fossil | 1 |
| gift | 1 |

The exact action-free inventory found nine owned missing stone-evolution precursors, but no held
stones, ₽558 against the ₽2,100 shop price and no party member with Pay Day. Those candidates are
preserved for later resource planning; item evolution is not the cheapest executable next gameplay.

The stone candidates remain deferred. Broaden item procurement and fishing through the same
reusable candidate vocabulary. Do not add named Safari or fishing species routes.

## Authority and claim boundary

The learned model chooses high-level goals and destinations in bounded development episodes.
Deterministic, tested skills still execute navigation, menus, combat, capture and evolution. The
latest fishing rows teach selected destination outcomes, but their missing action traces make them
ineligible for evaluation or promotion. The earlier successful three-option Golduck evolution is a
native selected-arm outcome; forced support and forced acquisitions add none.

Fresh-game autonomy, arbitrary-seed reliability, full Red registration, unfamiliar-ROM competence,
learned battle control and transfer to Blue or Crystal remain unproved. Crystal stays deferred.

## Session discipline

1. Name the reusable capability and cheapest falsifier before editing.
2. Spend most effort on executable data/scenarios and measured model outcomes.
3. One focused test batch; one CI check after a meaningful commit. No CI-only loop.
4. Stop on species-specific routing, coordinate-bearing policy features, forced outcomes described
   as learning, unsupported physical prerequisites or consumed-state replay.
5. Reorient after the first bounded result or falsifier and update this file in place.

[Prior report](docs/work-sessions/2026-09-12-model106-measured-fishing-capture.md) · [Prior evidence](docs/evidence/red-model106-measured-fishing-capture-2026-09-12.json). Recommended model:
**Sol High, Fast enabled** for implementation. Use Astra High/Max only for architecture or
authority-promotion review.
