"""One explicit earned five-room chain; no general League model admission."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .observation import EventFlag, event_flag_is_set

LEAGUE_CHAIN_ADMISSION_SHA256 = "b2a0c70689cf2770238215da07a45ba25bdc5005b2c66da819f6da23fce92aa8"
LEAGUE_CHAIN_ROOT_SHA256 = "303cc6841d71a3a1cee219f387f041948814daf42e59066c692d15d3cdc3992d"
LEAGUE_CHAIN_ENVELOPE_SHA256 = "4abd3b57fdaee6ee0167ac2f167207164714cacfd860da208620c48992ce1cb0"
LEAGUE_CHAIN_TARGETS = (
    ("defeat_lorelei", "cartridge-trainer-story", 245, (244, 44, 1), 2273, 5544),
    ("defeat_bruno", "cartridge-trainer-story", 246, (233, 33, 1), 2281, 5742),
    ("defeat_agatha", "cartridge-trainer-story", 247, (246, 46, 1), 2289, 5940),
    ("defeat_lance", "cartridge-trainer-story", 113, (247, 47, 1), 2297, 6138),
    ("defeat_champion", "cartridge-final-story", 120, (243, 43, 2), 2305, 6435),
)


def _digest(path):
    return sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class EarnedLeagueStepScope:
    """Authenticate each successor against retained earned predecessor outcomes.

    The outer runner also checks loaded native state, costs, event flags, envelope
    and the global 15000-action/15-item budget. These are not policy features.
    """

    campaign: Path
    index: int

    def binding(self, battler):
        from .red_learned_trainer import AGATHA_STORY_SHA256

        if (
            type(self.index) is not int
            or not 0 <= self.index < 5
            or not isinstance(self.campaign, Path)
            or not self.campaign.is_absolute()
            or self.campaign.resolve() != self.campaign
        ):
            raise ValueError("invalid earned League chain location or index")
        root = self.campaign / "stage-465"
        if (
            _digest(root / "final.state") != LEAGUE_CHAIN_ROOT_SHA256
            or _digest(root / "final.envelope.json") != LEAGUE_CHAIN_ENVELOPE_SHA256
        ):
            raise ValueError("earned League chain root differs")
        source_sha = LEAGUE_CHAIN_ROOT_SHA256
        for i in range(self.index):
            directory = self.campaign / f"stage-{466 + i:03d}"
            claim = json.loads((directory / "claim.json").read_bytes())
            final = json.loads((directory / "final.json").read_bytes())
            completion = json.loads((directory / "battle-completion.json").read_bytes())
            terminal_sha = _digest(directory / "final.state")
            if (
                claim.get("chain_index") != i
                or claim.get("chain_root_sha256") != LEAGUE_CHAIN_ROOT_SHA256
                or claim.get("source_sha256") != source_sha
                or claim.get("model_sha256") != AGATHA_STORY_SHA256
                or claim.get("admission_sha256") != LEAGUE_CHAIN_ADMISSION_SHA256
                or claim.get("campaign_execution") is not True
                or final.get("sha256") != terminal_sha
                or final.get("error") is not None
                or final.get("safe") is not True
                or completion.get("outcome") != "won"
                or completion.get("field_ready") is not True
                or completion.get("episode", {}).get("battle_won") is not True
                or completion.get("final_map") != LEAGUE_CHAIN_TARGETS[i][2]
            ):
                raise ValueError("earned League predecessor is not an authenticated victory")
            source_sha = terminal_sha
        if (
            battler.source_state_sha256 != source_sha
            or battler.output != self.campaign / f"stage-{466 + self.index:03d}"
            or battler.model_sha256 != AGATHA_STORY_SHA256
            or battler.qualification_sha256 != LEAGUE_CHAIN_ADMISSION_SHA256
        ):
            raise ValueError("earned League successor source/model/output differs")
        return source_sha, LEAGUE_CHAIN_TARGETS[self.index]


def require_chain_live_boundary(raw, index):
    """Historical progress cannot bypass the cartridge's current room order."""
    if type(index) is not int or not 0 <= index < 5 or raw.event_flags is None:
        raise ValueError("invalid live League boundary")
    if raw.battle_state or not any(raw.party_hp or ()):
        raise ValueError("League field boundary requires a living nonbattle party")
    for i, target in enumerate(LEAGUE_CHAIN_TARGETS):
        if event_flag_is_set(raw.event_flags, target[4]) != (i < index):
            raise ValueError("live League defeat flags differ from the bound room order")
    if event_flag_is_set(raw.event_flags, EventFlag.BEAT_LANCE) != (index == 4):
        raise ValueError("live Lance scene flag differs from the bound room order")


def require_owned_chain_stock(raw, initial_bag, spent):
    """No resupply or item substitution can hide the finite preparation cost."""
    from .observation import ItemId

    caps = {
        int(ItemId.POTION): 7,
        int(ItemId.HYPER_POTION): 3,
        int(ItemId.REVIVE): 4,
        int(ItemId.FULL_HEAL): 1,
    }
    if not isinstance(spent, dict) or any(k not in caps for k in spent):
        raise ValueError("unsupported League preparation item")
    expected = dict(initial_bag)
    if len(expected) != len(initial_bag) or any(expected.get(i) != n for i, n in caps.items()):
        raise ValueError("initial owned League reserve differs")
    for item, count in spent.items():
        if type(count) is not int or not 0 <= count <= caps[item]:
            raise ValueError("owned League item budget exceeded")
        left = expected[item] - count
        if left:
            expected[item] = left
        else:
            expected.pop(item)
    if (
        raw.bag_items is None
        or len(dict(raw.bag_items)) != len(raw.bag_items)
        or (dict(raw.bag_items) != expected)
    ):
        raise ValueError("League inventory no longer matches retained preparation cost")
