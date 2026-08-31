# AI Systems Specialist interview handoff: transferable Pokémon agent

Prepared: 2026-08-31

Repository: [PeteAndrews1289/pokemon-red-completion-agent](https://github.com/PeteAndrews1289/pokemon-red-completion-agent)

Evidence baseline: published `main` commit `1d9554923f7973d6c3807445c1c4fc19c65dca1b`, which passed
[GitHub CI run 33424040364](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/33424040364).

This handoff covers only the current completion-agent repository. It deliberately does not use
results or claims from the concluded predecessor project.

## Interview-safe summary

> I am building a hierarchical, auditable agent that uses Pokémon Red as its first curriculum for
> learning reusable navigation, battle, party-management, resource, and collection decisions. The
> deterministic teacher and game-control stack can complete Red from power-on through the Hall of
> Fame, and the repository can generate authenticated short scenarios, fit small policies, compare
> them prospectively with controls, and reject them when they do not improve held-out outcomes.
> One uncounted canonical integration run also finished Red with learned modules making thousands
> of bounded choices inside deterministic route, skill, and safety scaffolding.
> The learned model does **not** yet have gameplay authority, has not autonomously completed Red,
> and has not transferred to Crystal. The long-term product is a model that finishes stories and
> builds a living Pokédex across games, versions, legitimate trades, and legitimate event inputs.

### Status vocabulary used below

- **Working:** implemented and supported by current repository evidence.
- **Partial:** a real implementation or bounded result exists, but it does not yet support the
  end-product claim.
- **Planned:** specified in architecture and roadmap, but not demonstrated.

## 1. Objective and current status

The objective is not merely to script a Pokémon Red completion. It is to create a transferable
agent that can enter a mainline Pokémon title, learn title-specific details, finish the story, and
contribute every legitimately obtainable species to a living Pokédex spanning the versions,
trades, and event inputs required for completion. Red is the first curriculum; Crystal is intended
as the first transfer test.

The project currently has three very different maturity levels:

| Layer | Status | Factual position |
| --- | --- | --- |
| Deterministic teacher and Red mechanics | **Working** | The teacher can complete Red from clean power-on through Champion and Hall of Fame while the independent referee verifies the run. |
| Model-training and evaluation system | **Partial** | Authenticated scenario collection, train/development separation, small model fitting, prospective prediction, and outcome comparison work. The latest battle candidate reduced training loss but tied its frozen prior on held development and was rejected. |
| Autonomous transferable player | **Planned** | Learned gameplay authority is **0** and demonstrated cross-title transfer is **0**. No model has autonomously completed Red, completed a living Pokédex, or played Crystal. |

The active learning board contains **19 causal Red train examples, 6 model fits, 6 verified
development outcomes, and 4 unseen comparisons**. These are deliberately small, bounded decisions,
not full-game episodes. The next experiment is a prospectively frozen V2 battle curriculum that
retains one prior train context, seeks seven fresh train contexts, and holds eight development
contexts together. It is still at its engineering/freezing boundary; no fresh V2 outcome or fit is
counted.

The current published baseline is green. A newer V2 engineering branch remains unmerged work in
progress and is excluded from every capability claim in this document.

## 2. What the system can demonstrably do now

### Working

- Run a deterministic Red teacher from power-on through the Champion and Hall of Fame under an
  independent semantic completion referee.
- Decode Red/Blue cartridge map, terrain, warp, ledge, encounter, evolution, fishing, and trade
  structures into typed data instead of relying only on handwritten routes.
- Observe live game state through PyBoy, including map and position, party, battle, menus, bag,
  badges, event flags, Pokédex, boxes, field capabilities, and selected resource state.
- Execute controller inputs through one bounded executor that checks whether each requested action
  was acknowledged, handles declared interruptions, replans in supported cases, and fails closed
  when safety or state assumptions do not hold.
- Run short authenticated scenarios, measure every supported candidate action from the same source
  state, keep train and development lineages separate, fit a small policy on train only, commit
  predictions before opening development outcomes, and preserve negative results.
- Track acquisition requirements and explicitly report version, trade, event, mutually exclusive,
  and unsupported blockers instead of pretending that one save can supply all 151 species.
- Serve read-only local dashboards whose counters are reconstructed from durable evidence rather
  than editable UI state.

### Partial

- Generated navigation works across meaningful Red probes, including dynamic occupancy, Surf,
  repeated Cut, Strength, and a story-gated Saffron passage. It is deterministic mechanics and
  graph search, not a learned cross-title navigation policy.
- A five-coefficient strategic-destination scorer trained on 24 examples scored 10/12 on held Red
  development examples versus 4/12 for a route-cost baseline, with six paired wins, zero losses,
  and exact p=0.03125. It has no live navigation authority.
- Battle, capture, party-development, training, resource, and goal-manager abstractions exist and
  can run in bounded Red scenarios. Learned rankers remain shadow or experimental components and
  have no promoted gameplay authority.
- One bounded model-selected acquisition has executed successfully in Red: the model selected the
  acquisition option at probability 0.7821, the skill completed in 665 controller actions and
  33,672 frames, and the ledger verified specimen preservation. It was development evidence for
  one decision, not general collection or gameplay authority.
- The living-Pokédex catalog can reason about acquisition dependencies and multi-run coverage, but
  the agent cannot yet autonomously execute an end-to-end living-Dex campaign.
- Crystal has a bank-aware observation layer and typed transfer/capability contracts. They are
  qualification scaffolding, not evidence of Crystal gameplay or transfer.
- One uncounted clean-power integration run completed Red with six authenticated learned roles
  active inside deterministic routing, skill, and safety boundaries. It recorded 3,315 battle
  decisions, including 3,248 model move decisions, plus 64,337 training-control and 125,800
  trainee/venue decisions. This proves subsystem integration on one canonical root; it does not
  prove timing/RNG robustness, learned navigation/menu execution, living-Dex autonomy, or broad
  promoted authority.

### Planned

- Teacher-free bounded authority for learned battle, navigation, party-development, and goal
  choices.
- Multi-goal learned composition across a complete story and collection campaign.
- A frozen title-neutral representation tested zero-shot in Crystal, followed by measured Crystal
  adaptation.
- Automated link trades, cross-save living-Dex consolidation, legitimate event ingestion, and
  autonomous multi-title completion.

## 3. Architecture and technology stack

### System architecture

```text
Private ROM + PyBoy emulator
            |
            v
Title-specific observation adapter
(Red today; thin Crystal adapter under qualification)
            |
            v
Typed, title-neutral semantic state
(location, capabilities, party, battle, resources, collection, objectives)
            |
            v
Goal manager + quest/dependency graph + living-Dex ledger
            |
            v
Candidate generation -> hard legality/safety masks -> bounded learned ranker
            |
            v
Typed skills and deterministic mechanics
(routing, battle actions, capture, training, inventory, field moves)
            |
            v
Single frame-safe executor -> controller inputs -> game

Independent referee ---------> verified outcomes
Artifact/provenance layer ----> immutable evidence -> read-only dashboards
```

This is intentionally hierarchical. Graph search should own exact geometry; deterministic code
should own legality and safety; learned components should choose among bounded semantic options.
The design avoids asking a model to rediscover facts such as whether a move has PP or whether a
wall is walkable.

### Technology stack

| Area | Technology |
| --- | --- |
| Core implementation | Python 3.11+ with typed dataclasses, protocols, enums, and explicit state machines |
| Emulator | PyBoy 2.7.0 |
| Learning | NumPy 2.x; interpretable linear/ridge rankers and small multilayer perceptron experiments |
| Cartridge authority | Pinned Generation I disassembly data plus direct cartridge-table decoding |
| Storage and integrity | Canonical JSON/JSONL, SHA-256 manifests, create-once files, atomic rename, file locking, `fsync`, source/runtime/ROM identity binding |
| Testing and static analysis | pytest, Ruff, mypy, mutation-style adversarial probes, GitHub Actions |
| Monitoring | Loopback-only Python HTTP dashboards using evidence-projected state |
| Development process | Git/GitHub, source-bound CI, Codex as primary implementation agent, Claude and Antigravity as independent reviewers |

There is currently **no PyTorch or TensorFlow dependency and no LLM in the gameplay runtime**. The
models being evaluated are intentionally small because the immediate question is whether the
semantic features and causal outcomes contain useful signal at all.

## 4. How the agent observes and controls the game

The emulator adapter verifies the private ROM identity, loads it into PyBoy, and exposes a narrow
read-only memory interface plus rendered frames. Revision-specific addresses remain inside the
title adapter. The rest of the system consumes semantic objects rather than raw addresses: for
example, current map, party health and moves, battle phase, bag resources, field abilities, event
facts, collection state, and legal candidate actions.

Control has a strict single-writer boundary. Only the executor may turn a semantic action into
button presses. It uses frame and retry budgets, releases controls between attempts, re-observes
the game after actions, and requires observable evidence that movement, menu selection, battle
action, or field action actually occurred. The referee is separately allowed to observe and verify
results, but it cannot choose or replace an action.

The live dashboard is an observer, not a controller. It can display game frames and authenticated
progress but cannot press buttons or alter counters.

## 5. Planning quests, battles, captures, leveling, inventory, and Pokédex completion

| Domain | Current design | Status boundary |
| --- | --- | --- |
| Quests and story | A validated dependency graph exposes currently available objectives. The goal manager enumerates options, masks impossible ones, ranks them, dispatches a typed skill, then re-observes and replans. Red has 36 semantic completion objectives. | **Working for the deterministic teacher; partial for learned selection.** |
| Navigation | Cartridge-derived map/warp/terrain graphs provide exact routes. Live occupancy, story gates, land/water mode, Cut mutations, Strength state, and interruptions constrain execution. | **Working in qualified Red probes; not learned or cross-title.** |
| Battles | Legal moves are masked using live battle state and PP. Semantic candidate features describe matchup, damage pressure, survival, resources, and action type. Bounded experiments compare all supported actions from the same state. | **Partial.** The current learned candidate is not authorized to control gameplay. |
| Captures | A title-neutral skill can weaken, apply supported status, throw a ball, restore, or abandon under HP, ball, party-space, storage, and attempt bounds. | **Working as deterministic bounded machinery; learned timing and composition remain partial.** |
| Leveling and evolution | Team-training code scores trainees and venues, rotates participation, monitors experience/evolution, and chooses among seek, fight, flee, heal, or stop under resource bounds. | **Working for teacher-managed Red training; learned party-development authority is unfinished.** |
| Inventory and economy | Typed reserve plans track money, healing, balls, PP, required key items, shopping, and safe recovery. Hard guards protect items and party members required for future objectives. | **Working inside supported Red routes; not a general learned inventory policy.** |
| Pokédex completion | The catalog joins encounters, fishing, evolution, gifts, static encounters, fossils, in-game trades, version differences, one-shot opportunities, and blockers. Current ledgers distinguish historical registration from retained living specimens; the roadmap further separates stored, evolved, traded, version-blocked, event-blocked, and unsupported states. | **Working as planning/accounting contracts; autonomous end-to-end execution is planned.** |

The long-term policy is therefore not one giant model predicting buttons. It is a hierarchy in which
learned policies choose meaningful goals and tactics while deterministic subsystems enforce game
rules, safety, exact navigation, and evidence requirements.

## 6. Memory, state tracking, and recovery

The runtime uses structured memory rather than an LLM conversation history:

- **Working memory:** freshly observed semantic state from emulator memory and frames.
- **Task memory:** objective completion, current capability facts, active goal, party/resource
  state, and collection ledger.
- **Episodic learning records:** scenario identity, lineage, candidate menu, committed choice,
  intervention, outcome, and model/runtime identities.
- **Durable experiment state:** immutable manifests, claims, terminals, model files, and path-free
  public receipts.

Experiments use a claim-first protocol: a root and candidate trial are durably claimed before any
controller input. Once activated, success, failure, or interruption remains in the denominator and
cannot be retried or silently replaced. Writes use canonical encodings, hashes, exclusive creation,
atomic replacement where appropriate, synchronization to disk, ownership and symlink checks, and
exact joins across source commit, ROM, runtime, source state, model, and outcome.

After a power loss or process interruption, the system can reconstruct which identities were
claimed and which artifacts were durably written. It may continue only with never-claimed work.
Contradictory or incomplete evidence fails closed. Public receipts omit private paths, ROM bytes,
saves, screenshots, and private model/data payloads.

## 7. Trades, version exclusives, and special events

The acquisition catalog does not treat a single cartridge or save as sufficient. For ordinary
retail Red or Blue, it derives reachability from cartridge data rather than a manually declared
species list:

- The species-level union across ordinary mutually exclusive choices is **135 species** for one
  version without a compatible external trade partner.
- That union reaches **139 species** when the four trade evolutions have a compatible partner.
- The paired version contributes **11 version-exclusive species**.
- Mew remains an external/event requirement rather than being fabricated as normally obtainable.

Those union counts do not mean every choice can coexist on one save. The stricter declared Red
one-save/no-link contract currently targets **124 registered species and 120 simultaneously retained
living specimens**, with explicit exclusions for the other starter, fossil, gift/evolution branch,
version-exclusive, link-evolution, and event-only choices. Its target-level field is 100, but that
contract has not been executed autonomously.

Ten in-game NPC trades are included in the catalog and account for species such as Farfetch'd,
Lickitung, Mr. Mime, and Jynx that are not supplied by ordinary wild/evolution paths.

What is not finished is equally important. A repeatable semantic link-trade executor, second-save
coordination, cross-version specimen consolidation, and a legitimate event-input workflow are not
implemented end to end. The planned contract requires the system to label these blockers
explicitly, use only legitimate supplied event inputs, and preserve living specimens across the
collection rather than merely setting Pokédex flags.

Legendary encounters and game-specific puzzles are planned as prerequisite graphs with one-shot
risk, save/state eligibility, inventory and field-move requirements, and verified capture
outcomes. Red contains deterministic puzzle mechanics, including the qualified Strength sequence,
but autonomous learned planning for every legendary puzzle is not complete.

## 8. LLM reasoning versus deterministic code

No LLM currently observes the game or chooses controller inputs at runtime.

Deterministic code owns:

- emulator I/O and semantic observation;
- cartridge decoding, pathfinding, and exact mechanics;
- legal-action and safety masks;
- quest dependency checks and typed skill execution;
- the independent referee;
- durable claims, provenance, logging, and recovery;
- evaluation partitions and promotion gates.

Small NumPy models are being evaluated for bounded ranking decisions: which legal battle action,
navigation recovery, party-development option, or high-level collection goal has the best expected
outcome. Their predictions are advisory until held-out outcome gates justify authority.

LLMs are used in the **engineering workflow**, not hidden inside the player:

- **Codex:** primary implementation, integration, testing, documentation, and publication agent.
- **Claude:** independent statistical, leakage, evaluation-language, and experimental-design review.
- **Antigravity:** independent architecture, portability, abstention, Crystal, and trust-boundary
  review.
- **Pete:** human product owner and final decision-maker who defines the objective, authorizes
  irreversible experiments, adjudicates reviewer disagreements, observes runs, and accepts or
  rejects results.

## 9. Validation, testing, logging, guardrails, and failure handling

The published baseline passed **6,082 pytest tests**, with 4 skipped, 3 deselected, and 1 expected
failure, plus Ruff, mypy, public-artifact, documentation, and product-focus gates. ROM-free tests
cover public CI; private-ROM checks are explicitly separated as integration work.

The important validation mechanisms are:

- an independent semantic referee for completion and skill outcomes;
- prospective train/development/sealed partitions at the lineage level;
- prediction commitment before development outcomes are opened;
- complete candidate measurement from identical source states where the contract permits it;
- no retry, replacement, optional stopping, or outcome-aware row selection;
- identity-free policy features and a ban on teacher-choice labels in causal outcome learning;
- exact source, runtime, ROM, state, dataset, and model hashes;
- bounded controller actions, frames, retries, healing, resources, and interventions;
- create-once terminal records that preserve infrastructure failures and negative model results;
- path sanitization and automated checks preventing private artifacts from entering GitHub;
- read-only dashboards projected from evidence rather than mutable progress counters.

One useful example of the guardrails working is the latest model result. Training loss fell from
**2.0818 to 0.7190**, but the frozen prior and candidate chose the same correct action on the held
development state. With zero discordance there was no demonstrated advantage, so the candidate was
rejected and received no authority. A lower training loss was not renamed as success.

## 10. Most difficult engineering problems solved so far

1. **Separating a successful teacher from learned competence.** A scripted teacher can finish the
   game while producing low-value demonstrations. The project now measures learned authority and
   held-out outcomes separately from teacher completion.
2. **Replacing expensive full runs with authenticated short scenarios.** One clean-power supply
   attempt spent 208,777 controller actions and 32,312,041 frames and yielded 0 usable roots from
   12 assignments. The result was preserved and the strategy was stopped rather than patched into
   another multi-day replay.
3. **Creating causal, leakage-resistant evidence.** The system had to define upstream lineages,
   freeze partitions prospectively, measure selected actions without inventing counterfactual
   labels, commit predictions before outcomes, and retain all failures.
4. **Turning emulator bytes into stable semantics.** Game-specific RAM, cartridge tables, map
   topology, dynamic objects, menus, battle phases, party/box state, and story flags are normalized
   behind typed adapters so higher layers do not depend on raw addresses.
5. **Reliable closed-loop control.** The executor must distinguish acknowledged motion from wall
   collisions, moving NPCs, battle or menu interruptions, field-mode changes, and actual story
   gates while avoiding unbounded retries.
6. **Crash-safe one-shot experimentation.** Power loss cannot make an inconvenient trial disappear
   or cause it to execute twice. Claims, terminals, hashes, and artifact joins make the experiment
   resumable without weakening its denominator.
7. **Designing for transfer before transfer exists.** Red-specific mechanics are kept behind an
   adapter while policy-facing features, option types, collection state, abstention, and
   intervention contracts remain title-neutral enough to be falsified in Crystal later.

## 11. Concrete metrics and verified milestones

| Milestone | Verified result | Correct interpretation |
| --- | --- | --- |
| Deterministic Red completion | 47,317,703 frames; 664,751 controller actions; 21/21 selected objectives; 36/36 observed objectives; 74/74 scheduled battles; Champion and Hall of Fame; final party 66/55/55/55/55/55 | Complete teacher/mechanics/referee integration, **not** autonomous learned completion |
| Mixed-stack canonical integration | 50,997,251 frames; 723,826 actions; 36/36 objectives; Hall of Fame; 3,248 model move decisions, 64,337 training-control decisions, and 125,800 trainee/venue decisions | One uncounted canonical-root integration inside deterministic scaffolding; not broad learned authority |
| Semantic completion contract | 312/312 semantic checkpoints and 36/36 objectives in qualified clean-power runs | Strong Red verification coverage |
| Cartridge-derived world model | 220 reachable maps, 78 reciprocal connections, 48,216 standable coordinates, 154,653 directed land edges, 749 ledge transitions | Static and typed traversal knowledge, not proof every route is always open |
| Live navigation probes | Center 86/86 steps; Mart 108 acknowledged of 112 requests with two replans; Surf 13/13; visible-object 43/43; repeated Cut 110/110; Strength 267 derived puzzle steps; Saffron 11/11 after closed/unknown rejection | Closed-loop deterministic navigation in qualified Red contexts |
| Learned strategic destination scorer | 24 train and 12 held development examples; 10/12 held versus route-cost baseline 4/12; paired 6 wins/0 losses; exact p=0.03125 | Genuine held learned result, still with no live navigation authority |
| Retail Red/Blue acquisition analysis | 135 solo species; 139 with compatible trade partner; explicit 11-version-exclusive and Mew blockers | Correct dependency accounting, not an executed living Pokédex |
| Strict one-save Red collection contract | 124 registration targets and 120 simultaneously retained living targets, with explicit exclusions | A declared/accounted target, not an autonomous completed collection |
| Bounded learned acquisition | Model selected acquisition at probability 0.7821; 665 actions; 33,672 frames; exact specimen preservation verified | One development decision, not general gameplay authority |
| Authentic learning board | 19 causal train examples; 6 fits; 6 verified development outcomes; 4 unseen comparisons | A real but still small training/evaluation base |
| Latest battle learning pair | 3 train and 3 development candidate actions measured; loss 2.0818 -> 0.7190; no teacher queries; predictions committed before development; zero development discordance | Candidate correctly rejected; no authority gain |
| Failed clean-power data supply | 0/12 usable roots after 208,777 actions and 32,312,041 frames | A costly hypothesis was falsified and stopped |
| Published validation baseline | 6,082 tests plus Ruff, mypy, artifact, documentation, and focus gates green | Repository quality and governance evidence, not model quality |

## 12. Pete's role

Pete's most accurate title on the project is **product owner and AI-systems director**. He should
not imply that he personally hand-wrote every source file; his material contribution was defining
the system, acceptance criteria, work process, and evidence standard while directing AI coding
agents.

Concretely, Pete:

- repeatedly defined the end product as a transferable player that finishes games and builds a
  living Pokédex, not a fixed Red walkthrough;
- required full-party, capture, evolution, trade, version, legendary, and resource mechanics when
  narrower completion routes would have been easier;
- identified visible runtime problems such as Saffron wall collisions, overly conservative healing,
  and starter-dominated training;
- established Codex as the implementation workhorse and Claude/Antigravity as independent
  reviewers with different specialties;
- reviewed plans and results, challenged focus drift, required reorientation to the mission, and
  adjudicated disagreements rather than automatically accepting any model's recommendation;
- supplied the local runtime and legally obtained game inputs, observed dashboards and live runs,
  handled power-loss/restart realities, and authorized one-shot experiment boundaries;
- required prospective gates, no-retry rules, honest negative results, GitHub documentation, and
  evidence suitable for external audit.

An interview-safe description is:

> I defined the product and acceptance criteria, decomposed it into teacher, observer, planner,
> learner, executor, referee, and evidence layers, used Codex as the primary implementation agent,
> used Claude and Antigravity as independent reviewers, and personally adjudicated trade-offs and
> accepted or rejected results. My focus was making AI-assisted development auditable rather than
> treating generated code or a successful demo as proof.

## 13. Current limitations and unfinished work

- The learned model does not yet have controller or gameplay authority.
- No learned model has autonomously completed Red.
- No living Pokédex has been autonomously assembled.
- Crystal has no realized gameplay outcome, zero-shot comparison, adaptation result, or transfer
  evidence.
- The causal corpus is small and outcome-imbalanced; the latest candidate showed no held
  development advantage.
- The immediate battle policy optimizes a short-horizon outcome and may need a richer state,
  action set, or horizon if V2 again lacks meaningful discordance.
- Multi-skill composition is demonstrated only in narrow cases, not across an entire autonomous
  campaign.
- Link trading, second-save/version orchestration, living-specimen consolidation, and legitimate
  event ingestion are not complete.
- Crystal-specific mechanics such as day/night, friendship, breeding, held items, roaming
  encounters, phone/weekly events, berries, and title-specific puzzles still require adapters and
  adaptation evidence.
- Many Red capabilities are mature deterministic scaffolding. Their existence does not prove that
  a learned policy can select and compose them under changed conditions.
- The V2 curriculum remains unmerged engineering work and has not collected its fresh outcomes.

The next meaningful milestone is not another full Red replay. It is a prospectively frozen,
lineage-diverse V2 battle batch that can either show held-out candidate/control discordance or
falsify the current short-horizon representation. Only after battle, navigation, and
party-development policies pass bounded Red gates should any learned authority be promoted and a
frozen title-neutral bundle be tested in Crystal.

## 14. Concise repository and file overview

| Area | Key files/directories | Purpose |
| --- | --- | --- |
| Product truth | `MISSION.md`, `NORTH_STAR.md`, `ACTIVE_PRODUCT_STATE.md` | Permanent objective, anti-drift rules, one current lane and counters |
| Long-range plan | `docs/model-first-roadmap.md`, `docs/red-to-crystal-readiness-roadmap.md` | Evidence ladder from Red scenarios to authority and Crystal transfer |
| Emulator and observation | `src/pokemon_red_completion/emulator.py`, `observation.py`, `domain.py` | PyBoy boundary and typed Red semantic state |
| Control and verification | `executor.py`, `player_loop.py`, `referee.py` | Sole controller authority, closed-loop execution, independent outcomes |
| Quest and hierarchy | `quest.py`, `goal_manager.py`, `red_goal_manager.py`, `objective_skills.py` | Dependency graph, candidate goals, ranking, typed skill dispatch |
| Navigation and mechanics | `gen1_cartridge.py`, `gen1_maps.py`, `gen1_terrain.py`, `semantic_traversal.py`, `global_router.py`, `gen1_cut.py`, `gen1_strength.py` | Cartridge-derived world model and bounded field mechanics |
| Battle and learning | `battle_semantics.py`, `battle_runtime.py`, `battle_outcome_learning.py`, `battle_neural_model.py`, `battle_outcome_batch.py` | Legal semantic actions, scenario outcomes, small models, V2 curriculum |
| Party, capture, resources | `capture.py`, `party.py`, `training.py`, `team_training.py`, `resource_economy.py` | Capture, development, evolution, rotation, inventory and recovery |
| Living Pokédex | `pokedex.py`, `red_pokedex.py`, `red_acquisition.py`, `collection_ledger.py`, `red_collection.py` | Species accounting, acquisition dependencies, blockers and preserved specimens |
| Integrity and recovery | `private_artifacts.py`, `provenance.py`, `runtime_identity.py`, claim-first modules | Immutable private records, source/runtime binding, one-shot recovery |
| Crystal boundary | `src/pokemon_crystal_completion/` | Bank-aware observation, capability masks, transfer and qualification contracts |
| Operations | `scripts/` | Freezers, preflights, one-shot runners, audits, fit commands and dashboards |
| Frozen configuration | `configs/` | Source-bound registries, plans, digests, active product focus and experiment contracts |
| Proof and quality | `docs/evidence/`, `tests/`, `.github/workflows/ci.yml` | Path-free receipts, ROM-free regression tests and CI |

The repository currently contains roughly **323 Python source files, 431 test files, and 527 public
JSON evidence receipts**. Those counts show project scale; they should not be presented as model
capability.

## Claims to use and claims to avoid

### Accurate

- “The deterministic teacher can complete Pokémon Red under an independent semantic referee.”
- “I built an authenticated scenario-to-model-to-held-out-evaluation pipeline.”
- “The latest candidate improved train loss but showed no held-out advantage, so we rejected it.”
- “The architecture is designed to test whether semantic skills transfer from Red to Crystal.”
- “The system explicitly models trade, version, event, and one-shot collection blockers.”
- “I directed multiple AI coding agents with separated implementation and review roles.”

### Not yet accurate

- “The AI model beat Pokémon Red.”
- “The model completes the Pokédex.”
- “The agent transfers to Crystal.”
- “An LLM watches the screen and plays the game.”
- “The project is reinforcement learning from scratch.”
- “Every planned architecture component is production-ready.”
