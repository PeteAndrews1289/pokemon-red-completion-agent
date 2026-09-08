# Retained Ekans evolution: failed execution, exact-state audit

Date: 2026-09-08 UTC. This is same-lineage training practice, not evaluation.

## What happened

Model67 continued from the actual saved Route4 endpoint. Cartridge rules and
owned inventory supplied the Ekans-to-Arbok objective while preserving a second
Ekans. All three regional proposals offered actual capture, evolution and team
recovery alternatives. The source proposal was Route11; the model then selected
**evolve_species** with recorded probability0.3354761832972618. The source
proposal is not an independently fitted choice.

Ekans reached level11 from6, but evolution stopped during a wild Drowzee9 battle.
The component raised **Team training lacks a safe collection finisher.** Terminal
certification then correctly rejected the mid-battle state. No Arbok, admitted
terminal checkpoint, new corpus row or model fit was produced. The partially
logged outcome event is not an admitted training result.

| Measure | Verified result |
| --- | --- |
| Controller actions / emulator frames | 2,751 / 217,562 |
| Observed wild encounter entries | 29; not claimed as29 wins |
| Exact failure location | Route11 (13,6), wild battle, input not ready |
| Trainee / retained base | Ekans11 in party; Ekans6 in box |
| Collection | 27 specimens,26 distinct living species,31 registered; no losses |
| Resources | Two capture items and209 currency retained |
| Observed faints | 0 |
| Fitted model | Unchanged:67 outcomes,28 successful,57 distinct selected rows |
| Training inventory | Unchanged:46 native episodes,16 regional choices |
| Intermediate saves | Six safe-quantum diagnostic records |
| Exact failure bytes | 167,677 bytes; two identical captures, exact round-trip |

## Root cause, not just the final exception

The collection trainer's field check asks for a usable finisher at the venue's
encounter level without the actual opponent's type. Structural venue coverage
checks whether some member could handle each encounter **after resource recovery**.
That is not a current-resource guarantee. The actual battle repeats the finisher
check with the opponent species and can reject every member.

This happened here under the existing90%HP and16-usable-PP reserve policy:

| Member | Why it could not finish this battle under current policy |
| --- | --- |
| Ekans11 | Trainee; also fails level and Psychic matchup checks |
| Dugtrio55 | Only10 usable immediate-damage PP; not above16 reserve |
| Snorlax55 | Only15 usable PP; recoil attacks excluded |
| Jolteon55 | Poisoned, despite57 usable PP and90.4%HP |
| Blastoise64 | 181/203HP =89.16%, below90% recovery threshold |
| Primeape28 | Healthy with40 usable PP, but Psychic opponent matchup rejected |

Primeape can pass the field check, allowing another encounter, then fails the
actual Drowzee matchup. The loop raises when the finisher is absent **before**
its battle escape/recovery handling. This is a deterministic readiness/recovery
mismatch, not evidence that the game is unwinnable or that the model chose an
inherently impossible collection goal. Do not fix it by silently lowering reserves,
allowing poisoned finishers, or treating resource-free checks as combat permission.

## What the previous diagnostic repair did accomplish

Unlike the earlier lost Route10 endpoint, both failure callbacks durably saved
the exact state. Seven manifest streams verify against their recorded lengths
and hashes. The latest safe quantum is154actions/12,326frames before the failure:
Route11(12,6),field,input ready,at2,597actions/205,236frames.

Both the exact failure and last quantum were loaded and inventoried without
controller input or frame advancement. Both contain all27 specimens. They remain
diagnostic states, not automatically admitted continuations or labels. Rewinding
to the quantum would discard real play and must not be presented as uninterrupted
recovery. Prefer qualifying a bounded safe exit from the actual retained failure.

- Execution source: `7216df1c0468540c2e945b0928dcbdd706f2740f`.
- Executable bundle: `38d4b4081ad89df99ced9bc4e8f65c6e815c34481ea4b2e3724eb482aa928771`.
- Episode: `red-retained-ekans-20260908-causal`.
- Failed manifest: `70101e05aca67e5e6f90f274148bcdeb903e0092162738a53a746d6b4cadcf7f`.
- Exact failure state: `ad5ab1f28c844bbd2ca912abf5a3a2e70e225ee61049c74fe74d07c75062a736`.
- Last quantum: `63aaa2e380f6c88b9ef49f09808266d1708719ca9b2e163f88aa53a209722eff`.
- Path-free [detailed evidence](../evidence/red-retained-ekans-failure-2026-09-08.json).

## Review and next work

252focused tests passed across collection shared experience, owned-evolution
inventory, regional goal/proposal handling, checkpoints, incremental fit and
viewer/roadmap contracts. These tests do **not** cover the newly observed
field-to-actual-opponent recovery mismatch. Green existing tests are not a fix.
No source implementation was changed or gameplay retried in this session.

Closeout documentation/public-artifact checks and repository lint passed. The
regenerated roadmap was visually inspected; dashboard status names the failure
and explicitly labels the older Route4 admitted save as historical. No game or
fit process remains active. No fresh full-suite or green-CI claim is made.

The completed useful-acquisition3/3 checklist is preserved in roadmap history.
The next safe-evolution checklist is1/3: exact diagnosis done, guarded recovery
qualification unfinished, useful evolution and fit unfinished. Phase3 remains
current. This is not another completed learning milestone.

Next session is bounded maintenance for this named lesson:

1. Exercise the actual collection loop with different opponent types and depleted
   helper resources; make the field/battle mismatch observable in ROM-free tests.
2. Require current-resource finisher coverage before seeking an encounter, and
   provide a separately guarded escape path if no combat finisher exists mid-battle.
   Keep finite waits, input budgets, collection retention and zero-faint checks.
3. Qualify recovery from the retained exact state without changing the consumed
   episode's failure or pretending its partial record was fitted. Only after a
   genuinely safe endpoint exists should a separately declared learned continuation run.

Stop on unsupported retreat, collection loss or unverifiable state; no replay,
teacher, sealed Red, Crystal or broad architecture expansion. No external agent
was used or remains pending, and no new provider-quota reading was taken.
Recommendation: Astra High, Fast off for the narrow recovery repair and review.
