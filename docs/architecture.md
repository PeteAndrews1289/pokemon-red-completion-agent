# Architecture

## Design principle

Pokémon Red contains several problems operating at radically different time scales. The system
therefore separates long-horizon quest planning from bounded control skills.

## Components

### Semantic state adapter

Translates pixels, tiles, collision data, and a small declared set of read-only RAM symbols into a
versioned state object. Pregame scratch values are never treated as story progress. Unknown or
inconsistent states fail closed.

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

### Specialists

- **Navigation:** deterministic A* over verified collision maps and transitions.
- **Interaction:** dialogue, prompts, shops, healing, item use, party menus, and move replacement.
- **Battle:** initially a conservative rule policy; later a trained, action-masked specialist.
- **Recovery:** identifies stalls, loops, blackouts, resource exhaustion, and displaced state.
- **Puzzle/HM:** explicit bounded controllers for game-specific interaction sequences.

Every specialist returns a bounded outcome: `success`, `retry`, `replan`, or `fatal`.

### Executor

Converts macro-actions into timed controller inputs. It is the only component allowed to press
buttons. It records the requested action, observed transition, and actor identity.

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
