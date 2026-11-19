"""Task-only native coverage beside an explicitly masked inherited quest.

This reader grants no source legitimacy, fitting admission or policy authority.
It retains exact native milestone predicates from the existing reader. General
progress and resource/loss labels remain unknown. A masked source claim must be
present and unchanged in every receipt; it cannot become a new task reward.
"""

from dataclasses import replace

from .provenance import canonical_sha256
from .red_sequence_state_audit import ScopedStorySequenceStateReader


class TaskSequenceStateReader:
    target_channels = frozenset({"completed_quests", "actions", "frames"})
    retain_saffron_arrival = False

    def __init__(self, reader, *, masked_source_quests=frozenset()):
        if (
            type(reader) is not ScopedStorySequenceStateReader
            or type(masked_source_quests) is not frozenset
            or not masked_source_quests <= {"reach_saffron"}
            or masked_source_quests & set(reader.objectives)
            or not set(reader.objectives) <= reader.quest_scope - masked_source_quests
        ):
            raise ValueError("task-only audit requires existing native predicates and a nontarget source mask")
        self.reader = reader
        self.masked_source_quests = masked_source_quests
        self.quest_scope = frozenset(reader.objectives)
        self.task_progress = tuple("quest:" + x for x in reader.objectives)
        self.task_sha256 = reader.task_sha256
        self.catalog_sha256 = canonical_sha256(self.document())

    def document(self):
        return dict(
            schema="pokemon.red.task-only-sequence-audit.v1",
            base_catalog_sha256=self.reader.catalog_sha256,
            task_sha256=self.task_sha256,
            task_quests=sorted(self.quest_scope),
            masked_source_quests=sorted(self.masked_source_quests),
            source_mask_rule="already reported before input; present in every before/after; never new credit",
            target_channels=sorted(self.target_channels),
            unknown_channels=["native_progress", "observed_cash_debits", "observed_cash_credits", "battle_losses"],
            inherited_source_arrival_verified=False,
        )

    def validate_source_claims(self, rows):
        if type(rows) not in (tuple, list) or not rows:
            raise ValueError("task-only audit requires the complete recorded outcome chain")
        for row in rows:
            for boundary in ("before", "after"):
                reported = row[boundary]["completed_objectives"]
                if (
                    type(reported) is not list
                    or any(type(q) is not str for q in reported)
                    or not self.masked_source_quests <= set(reported)
                ):
                    raise ValueError("masked inherited quest must remain present and cannot be newly acquired")

    def task_completed(self, initial, terminal):
        return bool((set(terminal) - set(initial)) & set(self.task_progress))

    def read(self, path, expected_sha256):
        boundary = self.reader.read(path, expected_sha256)
        if (
            "reach_saffron" in self.masked_source_quests
            and "story:saffron_guards_open" not in boundary.progress
        ):
            raise ValueError("masked Saffron source claim lacks current native guard access")
        quests = tuple(sorted(set(boundary.quests) & self.quest_scope))
        return replace(
            boundary,
            progress=tuple("quest:" + q for q in quests),
            quests=quests,
        )
