# Architecture

## Design principle

Pokémon Red contains several problems operating at radically different time scales. The system
therefore separates long-horizon quest planning from bounded control skills.

The target actor is a learned/hybrid policy: a semantic planner selects objectives and specialists,
and trained specialists act on structured game state. The deterministic teacher is a disclosed
data-generation and safety baseline, not the final actor. Neither planner nor specialists may use
raw memory addresses, trace indices, or hidden teacher actions as decision inputs.

## Private runtime boundary

The exact private ROM is read once, fingerprinted, and passed to PyBoy as an in-memory stream.
PyBoy never receives the source path and cannot auto-load adjacent cartridge RAM. It runs
headlessly by default; optional watch mode renders a local SDL window at a validated 1×, 2×, or 4×
speed. Human window input remains disabled in both modes, and PyBoy always stops with saving
disabled.

The current PyBoy port exposes only two narrow capabilities:

- read one byte from Game Boy Work RAM through the declared read-only memory adapter; and
- press, release, or tick through the sole frame-safe executor.

Cartridge ROM, VRAM, external cartridge RAM, I/O, and all other address regions fail closed. The
declared actor interface does not permit RAM writes, state loading or saving, emulator-backend
injection, or ROM-payload access. Watch mode changes rendering only: it does not add controller
authority, screenshots, recordings, or uploads. This is an enforced interface boundary within one
Python process, not a sandbox for malicious code. Public reports omit the filename and path.

## Components

### Semantic state adapter

The current implementation translates a small declared set of read-only Work RAM symbols into a
versioned state object. Pregame scratch values are never treated as story progress. Opening-game
map, event, script, controller-mask, party, and species fields are combined into typed phases; a
map transition alone is not considered proof that control is ready. Unknown or inconsistent states
fail closed. Future pixel, tile, or collision-data readers require separate, explicitly bounded
ports before they can enter this adapter.

### Qualified continuous teacher

The current bounded teacher uses one emulator session for 58 checkpoints from clean power-on
through Misty:

1. bedroom input ready;
2. Red's house first floor;
3. stable Pallet Town exit;
4. Professor Oak triggered;
5. starter selection ready; and
6. Squirtle present with the corresponding story event and controls restored;
7. the lab rival battle observed and won;
8. stable arrival in Viridian City;
9. Oak's Parcel present with the corresponding Mart event;
10. safe return to Pallet Town; and
11. the parcel delivered and Pokédex received with controls restored;
12. Oak's Lab exited after the Pokédex;
13. Viridian City reached northbound;
14. Route 2 reached;
15. the Viridian Forest south gate reached;
16. Viridian Forest entered;
17. Viridian Forest cleared;
18. Pewter City reached;
19. Pewter Gym entered with a battle-ready Squirtle;
20. Brock's live trainer battle identified;
21. Brock defeated with the Boulder Badge and TM34 concurrently verified;
22. Route 3 reached from Pewter;
23. required Route 3 trainer 0 identified and defeated;
24. required Route 3 trainer 1 identified and defeated;
25. required Route 3 trainer 3 identified and defeated;
26. required Route 3 trainer 6 identified and defeated;
27. Route 4 reached after all four required events;
28. Mt. Moon entered;
29. the connected B1F route reached;
30. the fossil-side B2F route reached;
31. the unavoidable Team Rocket battle identified and defeated;
32. the fossil-guarding Super Nerd battle identified and defeated;
33. the Helix Fossil event and matching inventory item verified;
34. the legal B1F exit ladder reached;
35. stable Route 4 exit from Mt. Moon verified;
36. stable Cerulean west entry verified;
37. the live Cerulean rival battle identified;
38. the Cerulean rival defeated;
39. Route 24 trainer 5 identified and defeated;
40. Route 24 trainer 4 identified and defeated;
41. Route 24 trainer 3 identified and defeated;
42. Route 24 trainer 2 identified and defeated;
43. Route 24 trainer 1 identified and defeated;
44. the Nugget Rocket battle and reward identified;
45. the Nugget Rocket defeated;
46. selected Route 25 trainer 8 identified and defeated;
47. selected Route 25 trainer 3 identified and defeated;
48. selected Route 25 trainer 2 identified and defeated;
49. selected Route 25 trainer 5 identified and defeated;
50. Bill's request for help verified;
51. Bill's cell separator used;
52. Bill's human form restored;
53. the S.S. Ticket received;
54. Bill's House exited with the ticket;
55. the mandatory Cerulean Gym trainer identified;
56. the mandatory Cerulean Gym trainer defeated;
57. Misty's live trainer battle identified; and
58. Misty defeated with the Cascade Badge and TM11 concurrently verified.

The public `opening` command retains its six-checkpoint compatibility contract. The `play` command
composes all 58 checkpoints without restarting, loading state, or saving. Every action is
reobserved, dialogue and battle loops have fixed budgets, and unexpected battles, maps,
coordinates, scripts, events, species, health, inventory, move PP, or controller masks fail
closed. Route 1 rejects every encounter. Viridian Forest permits only three intentionally seeded
Kakuna training battles and the mandatory Bug Catcher, each with its own type, party, and bounded
completion gates. Route 3 and Mt. Moon permit only the declared mandatory trainer identities;
unexpected wild battles and trainer substitutions fail closed.

