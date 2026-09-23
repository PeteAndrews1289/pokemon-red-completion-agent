"""Typed native NPC exchange evidence, separate from capture and evolution.

Only a trusted native recorder may seal these facts. Hashes bind its observations;
they are not signatures and do not authenticate arbitrary user-supplied JSON.
No exchange identity or memory intervention becomes a policy feature.
"""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256

from .provenance import canonical_sha256
from .red_collection import red_species_ref
from .red_npc_trade import stationary_npc_trades

ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
SCHEMA = "pokemon.red.native-npc-exchange.v1"
# Derived from stationary_npc_trades on the pinned cartridge, not hand-written
# exchange pairs. Bind the entire table/script/object descriptor on reconstruction.
OFFER_DIGESTS = frozenset(
    {
        "4e17065118c835f34c2da7f5598688cb70e57340681ae8fdb4c1d6b5e73c91b0",
        "1f6e718fd6d125a2140ea73c9fc4ed0b4839ca7dc4445478cfd999fc16f829ab",
    }
)


def exchange_snapshot(observation, flags):
    """Record fresh native counts including levels; registration alone is not stock."""
    stock = Counter((s.species_ref, s.level) for s in observation.collection_observation.specimens)
    return dict(
        stock=[[s, level, n] for (s, level), n in sorted(stock.items())],
        flags=sorted(flags),
        cash=observation.raw.player_money,
        bag=[list(x) for x in observation.raw.bag_items],
        map_id=int(observation.raw.map_id),
        battle=int(observation.raw.battle_state),
        ready=observation.input_ready,
    )


def declare_npc_exchange(rom, trade, before, *, flags, level):
    if sha256(rom).hexdigest() != ROM_SHA256 or trade not in stationary_npc_trades(rom):
        raise ValueError("NPC exchange cartridge/offer differs")
    offer = asdict(trade)
    offer["at"] = list(offer["at"])
    declaration = dict(
        schema=SCHEMA,
        rom_sha256=ROM_SHA256,
        offer=offer,
        level=level,
        before=exchange_snapshot(before, flags),
    )
    validate_exchange_declaration(before.registered_checkpoint, declaration)
    return declaration


def _stock(snapshot, checkpoint):
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"stock", "flags", "cash", "bag", "map_id", "battle", "ready"}
        or type(snapshot["cash"]) is not int
        or not 0 <= snapshot["cash"] <= 999999
        or type(snapshot["map_id"]) is not int
        or not 0 <= snapshot["map_id"] < 248
        or type(snapshot["battle"]) is not int
        or snapshot["battle"] != 0
        or snapshot["ready"] is not True
    ):
        raise ValueError("NPC exchange native snapshot differs")
    flags = snapshot["flags"]
    if (
        not isinstance(flags, list)
        or any(type(x) is not int or not 0 <= x < 10 for x in flags)
        or flags != sorted(set(flags))
    ):
        raise ValueError("NPC exchange flags differ")
    bag = snapshot["bag"]
    if (
        not isinstance(bag, list)
        or len(bag) > 20
        or any(
            not isinstance(x, list)
            or len(x) != 2
            or any(type(v) is not int for v in x)
            or not 1 <= x[0] <= 255
            or not 1 <= x[1] <= 99
            for x in bag
        )
        or len({x[0] for x in bag}) != len(bag)
    ):
        raise ValueError("NPC exchange bag differs")
    rows = snapshot["stock"]
    if (
        not isinstance(rows, list)
        or any(
            not isinstance(x, list)
            or len(x) != 3
            or not isinstance(x[0], str)
            or type(x[1]) is not int
            or not 1 <= x[1] <= 100
            or type(x[2]) is not int
            or not 1 <= x[2] <= 246
            for x in rows
        )
        or rows != sorted(rows)
        or len({(x[0], x[1]) for x in rows}) != len(rows)
    ):
        raise ValueError("NPC exchange stock differs")
    counts = Counter()
    for s, _, n in rows:
        counts[s] += n
    if dict(counts) != dict(checkpoint.specimen_counts):
        raise ValueError("NPC exchange native stock differs from registration")
    return Counter({(s, level): n for s, level, n in rows})


def validate_exchange_declaration(before, declaration):
    if (
        not isinstance(declaration, dict)
        or set(declaration) != {"schema", "rom_sha256", "offer", "level", "before"}
        or declaration["schema"] != SCHEMA
        or declaration["rom_sha256"] != ROM_SHA256
        or canonical_sha256(declaration["offer"]) not in OFFER_DIGESTS
        or type(declaration["level"]) is not int
        or not 1 <= declaration["level"] <= 100
    ):
        raise ValueError("NPC exchange declaration differs")
    offer = declaration["offer"]
    source, target = red_species_ref(offer["give"]), red_species_ref(offer["receive"])
    stock = _stock(declaration["before"], before)
    if (
        offer["index"] in declaration["before"]["flags"]
        or target in before.local_species
        or stock[source, declaration["level"]] < 1
        or dict(before.specimen_counts).get(source, 0)
        <= dict(before.protected_counts).get(source, 0)
    ):
        raise ValueError("NPC exchange source, target or unused flag differs")
    return source, target, stock


def require_npc_exchange_transition(before, after, declaration, witness):
    source, target, expected = validate_exchange_declaration(before, declaration)
    actual = _stock(witness, after)
    expected[source, declaration["level"]] -= 1
    expected[target, declaration["level"]] += 1
    first, offer = declaration["before"], declaration["offer"]
    if (
        actual != +expected
        or set(witness["flags"]) != set(first["flags"]) | {offer["index"]}
        or witness["map_id"] != offer["map_id"]
        or witness["cash"] != first["cash"]
        or witness["bag"] != first["bag"]
        or after.local_species != tuple(sorted(set(before.local_species) | {target}))
        or after.global_species != tuple(sorted(set(before.global_species) | {target}))
        or any(
            getattr(before, k) != getattr(after, k)
            for k in (
                "binding_sha256",
                "completion_scope",
                "completion_contract_sha256",
                "target_species",
                "protected_counts",
                "allowed_evolutions",
            )
        )
    ):
        raise ValueError("NPC exchange lacks an exact native transition")
