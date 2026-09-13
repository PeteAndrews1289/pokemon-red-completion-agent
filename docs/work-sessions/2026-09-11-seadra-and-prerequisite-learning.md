# Seadra and prerequisite learning

The retained Red learner completed four more model-directed development decisions. It evolved the newly caught Horsea into Seadra, then earned money, bought one capture item and restored the party. The collection advanced from 69 to 70 registered species and the model from 90 to 94 settled examples.

[Path-free evidence](../evidence/red-seadra-prerequisite-learning-2026-09-11.json).

## What ran

- BR01 exposed evolution and acquisition. The model selected evolution; deterministic mechanics trained Horsea into Seadra and registered national #117. It used 4,378 actions and 371,135 frames.
- BS01 exposed two high-level goals. The model selected resupply and earned 550, moving cash from 543 to 1,093.
- BS02 exposed four goals. The model again selected resupply and bought one capture item for 600, leaving 493 cash and four capture items.
- BS03 exposed two goals. The model selected recovery and restored the injured lead from 72 to 88 HP.

Every selected outcome succeeded and was fitted exactly once. There were no retries, teacher fallbacks, authority promotions, sealed Red accesses, Crystal accesses or full-game replays. The final model contains 94 settled examples, 61 successful outcomes and 22 economy-qualified examples.

## Audit

A separate read-only audit reopened each retained terminal, checked its state and ROM digests, reconstructed the Pokédex from party and boxes, verified resource counts and input readiness, and joined the final model and training corpus through their sealed hashes. The audit used zero controller actions, advanced zero frames, made zero predictions and performed zero fits.

The final save is input-ready on Seafoam B4F with 70 registrations, 54 living species, 58 specimens, 493 money, four capture items and party HP 88/118/150/90/120/249.

## Engineering result

Regional inventory now shares exact route plans within one read-only scan and limits full route enumeration to acquisition candidates. On the exact endpoint the candidate order and menu hash stayed identical, but wall time improved only from 257.442 to 246.736 seconds—about 4.2%. That refactor is safe, but it is not a meaningful throughput solution.

The following live run exposed a separate semantic issue: six regional sources could be distinct identities yet have identical title-neutral feature rows. The cycle now refuses to manufacture a source-choice label in that case. It may make a deterministic source proposal for mechanics, while the learned parent policy still chooses the actual high-level goal. All three BS steps therefore trained only the genuine resupply/recovery decision, not the proposed region.

## Reorientation

Do not spend another session optimizing the four-minute scan. The product goal is a player that accumulates missing registrations. Continue from BS03/model94 with the preserved resources and seek a bounded acquisition or useful evolution. The next acceptance item is another verified registration under model-selected high-level authority; failures and prerequisite decisions remain valid training data, but do not satisfy that item.

This remains bounded saved-state learning. It does not establish fresh-game autonomy, arbitrary-seed reliability, complete Red collection or transfer to Blue, a Red modification or Crystal.
