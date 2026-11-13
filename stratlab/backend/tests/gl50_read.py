"""gl50 (R50, the rotating review: the live Biotech and Capital goods decks ranked layers with no company's way of earning read): a chain
whose layers have no way of earning read is shown, never ranked. Synthetic maps built before R25 carry no models; the tests of the ranking
rules give their layers one (`read`), so they go on testing the rule they were written for (updated on purpose)."""
import copy

READ = {"id": "manufacturing", "family": "making"}


def read(m, f=None, *rest, model=None):
    """The map `m` with every layer that has companies and no model given `model` (READ); (m, f, *rest) when given more, as deck_of takes."""
    m = copy.deepcopy(m)
    for v in m.get("value_chain") or []:
        if v.get("companies") and not v.get("model"):
            v["model"] = dict(model or READ)
    return (m, f, *rest) if f is not None else m


def blocks(bs, model=None):
    """chain_table's blocks, each given a model (READ) where it has none."""
    return [{**b, "model": b.get("model") or dict(model or READ)} for b in bs]


def read_args(args, model=None):
    """deck_of's arguments (region, map, facts, ...) with the map's layers given a model (read)."""
    return tuple(read(a, model=model) if isinstance(a, dict) and "value_chain" in a else a for a in args)