The rival event alone is insufficient because the game also sets it after a loss. The immutable
victory checkpoint therefore requires a previously observed trainer-battle state, a winning battle
result, stable lab script and controls, and a level-6 Squirtle restored to 21/21 HP. Likewise, the
Pokédex checkpoint requires both Pokédex and parcel-delivery events, the parcel absent from
inventory, no battle, and restored controls. Before Brock, the teacher requires a healthy
level-9 Squirtle with Bubble and a safe PP reserve. The final gate requires an observed live Brock
battle followed by the Brock and TM34 events, TM34 in inventory, both Boulder Badge mirrors, zeroed
Gym scripts, and a surviving status-free Squirtle. Because the game's reward text can outlive the
script and control-mask bytes, the teacher then clears a bounded number of text pages and requires
an actual accepted overworld movement followed by a stable reobservation before qualification.
The Mt. Moon chapter additionally requires all four selected Route 3 event transitions in order,
live opponent/class/trainer identity for the required Rocket and Super Nerd, exactly one fossil
event with its matching item, stable post-warp control on Route 4, and Cerulean arrival with a
surviving status-free Wartortle. The Cascade chapter requires the live Cerulean rival, all five
Route 24 trainers and the Nugget Rocket in order, four selected Route 25 trainer identities,
Bill's request/transformation/ticket event chain, the mandatory Gym trainer, Misty's exact live
trainer identity, and concurrent Cascade Badge and TM11 event, inventory, and badge mirrors.
Adaptive move selection for the rival and Misty consumes bounded battle state, while the fixed
required-trainer routines retain the already qualified deterministic strategy.

The corridors and semantic gates are derived from pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8` and independently verified on the supported private ROM.
The concluded predecessor supplied the separately attributed power-on bootstrap, not this route.
Completing these **58/58 checkpoints** verifies **9/36 objectives**. Three exact clean-power-on
runs were identical at 434,510 frames and 5,936 actions. This verifies deterministic-teacher
repeatability for that route; it does not verify a learned policy, held-out timing/RNG
generalization, or the full game.

The teacher remains useful after it reaches the Hall of Fame: it can generate labeled
demonstrations, answer bounded DAgger queries, and attempt declared perturbation schedules. Teacher
metrics stay in separate evidence from learned-policy metrics.

### Objective graph

Represents the power-on-to-Hall-of-Fame route as a directed acyclic graph. Every objective declares:

- prerequisites;
- semantic completion facts;
- responsible specialist;
- deterministic priority;
- retry budget; and
- recovery destination.

The graph supports legitimate midgame flexibility without letting attractive but invalid evidence
skip prerequisites.

### Skill router

Chooses one bounded specialist from the verified state and current objective. It never sends
buttons directly. A future trained router may replace the deterministic router behind the same
interface.

### Target semantic planner

The final planner consumes the semantic observation, completion facts, resource state, and bounded
specialist outcomes. It selects the next objective and specialist, replans after unexpected but
legal transitions, and delegates stalls or unsafe resource states to recovery. Its held-out
evaluation disables teacher/oracle fallback; the objective graph may still constrain invalid
choices and the executor may still enforce action safety.

### Specialists

- **Navigation:** deterministic A* over verified collision maps and transitions.
- **Interaction:** dialogue, prompts, shops, healing, item use, party menus, and move replacement.
- **Battle:** initially a conservative rule policy; later a trained, action-masked specialist.
- **Recovery:** identifies stalls, loops, blackouts, resource exhaustion, and displaced state.
- **Puzzle/HM:** explicit bounded controllers for game-specific interaction sequences.

Every specialist returns a bounded outcome: `success`, `retry`, `replan`, or `fatal`.

Learned specialists are trained first on qualified demonstrations, then on timing/RNG
perturbations and learner-induced corrections. Promotion tests include unseen nearby positions,
encounters, damage and status outcomes, menu state, and timing schedules.

### Executor

Converts macro-actions into timed controller inputs. It is the only component allowed to press
buttons. It records the requested action, observed transition, and actor identity. The opening
command may also publish checkpoint progress to the terminal, while `--watch` renders the same
execution locally without granting the viewer input authority.

### Referee

Reads state independently of the actor and verifies objectives, failure conditions, and final
completion. It may grade an action but may not choose, replace, or hide one.

### Dataset recorder

Stores private, structured teacher actions, learner rollouts, corrections, and recovery examples.
Public outputs contain aggregate metrics and schemas, never ROM-derived payloads or private paths.

## Runtime LLM boundary

A language or vision model may be tested at objective or recovery boundaries, but it is not the
default per-button controller. Any live model call is recorded and changes the assistance label.

## Training boundary

Specialists are trained and promoted independently. Updating the battle policy cannot silently
change navigation. A specialist is replaced only after frozen tests cover nominal, perturbed, and
recovery states.

Training may restore private snapshots to build targeted curricula. Full-game evaluation may not.
Evidence is published in three non-interchangeable lanes: exact deterministic-teacher repeats,
perturbed/multi-seed teacher coverage, and held-out learned/hybrid multi-seed runs. Only the last
lane evaluates learned generalization, and it requires frozen weights, teacher fallback disabled,
and no save-state restoration.
