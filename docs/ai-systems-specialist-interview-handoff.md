# AI Systems Specialist interview handoff: transferable Pokémon agent

Updated: 2026-09-12

Repository: [PeteAndrews1289/pokemon-red-completion-agent](https://github.com/PeteAndrews1289/pokemon-red-completion-agent)

This handoff describes only the active completion-agent repository. It does not use claims from the
concluded predecessor project.

## Interview-safe summary

> I am directing an AI-assisted systems project to build a hierarchical Pokémon player. A learned
> planner chooses useful semantic goals—such as where to search, whether to develop the team, or how
> to restore resources—while deterministic, verified skills handle exact movement, menus, battles,
> captures and safety. Pokémon Red is the first curriculum, not the final product. The current
> model has 111 settled training examples and its latest durable save has 83 verified Pokédex
> registrations. The last two four-way choices produced one new registration and one honest route
> failure; both were retained as lessons. A deterministic teacher has completed Red, but the learned
> player has not yet independently completed the game, finished the Pokédex, or transferred to
> another title.

Status terms in this document:

- **Working** means implemented and supported by current evidence.
- **Partial** means real bounded behavior exists but does not establish end-product competence.
- **Planned** means designed or represented in the roadmap but not demonstrated.

## 1. Objective and current status

The objective is a model that can enter a Pokémon game, finish its story, respond to changed state,
and accumulate one shared, verified registered Pokédex across runs, versions, legitimate trades and
legitimate event inputs. A species needs global credit once; the system still keeps global credit,
each save's local Pokédex flags, and physical party/box specimens separate.

The delivery sequence is Red, Blue/shared-ledger integration, an unfamiliar compatible Red ROM
modification as the first adaptation test, then Crystal and later titles. Crystal is currently on
the backburner so the project can first establish sustained model-directed Red play.

| Layer | Status | Current evidence boundary |
| --- | --- | --- |
| Red teacher, mechanics and verification | **Working** | Deterministic checkpoint-based runs reached Champion and Hall of Fame under semantic verification. |
| Bounded learned Red goal selection | **Partial** | Model111 has 111 settled training-only examples; models have selected real resource, recovery, evolution, capture and destination goals. |
| Current retained Red state | **Working** | 83 registered species, 63 living species and 67 specimens reopen at an authenticated checkpoint. |
| Sustained autonomous Red player | **Partial / unfinished** | The hierarchy can execute bounded chains, but unsupported route interruptions, empty/forced menus and deterministic support still prevent an independent start-to-finish claim. |
| Modified-Red, Blue and Crystal transfer | **Planned** | Contracts and some adapters exist, but no transfer result is claimed. |

The immediate task is deliberately narrow: make route eligibility reflect what the executor can
actually handle, recover model111 from a retained scripted-dialogue interruption without awarding a
training label, rebuild the action-free candidate menu, and permit one fresh supported model choice.

## 2. What the system can demonstrably do now

### Working

- Observe Red through PyBoy and project emulator state into typed semantic objects covering
  location, party, battle, inventory, capabilities, events, storage and Pokédex state.
- Decode cartridge-derived maps, terrain, warps, ledges, encounters, fishing, evolutions and
  in-game trades.
- Route and execute supported movement, field actions, menus, battles, captures, training,
  evolution, storage and resource recovery with bounded deterministic skills.
- Verify outcomes independently, preserve exact save/model lineage, and recover after process or
  power interruption without silently replaying consumed choices.
- Keep shared registrations separate from locally owned flags and physical specimens.
- Fit a small option-value model incrementally from eligible selected outcomes, including failures
  and measured resource cost.
- Show saved evidence, training state, live frames when a runner is attached, and engineering work
  in a read-only local dashboard.

### Partial

- The learned planner has made bounded live choices among identity-free semantic candidates. It
  does not choose raw coordinates or button sequences.
- The latest successful choice selected one of four fishing destinations, used 542 controller
  actions and 31,464 frames, made five casts, and changed the registered count from 82 to 83.
- The next four-way choice used 435 actions and 14,832 frames before an unsupported scripted
  dialogue stopped the route. It made no collection gain and was retained as training row 111.
- Model-selected collection, evolution, recovery, supply and income chains have run in related
  development states. They are useful curriculum evidence, not independent generalization.
- A shared-Pokédex planner can account for acquisition dependencies and blockers, but it cannot yet
  autonomously finish the complete campaign.

### Planned

- Independent, sustained model-directed play from a fresh game through story completion.
- Completion of all legitimate Red registration targets, followed by shared-ledger Blue work.
- Measured initial performance and adaptation on an unfamiliar compatible Red modification.
- Crystal and later-title adaptation, cross-save trades and legitimate event integration.

## 3. Architecture and technology stack

```text
Private cartridge + PyBoy
        -> title-specific observer
        -> title-neutral semantic state and memory
        -> dependency planner and available-goal generator
        -> legality/capability masks
        -> learned option-value ranker
        -> deterministic typed skill
        -> single controller executor
        -> independent outcome checks
        -> checkpoint, evidence and incremental fit
```

| Area | Technology |
| --- | --- |
| Core | Python 3.11+, dataclasses, protocols, enums and explicit state machines |
| Emulator | PyBoy 2.7.0 |
| Learning | NumPy-based regularized multi-outcome option-value models |
| Knowledge | Direct Generation I cartridge decoding plus pinned disassembly-derived authority |
| Memory | SQLite shared-registration ledger, per-save state and hash-linked JSON/JSONL artifacts |
| Integrity | SHA-256 identities, create-once records, atomic writes, locks, `fsync` and source/runtime/ROM binding |
| Quality | pytest, Ruff, mypy, publication checks and GitHub Actions |
| Observability | Loopback-only Python HTTP dashboard with HTML, CSS and JavaScript |
| Development | Git/GitHub; Codex implementation; Claude and Antigravity independent review |

There is no LLM in the gameplay runtime and no claim that a language model is visually playing the
game. The current learner is intentionally small and interpretable.

## 4. How the agent observes and controls the game

The Red adapter reads revision-specific emulator memory and frames, validates coherent state, and
emits semantic observations. Higher layers see facts such as available field capabilities, party
condition, money, capture supplies, collection pressure and legal goals rather than raw addresses.

Only the executor may issue controller input. It turns a typed action into button presses, advances
bounded frames, releases controls, re-observes, and checks that the expected state change occurred.
Moving NPCs, menus, encounters, story dialogue and failed movement can interrupt execution; the
runner either handles a declared interruption or stops with the exact failure retained.

The teacher and referee do not share action authority. The teacher can create curriculum states,
demonstrate mechanics or provide declared safety support. The referee observes postconditions but
cannot substitute a better action. The dashboard is read-only.

## 5. Planning quests, battles, captures, leveling, inventory and Pokédex completion

| Domain | Approach | Status |
| --- | --- | --- |
| Story and quests | Dependency graph exposes currently achievable semantic objectives. | Teacher path works; model composition is partial. |
| Navigation | Cartridge-derived graph search computes exact geometry; live gates and capabilities constrain execution. | Strong Red mechanics; current dialogue capability mismatch is open. |
| Battles | Legal moves and switches are filtered from live state and PP; tactical execution is bounded. | Deterministic support works; learned general battle authority is unfinished. |
| Captures | Search, encounter, weaken/status where supported, throw, verify and preserve state under supply/storage bounds. | Bounded Red captures work. |
| Leveling/evolution | Choose useful missing evolutionary lines and train only as far as a needed registration or team role requires. | Several chains work; general scheduling remains partial. |
| Inventory/economy | Track prices, reserves, healing, capture items and legitimate income options. | Bounded supply and income paths work; sustainable general policy is unfinished. |
| Pokédex | Shared registration demand combines encounters, fishing, evolutions, gifts, fossils, trades, version differences and blockers. | Accounting works; autonomous completion is planned. |

The system does not require every Pokémon to reach level 100 or every form to remain simultaneously
stored. After story completion it should catch a missing line, evolve only for missing registrations,
deposit when practical, and continue. Duplicates are allowed but do not earn repeated novelty credit.

## 6. Memory, state tracking and recovery

- Working memory is the current semantic emulator observation.
- Task memory tracks objectives, capabilities, resources, owned specimens and collection demand.
- Shared memory records globally verified species registrations across runs without fabricating a
  local specimen or local Pokédex flag.
- Episodic memory records the candidate menu, selected probability, chosen action, intervention,
  result, cost and model identity.
- Durable checkpoints bind save state, model, corpus, code and evidence by hashes.

Consumed model choices are not retried simply because they failed. Interrupted or incomplete work
remains distinguishable from success and failure. After a crash, the system authenticates the last
durable checkpoint and continues only through an allowed recovery boundary. Public receipts omit
ROM bytes, saves, private paths and private training artifacts.

## 7. Trades, version exclusives and special events

The catalog derives what each cartridge can supply and labels what requires another source. It
recognizes version exclusives, four link-trade evolutions, mutually exclusive starters/fossils/gifts,
ten in-game NPC trades, static and legendary encounters, and event-only species such as Mew.

The product plan is to run Red and Blue against the shared registry, perform legitimate cross-save
or cross-version trades where required, and award global credit only after verified acquisition.
Later generations add time, friendship, breeding, held items, roaming encounters and title-specific
puzzles behind new adapters. A missing event input remains an explicit blocker; the system must not
fabricate availability or edit the save to set a Pokédex flag.

Repeatable link-trade execution, multi-save consolidation and event workflows are not yet complete.
Legendary prerequisite graphs and one-shot risk handling exist as design requirements, but every
special puzzle has not been autonomously solved.

## 8. Where LLM reasoning is used versus deterministic code

Deterministic runtime code owns observation, cartridge mechanics, pathfinding, legal actions,
safety, controller input, postcondition checks, persistence and evaluation boundaries. The small
NumPy learner ranks bounded semantic alternatives using recorded outcomes.

LLMs are engineering collaborators:

- Codex performs the primary implementation, integration, testing, documentation and publication.
- Claude reviews statistics, leakage, claim language and experimental design at useful gates.
- Antigravity reviews architecture, portability, abstention and broader implementation concerns.
- Pete defines the product and constraints, directs the agents, reviews trade-offs, observes runs
  and accepts or rejects results.

An LLM review is not gameplay evidence. Reviewer suggestions are adjudicated against executable
tests, preserved results and the mission rather than accepted automatically.

## 9. Validation, logging, guardrails and failure handling

- Public CI runs ROM-free tests, linting, typing, documentation and private-artifact guards.
- Private runs bind the cartridge, source, runtime, state, corpus and model identities.
- Model menus omit title-specific identity fields and record selection probability.
- Actual selected outcomes—including zero-gain failures and cost—enter the eligible dataset; no
  unobserved alternative receives an invented target.
- Forced support, safety overrides and teacher actions remain separate from learned choices.
- Controller actions, frames, attempts, resources and interventions are bounded and logged.
- Checkpoints and terminals are create-once or hash-linked so a crash cannot erase an inconvenient
  result.
- Independent evaluation and authority promotion remain separate from in-sample fitting.
- The dashboard reconstructs claims from evidence and cannot control the emulator.

CI verifies engineering integrity; it is not model training and does not prove the player is good.
The project now batches meaningful changes before CI instead of treating repeated workflow runs as
progress.

## 10. Most difficult engineering problems solved so far

1. Separating deterministic teacher completion from learned competence.
2. Turning raw emulator and cartridge state into stable, typed, title-neutral semantics.
3. Preserving one truthful lineage across model choice, controller execution, outcome, fit and
   restart—even through power loss or reporter failure.
4. Preventing outcome leakage, invented counterfactual labels and retries of consumed choices.
5. Building a shared registry without confusing global credit, local flags and physical specimens.
6. Composing learned high-level judgment with deterministic low-level skills and explicit safety
   boundaries.
7. Retaining partial progress and failure costs instead of discarding an episode because its final
   goal failed.
8. Identifying focus drift: a reliable teacher, green CI and more infrastructure are not substitutes
   for new model-controlled decisions.

## 11. Concrete metrics and verified milestones

| Milestone | Verified result | What it establishes |
| --- | --- | --- |
| Deterministic Red integration | Champion and Hall of Fame reached under semantic verification | Teacher, mechanics and referee can compose; not learned autonomy. |
| Current collection state | 83 registrations, 63 living species, 67 specimens | Real retained Red progress; not Pokédex completion. |
| Current learner | 111 settled training-only examples, 76 successful | Incremental selected-outcome training works; not 111 independent games. |
| Latest successful choice | Four candidates; probability 0.087610; 542 actions; 31,464 frames; five casts; registrations 82→83 | A model-selected destination produced a verified gain. |
| Latest retained failure | Four candidates; probability 0.292434; 435 actions; 14,832 frames; no gain | Failure and cost survived and became row 111; no retry. |
| Latest fit | Weighted in-sample MSE 0.031432→0.011165 | The model fit the complete eligible corpus; no independent advantage claim. |
| Latest loop boundaries | 0 teacher labels, 0 authority promotions, 0 sealed/Crystal accesses | The result stayed inside bounded Red development. |

The current model artifact is identified publicly by SHA-256
`2eb854c7bc267a907fd5ffaf4037e06266bd9c1cc120fa335c011b59b7bbbaa9`.

## 12. Pete's role

Pete's accurate role is product owner and AI-systems director. He did not claim to hand-write every
line. He repeatedly defined the end product, rejected shortcuts that optimized only a fixed Red
route, required collection/evolution/resource/version/trade behavior, chose the agent workflow,
challenged focus drift, reviewed architecture decisions, supplied and observed the local runtime,
and validated whether results matched what appeared in the game and dashboard.

An interview-safe description is:

> I defined the product, acceptance criteria and evidence boundaries; decomposed the system into
> observer, planner, learner, skills, executor, referee and memory; directed Codex as the primary
> implementation agent; used Claude and Antigravity as independent reviewers; and adjudicated the
> trade-offs. My contribution was systems direction and validation—making AI-assisted engineering
> produce testable, honest artifacts rather than treating generated code as proof.

## 13. Current limitations and unfinished work

- No learned model has independently played Red from title screen through Hall of Fame.
- The current 111 examples are related development outcomes, not 111 independent games.
- The latest fit has no independent evaluation or promoted authority.
- Route eligibility still needs to reflect scripted-dialogue capability before the next menu.
- Low-level navigation, battle, capture and menu control remain primarily deterministic.
- Red registrations are incomplete: 41 required Red registrations remain in the current contract.
- The system has not autonomously completed the shared Pokédex.
- Blue integration, link trades, legitimate event inputs and modified-Red adaptation are unfinished.
- Crystal has not been used as transfer evidence; later-generation mechanics need adapters.
- Generalization to random starts, changed timing/RNG, unseen ROM modifications and new games is
  still a research goal, not a demonstrated capability.

## 14. Concise repository and file overview

| Area | Starting points |
| --- | --- |
| Product truth | `MISSION.md`, `NORTH_STAR.md`, `ACTIVE_PRODUCT_STATE.md` |
| Immediate restart | `HANDOFF.md`, `docs/current-agent-handoffs.md` |
| Current plan | `docs/model-first-roadmap.md`, `docs/development-roadmap.md` |
| Architecture | `docs/architecture.md`, `src/pokemon_red_completion/` |
| Observation/control | `observation.py`, `red_player_observer.py`, `red_bounded_player.py`, executor and referee modules |
| Learning | `living_dex_option_value.py`, `red_player_model.py`, `red_player_incremental_fit.py`, training-dataset modules |
| Collection/memory | registration, collection, acquisition, evolution, storage and SQLite ledger modules |
| Crystal boundary | `src/pokemon_crystal_completion/`, `docs/crystal-transfer-benchmark.md` |
| Operations | `scripts/`, `configs/` |
| Proof | `tests/`, `docs/evidence/`, `docs/work-sessions/`, `.github/workflows/ci.yml` |

The exact current restart and evidence are in the
[model111 session](work-sessions/2026-09-12-model111-fishing-learning-loop.md). Historical receipts
remain immutable; the [documentation map](README.md) explains which files are current instructions
and which are preserved history.
