# Verified retirement of 578 old run logs

Pete authorized the exact archive-first list from the
[retention audit](2026-10-15-run-retention-audit.md). All 578 originals are now
removed after durable archival and full verification. The observed net physical
recovery is **18,799,828,992 bytes / 17.5087 GiB**, including archive and restoration
test costs. No whole run directory was removed.

| Volume | Files removed | Observed net free-space gain |
| --- | ---: | ---: |
| T7 Developer | 565 | 12.6418 GiB |
| Pokémon Runs | 13 | 4.8669 GiB |
| Pokémon Runs 2 and T7 backup | 0 | 0 |

The shared APFS container rose from 87,279,710,208 to 106,079,539,200 free bytes;
three settled samples agree. All archives live on T7 Developer, rather than being
split by source volume. APFS container and summed volume gains differ by 4 KiB.
Later documentation writes use a small additional amount.

## Verification and preserved data

578 ordinary gzip files retain 1,566,304,823 compressed bytes / 1.4587 GiB. Every
payload passed full decompression, exact byte count and SHA-256 before removal
and again afterward. One complete episode was restored and decoded through the
existing reader, and one isolation report restored and parsed. Small restoration
copies remain and are included in the measured net result.

The exact 578 receipts match the approved list. All source parents remain.
12,701 package/environment/protected pins and 2,060 retained sibling/input files
rehash unchanged. Models, curated training data, saves, source, outcomes, backups
and all 38 files excluded from the broader survey stay in place. Raw historical
teacher replay bytes remain losslessly archived; their old full-manifest readers
require restoration before use. Archives on the same drive are not independent
backups. No other files or later journal batches were retired.

Eight focused safety tests pass. Two maintenance portability issues were corrected
before removal; no production guard or player code was weakened. This is not a
full-suite/CI or gameplay qualification.

## Recovery records

The private audit packet's approved-retirement-v1 directory contains CLEANUP.md,
CATALOG.json, CATALOG-SEAL.json, payloads, RESTORE.md, immutable RESULT.json and
per-file EVENTS.jsonl. The proposal hash remains
f269bcb084011671ae1bf23c7756ee4473cc4484c785f9136e4e8f80652db46f;
catalog ae44d071fe7f9ff2333ff09f52d9c3de5c5daf68e278b15212f4ee4fb7e2a714;
result 17bae54074ea9d435e38bbf29de78c536573e364db31f04fc6c079c18409997a.
[Path-free evidence](../evidence/red-run-retirement-2026-10-15.json).

## Outcome and next session

This fulfills the approved cleanup. No actor was resumed, no model input was
changed and no TRAIN, fit, weight or registration delta occurred. The completed
reference and failed frozen attempts remain separate; fresh final gates stay 0/5.
The existing monitor remains paused. [HANDOFF.md](../../HANDOFF.md) owns next work.

Before another long run, scope prospective leaner logging and verify the chosen
existing output volume has sufficient headroom. Reuse current receipts, readers
and stop guards; test compatibility and size on a short copy, not a fresh campaign.
Allow up to two hours, reassessing after 15 stalled minutes or two equivalent
failures. Stop for lost evidence or broader architecture. No further deletion,
volume change, fitting, save edits or publication. Suggested maintenance setting:
6.1 Sol High, normal speed/Fast off; no setting change is claimed.
