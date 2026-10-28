# Pokémon Red audit and Windows roadmap

> Documentation role: historical scoped plan. The original trial, budget and
> results below retain their date-specific scope. For current work follow
> [HANDOFF](../HANDOFF.md) and latest user direction; this page is not a dispatch.


Windows MAIN, October 17 2026. Hardware and timing observations were collected between 12:58 and 1:06 a.m. Eastern. A terminal review at 1:16 a.m. Eastern verified the new story win and postgame stop described below. This is an audit and plan, not a new actual launch.

## Decision

Keep the existing local player, battlers, recorder, referee and supervisor. The next improvement should make their composition reliable and efficient before adding more simultaneous full campaigns. This PC has ample CPU capacity for a two-worker development pilot. Memory, package overhead and useful progress per hour should determine whether to expand further.

The working source, Git history, fitted models, helpers, runtime, tests and relevant failed checkpoints are available on Windows. The unfinished historical archive does not prevent development. It still matters when a future learning task needs a particular original TRAIN dataset or provenance record.

## Current campaign and what its result will establish

The actual stopped at 1:07:28 a.m. Eastern. Terminal authentication verifies **Champion defeated, concurrent Hall of Fame state, and 117/124 registrations**, including a legitimate Mewtwo capture. The existing capture support spent the Master Ball on Mewtwo. The original party is fully restored, controls are released, and the exact final state/context and all costs are preserved.

The stop is `RedLiveOptionMenuError`: the postgame menu has zero executable candidates in Celadon Game Corner. Its last completed model-selected coin purchase spent 29,000, leaving 329 cash and 2,550 coins. There are zero execution errors, one admission error and three ordinary setbacks in this attempt. The immediate task is copied diagnosis and qualified same-save continuation under the existing repair authority.

The seven remaining declared registrations are **Porygon, Articuno, Zapdos, Moltres, Dratini, Dragonair and Dragonite**. The story condition is now earned; all 124 registrations are still required in this same save.

The Windows lineage contains seven actual restored launches, one separate failed pre-emulator launch, and seven native terminal stops, including the new postgame admission stop. Their errors, partial tails, earned resources and costs remain. This is restored DEVELOPMENT. A completed result would demonstrate supported same-save completion; it would not retroactively become an unchanged fresh frozen acceptance run.

The existing cutoff remains **3:49:36 a.m. Eastern on October 17**. The 15-minute monitor and qualified repair authority remain active across this repairable stop within the original limits. No successor has been launched at the terminal review; continuation requires copied qualification. This plan creates no extension or new game budget.

When the campaign ends:

1. Authenticate native exit, released controls, the final paired state/context, nested errors and cumulative actual plus diagnostic costs.
2. If complete, preserve Champion/Hall of Fame evidence and the 124 ledger without replaying the completed save.
3. If incomplete at the cutoff or a cumulative cap, retain the exact terminal and next blocker. Any later gameplay needs a newly bounded work order; the monitor must not revive it automatically.

## Hardware and usable capacity

| Component | Measured configuration | Practical consequence |
| --- | --- | --- |
| CPU | AMD Ryzen 9 9900X, 12 physical cores and 24 threads | Plenty of capacity for separate emulator processes and bounded test jobs. One campaign cannot automatically use all those cores. |
| RAM | 32 GB installed class, approximately 31.1 GiB visible to Windows | Enough to begin a two-worker pilot; simultaneous worker memory and Windows headroom need measurement. |
| GPU | GeForce RTX 5060 Ti, 16 GB VRAM confirmed by NVIDIA's tool | Available for future suitable learning workloads. Current emulation and goal inference do not use a CUDA training stack. |
| Storage | WD Green SN3000 2 TB NVMe SSD; approximately 1.84 TB free on C | Capacity is currently comfortable. Small-file counts, archive validation and journal growth still affect throughput. |
| WSL2 | 24 logical CPUs exposed; approximately 15.2 GiB RAM and 4 GiB swap | This is the current Linux envelope, not an additional pool of physical RAM. |
| WSL filesystem | Approximately 891 GiB free within its present virtual filesystem | Keep active Linux work here; the virtual filesystem's limit and the host disk's free space are separate measurements. |

The processor configuration agrees with [AMD's specifications](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9900x.html). NVIDIA lists both 8 GB and 16 GB variants; the local NVIDIA query identifies this machine as the [16 GB variant](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5060-family/). The Windows video-controller API truncated its memory value, so that field was not used for the VRAM conclusion.

The player used approximately 94% of one logical CPU and 3.2 GiB resident memory in the observed process sample. Windows available memory varied from about 4.9 to 8.5 GiB across two snapshots. WSL reported about 10.9 GiB available, including reclaimable cache. These are live observations, not a stress test or proof of a maximum worker count.

No custom `.wslconfig` was present. Microsoft's documented default exposes the host logical processors and assigns approximately half of host memory to WSL2. Any future memory-setting change needs a maintenance boundary because WSL settings apply when the VM starts. [Microsoft WSL configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

### Recommended operating modes

| Mode | Assessment | Gate |
| --- | --- | --- |
| One actual player plus light inspection and documentation | Already demonstrated | Preserve current frozen package and limits. |
| Two isolated development workers | Best first capacity experiment | Current campaign finished, existing transfer/run boundary satisfied, benchmark plan authenticated and memory guards active. |
| Three workers | Plausible, unqualified | Two-worker throughput and memory soak pass first. |
| Four workers | Memory-sensitive experiment, not a default | Four times the sampled worker RSS is about 13 GiB before other Linux memory. Profile peak and growth across chunks first. |
| GPU learning | Future option | A useful learner bottleneck and separately qualified GPU environment justify it. |

Two workers improve experimental throughput. They do not combine progress into one save or make one campaign advance twice as fast. Use them for purposeful baseline/candidate or different failure-boundary coverage, not two copies of the same unresolved failure.

No hardware purchase is justified by the current evidence. Revisit RAM only if measured concurrent workloads exhaust memory after ordinary cache reclamation and workload sizing.

## Where time is going

The existing noninteractive emulator is already uncapped and disables sound emulation. PyBoy defines speed zero as fastest possible execution; changing a chat setting or requesting a larger speed multiplier will not accelerate this configuration. [PyBoy speed API](https://docs.pyboy.dk/api/pyboy.html)

Native receipt phase timings identify a larger target:

| Actual sample | Closed receipts | Menu and boundary observation | Native execution | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Completed V7 attempt | 94 | 2,103 seconds, about 63% of measured phases | 1,230 seconds, about 37% | Legal-option discovery and observation dominate the completed attempt. |
| Running V8 sample | 102 | 1,112 seconds, about 73% | 400 seconds, about 26% | Many short story mechanics still pay substantial menu overhead. This is a partial sample. |

Other measured phases account for the small remainder. One V7 failure has an unmeasured verification duration; it is retained as unknown. These percentages are observed phase shares, not a controlled Windows-versus-Mac speed comparison or a prediction for the final campaign.

Prior October 3 profiling already identified regional and fishing discovery as expensive. Reuse that work and the existing route/inventory caches. The next performance repair should preserve the same legal menu, quotes, resource guards and source binding while avoiding repeated work. Faster menus must never retain offers invalidated by HP, PP, inventory, location, events, custody or a changed native state.

### Training and evolution

Four level-evolution outcomes in V7 required 430 training battles and 27 healing trips; a stone evolution used one additional healing trip. Examples from the actual lineage:

| Registration earned | Training battles | Healing trips | Recorded execution time |
| --- | ---: | ---: | ---: |
| Poliwhirl | 77 | 3 | 58.6 seconds |
| Kingler | 151 | 16 | 154.3 seconds |
| Gyarados | 57 | 3 | 51.0 seconds |
| Magneton | 145 | 5 | 125.9 seconds |

These times cover the selected execution, not the whole surrounding menu and engineering cost. The events are legitimate gameplay, but battle count alone does not establish efficient preparation.

The current adapter already prefers the highest supported venue for this boxed-evolution path. One earlier related-copy comparison improved useful trainee XP per second from 57.73 to 91.87, about 59%, with more healing. That narrow improvement does not establish optimal venue selection or a whole-run speed gain.

The next objective should be useful trainee XP and completed evolution per end-to-end minute, accounting for travel, encounter rate, shared XP, battle duration, PP, healing, losses and return to the original party. The strongest wild Pokémon is not automatically the best venue. Stop at the required evolution or demonstrated readiness target rather than leveling every capture equally.

### Package and startup costs

The current frozen package identity manifest is approximately 199 MiB and contains 690,983 file pins. Of those, 683,105 fall under history or migration headings. The active goal model is a small learned ridge model with 356 input features, nine output values and 161 settled training examples; its main coefficient matrix has 3,204 entries.

This makes package parsing, validation, memory use and retained-history handling important profiling targets. Preserve all evidence and integrity guarantees. Before changing packaging, prove which historical files the runtime actually needs and measure startup separately from per-choice menu construction. Reuse existing isolation and manifest machinery rather than creating another packaging or logging framework.

## What is learned and what is execution support

| Decision or operation | Current owner | What remains to prove |
| --- | --- | --- |
| Choice among admitted semantic goals | Frozen local value model with disclosed exploration mix 0.75 | Better useful ranking, resource timing and stopping across varied states. |
| Battle choices | Existing fitted battlers and their declared tactical boundaries | Readiness and preparation should improve native outcomes across appropriate variants. |
| Navigation, menus, PC withdrawal/deposit, evolution mechanics | Deterministic title adapters | Reliable composition across battle, dialogue, travel, resource and custody boundaries. |
| A menu with one available action | Single-option support | It is not evidence of a learned comparison. |
| Temporary League medicine reserve | Disclosed rule-based support using earned resources | Learned anticipation remains a later learning question. |
| Outcome verification and native costs | Referee and recorder | Preserve typed errors, partial progress, original losses and attribution. |

The audited V7 sample contains 88 model-interface choices and six support choices. The V8 timing sample contains 41 model-interface choices and 61 support choices. The model-interface receipts are labeled exploration; they are not proof that a greedy learned policy independently chose every action optimally.

This hybrid design is a reasonable path to an autonomous player: portable decisions can be learned while execution skills handle controller mechanics. The risk is treating additional Red-specific support patches as improved learned competence. Future learning should target demonstrated preparation, cost and stopping errors with informative TRAIN contrasts, while keeping deterministic legality separate from strategic preference.

In-game XP, new registrations, engineering repairs and passing tests do not change model weights. This audit performs zero TRAIN collection, fits, new weights or runtime LLM calls.

## Reliability and project state

The recent stopped Windows attempts expose a family of composition defects: trainer introduction and battle settlement, capture-resource availability, duplicate or mismatched admission, and earning followed by legal escape and Center return. These justify better boundary coverage with the existing components before another broad rewrite or full-game replay.

| Area | Audit finding | Next action |
| --- | --- | --- |
| Working assets | Editable source, Git history, current models/helpers/runtime and relevant failures are present | Continue Windows development; verify the exact dataset before each later fit. |
| Source recovery | Git HEAD is September 27; before this audit there were 361 modified tracked files, 38 tracked deletions and 515 untracked entries | A verified local Git bundle, tracked patches and readable untracked-source archive now preserve recovery. Review existing deletions; never restore, discard or publish blindly. |
| Source scope | 748 Python source modules and 1,175 test modules; 2,293 executable/project files inventoried | Counts describe scope, not coverage or correctness. |
| Windows validation | Original 543 focused checks, eight bootstrap checks and ten supervisor checks passed; later repairs have their own targeted evidence | Do not add overlapping counts or describe them as a full-suite pass. |
| Current repair validation | Funding return has 288 focused checks, native copied qualification and a verified actual return; unchanged supervisor has 20 targeted platform checks | Retain the negative cases and qualify related failure boundaries. |
| Development tooling | Pytest is present; Ruff, mypy and pytest-xdist are absent from the frozen runtime | Use a separate development environment after the run; do not mutate the actor environment. |
| Type coverage | The project configuration names 44 legacy mypy exclusions | Shrink the relevant exclusions when touching those components; a wholesale type-cleanup project is not the next player outcome. |
| Current documentation | Main roadmap still described the Mac pause; generated review still named an older Windows continuation and monitor state | Replace current instructions, preserve history and regenerate existing projections. |
| Historical transfer | Source 04 and 05 archives verified; source 03 still receiving; source 02 remains pending | Keep the existing finite copier and awake process untouched. No claim that all archives are on Windows. |

The audit authenticates the active plan, launch, package identity, process chain, 3,792 critical pins and protected checkpoints. It does not rehash all 690,983 package data pins, rerun the full test suite or benchmark concurrent actors during the campaign.

## Roadmap after the current campaign

These are gated work packages within the existing Red roadmap stages. They do not change the final completion criteria or authorize a launch, a new cumulative budget, fitting during the current freeze, or parallel play now.

| Order | Player outcome and work | Acceptance before moving on | Initial work allowance |
| --- | --- | --- | --- |
| 1 | Seal the campaign result, custody, costs, source identity and exact next blocker; preserve a local source recovery point | Authenticated terminal and released controls; no lost failure tail, diagnostic gain or ambiguous launch authority | 30–60 minutes |
| 2 | Make the known failure boundaries reliable using existing player, battler, recovery and export components | Every reproduced failure stays retained; positive and negative contract checks plus varied copied native continuations pass without hidden fallback | One bounded session, up to three hours |
| 3 | Reduce menu, package/startup and preparation cost, one measured hotspot at a time | Same legitimate options and guards; a measured end-to-end improvement with no degraded outcome or custody checks | One or two bounded sessions |
| 4 | Benchmark one versus two isolated workers; consider a third only after two passes | Useful aggregate throughput improves while memory, swap, storage growth and per-worker correctness remain within declared guards | 30–60 minute pilot after the actor/transfer boundary |
| 5 | Improve the demonstrated model decision gaps using verified TRAIN data, retaining failures and the baseline | Held-out native outcomes improve in useful preparation, stopping or resource timing; no fitting of this DEVELOPMENT lineage | One specific learning question per bounded session |
| 6 | Freeze a qualified candidate and prepare a separately authorized clean-start acceptance campaign | Source, weights, configuration, support, seeds, exclusions and budgets fixed before launch; native Champion/HOF plus 124 in one unchanged save | Campaign budget chosen from measured runtime |
| 7 | Establish reliability and transfer | Keep every attempt; the existing reliability target is at least eight successes in ten preregistered held-out clean-start attempts, followed by the compatible-hack comparison | Gate-driven, not a promised completion date |
| 8 | Transfer through Crystal and then toward Emerald | Measure reuse versus a learner without Red experience; learn new mechanics and maintain explicit deferred-species gaps | After the Red gate |

The final native audit found the empty postgame menu; package 2 addresses that exact blocker first. If mechanics are sound but useful decisions are poor, use package 5 sooner. Do not spend successive sessions on infrastructure while avoiding the actual learning question.

### Concurrency pilot

Use the existing prepared isolation approach: one source writer, immutable candidate identities, independent output/save directories, separate ports, no shared writable model or state, and complete costs for every worker. No progress merges. Related checkpoint copies are correlated component evidence; independent clean-start campaigns remain separate attempts.

Measure cold startup, warm menu time, useful outcomes per hour, frames per second, model/support counts, peak and growth of RSS, host/WSL memory, swap and log bytes per hour. Compare the same workload serially and with two workers; include validation and recording costs.

Proposed decision thresholds, not measured results: retain two workers if aggregate useful throughput reaches at least 1.6 times the single-worker baseline, per-worker slowdown stays within 25%, host available memory stays above 6 GiB, WSL available memory stays above 2 GiB, and swap does not grow persistently. Keep the existing stronger reserve where a run declares one. If those conditions fail, improve one worker before expanding.

The prior transfer/run boundary remains in force for parallel trials. Incomplete historical backup does not block serial development. If that boundary is still unresolved after the campaign, leave the pilot queued while reliability and profiling work proceeds.

### First three work sessions

1. **Terminal review and reliability.** Seal the actual result and source recovery point, then select the highest-impact reproduced boundary. Reuse the existing native recorder/referee and copied qualification. Finish with an exact failure retained and a positive/negative contract result.
2. **Throughput and preparation.** Attribute one slow menu to its discovery families. Compare a contained optimization against identical legal menus and end-to-end costs. For training, compare useful XP and completed evolution per minute, including healing and travel. Do not replay all of Red to measure a local defect.
3. **Capacity and learning decision.** Run the qualified two-worker pilot only when its boundary is satisfied. Use its evidence to choose concurrency. Then select one demonstrated model decision gap for the next TRAIN-only learning mission, or freeze readiness if no such gap remains.

Each ordinary work session is bounded to at most three hours unless a new work order specifies otherwise. Reassess an issue after 15 minutes or two equivalent failures and change tactics. Stop for unverifiable state, exhausted applicable limits, unavailable prerequisites, a human pause or a material expansion of scope.

## Measures that keep the roadmap honest

- **Player success:** same-save story completion, required registrations and custody; never stitched totals.
- **Reliability:** unhandled execution/admission failures and time between required engineering repairs, with ordinary game losses reported separately.
- **Efficiency:** useful registrations/evolutions and readiness improvement per end-to-end hour; XP, frames and cash/healing costs remain supporting measures.
- **Autonomy:** genuine model comparisons, exploration and support decisions shown separately; learned stopping and resource anticipation need their own evidence.
- **Learning:** only verified TRAIN examples, actual fits and held-out outcome changes count. Historical counters do not advance because of this audit.
- **Capacity:** throughput and memory measured for the actual workload; CPU core count and GPU specifications do not establish emulator worker capacity.

The immediate next decision is to diagnose the preserved 117-registration postgame menu on copies and qualify a continuation if the existing resources and mechanics permit one. A zero-input, zero-frame copy already reproduces the empty menu with unchanged bytes and no model query; a blind restart would not repair it. Later copied diagnosis distinguished Lance exhaustion at 80 decisions from a loss: the unchanged same-battle lifecycle won with one further decision, then the low-stock party lost to Champion. No smaller medicine reserve or complete earning cycle has qualified. The next repair must test existing ordinary funding or truthful loss recovery; all copied gains remain excluded from the actual 117. The broader post-run priorities remain boundary reliability and the measured menu bottleneck. Preserve the same save, all failed runs, originals and historical copies. No deletion, publication, external agents or remote-access changes are part of this roadmap.
